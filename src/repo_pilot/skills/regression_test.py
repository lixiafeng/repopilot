from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from repo_pilot.provider import Provider
from repo_pilot.skills.base import Skill, SkillContext, SkillResult
from repo_pilot.tools import CommandTools


@dataclass(slots=True)
class GeneratedRegressionTest:
    """One regression test proposed by a generator."""

    path: str
    content: str
    rationale: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0


class RegressionTestGenerator(Protocol):
    def generate(
        self,
        context: SkillContext,
    ) -> GeneratedRegressionTest:
        ...


class ProviderRegressionTestGenerator:
    """LLM-backed generator that reuses RepoPilot's existing Provider."""

    def __init__(
        self,
        provider: Provider,
        *,
        max_context_files: int = 6,
        max_chars_per_file: int = 2500,
        max_total_context_chars: int = 12000,
    ) -> None:
        self.provider = provider
        self.max_context_files = max_context_files
        self.max_chars_per_file = max_chars_per_file
        self.max_total_context_chars = max_total_context_chars

    def generate(
        self,
        context: SkillContext,
    ) -> GeneratedRegressionTest:
        prompt = self._build_prompt(context)
        response = self.provider.complete(prompt)
        payload = self._parse_json_object(response.content)

        path = payload.get("path")
        content = payload.get("content")
        rationale = payload.get("rationale", "")

        if not isinstance(path, str):
            raise ValueError(
                "Regression-test response field 'path' must be a string."
            )

        if not isinstance(content, str):
            raise ValueError(
                "Regression-test response field 'content' must be a string."
            )

        if not isinstance(rationale, str):
            rationale = str(rationale)

        return GeneratedRegressionTest(
            path=path,
            content=content,
            rationale=rationale,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            estimated_cost=response.estimated_cost,
        )

    def _build_prompt(
        self,
        context: SkillContext,
    ) -> str:
        repo_context = self._collect_repo_context(
            repo=context.repo_path,
            diff=context.diff or "",
        )

        return f"""
TASK: GENERATE_REGRESSION_TEST

You are adding ONE focused pytest regression test after an existing
repository repair has already passed its original verification.

ISSUE:
{context.issue}

APPLIED DIFF:
{context.diff or "(no diff supplied)"}

ORIGINAL TEST COMMAND:
{context.test_command or "(not supplied)"}

CURRENT REPOSITORY CONTEXT AFTER THE PATCH:
{repo_context}

Requirements:
1. Return exactly one JSON object and no markdown.
2. Do not modify implementation code.
3. Generate one focused pytest regression test for the repaired behavior.
4. Prefer the repository's existing test layout and import style.
5. The test should protect the bug described by the issue and applied diff.
6. Do not merely duplicate an existing assertion when a meaningful regression
   case can be expressed.
7. The path must be relative to the repository.
8. The Python filename must start with "test_".
9. Do not use network access, sleeps, shell commands, or destructive actions.

Return this exact JSON shape:
{{
  "path": "tests/test_repopilot_regression.py",
  "content": "complete Python test file contents",
  "rationale": "short explanation of what regression this protects"
}}
""".strip()

    def _collect_repo_context(
        self,
        *,
        repo: Path,
        diff: str,
    ) -> str:
        repo = repo.resolve()
        paths: list[Path] = []

        for relative_name in self._changed_files(diff):
            candidate = (repo / relative_name).resolve()

            try:
                candidate.relative_to(repo)
            except ValueError:
                continue

            if (
                candidate.exists()
                and candidate.is_file()
                and candidate.suffix == ".py"
            ):
                paths.append(candidate)

        test_paths = sorted(
            {
                *repo.rglob("test_*.py"),
                *repo.rglob("*_test.py"),
            }
        )

        for candidate in test_paths:
            if candidate not in paths:
                paths.append(candidate)

        chunks: list[str] = []
        total_chars = 0

        for path in paths[: self.max_context_files]:
            try:
                content = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError:
                continue

            remaining = self.max_total_context_chars - total_chars

            if remaining <= 0:
                break

            snippet = content[
                : min(
                    self.max_chars_per_file,
                    remaining,
                )
            ]

            relative = path.relative_to(repo).as_posix()

            chunks.append(
                f"--- {relative} ---\\n"
                f"{snippet}"
            )

            total_chars += len(snippet)

        if not chunks:
            return "(no repository snippets available)"

        return "\\n\\n".join(chunks)

    @staticmethod
    def _changed_files(diff: str) -> list[str]:
        paths: list[str] = []

        for match in re.finditer(
            r"^\\+\\+\\+ b/(.+)$",
            diff,
            flags=re.MULTILINE,
        ):
            path = match.group(1).strip()

            if (
                path
                and path != "/dev/null"
                and path not in paths
            ):
                paths.append(path)

        return paths

    @staticmethod
    def _parse_json_object(
        content: str,
    ) -> dict[str, Any]:
        text = content.strip()

        if text.startswith("```"):
            lines = text.splitlines()

            if lines:
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\\n".join(lines).strip()

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Regression-test provider did not return valid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise ValueError(
                "Regression-test provider response must be a JSON object."
            )

        return payload


class RegressionTestSkill(Skill):
    """
    Generate and execute one temporary regression test in the task workspace.

    The generated file is removed after execution by default. If the generated
    path already existed, the original contents are restored.
    """

    name = "regression_test"

    def __init__(
        self,
        generator: RegressionTestGenerator,
        *,
        timeout_seconds: int = 60,
        keep_generated_test: bool = False,
        commands: CommandTools | None = None,
    ) -> None:
        self.generator = generator
        self.timeout_seconds = timeout_seconds
        self.keep_generated_test = keep_generated_test
        self._uses_default_commands = commands is None
        self._commands = commands or CommandTools(timeout_sec=timeout_seconds)

    @property
    def commands(self) -> CommandTools:
        return self._commands

    @commands.setter
    def commands(self, value: CommandTools) -> None:
        self._commands = value
        self._uses_default_commands = False

    def run(
        self,
        context: SkillContext,
    ) -> SkillResult:
        repo = context.repo_path.resolve()

        if not repo.exists() or not repo.is_dir():
            return SkillResult(
                name=self.name,
                success=False,
                message=f"Repository path does not exist: {repo}",
            )

        try:
            generated = self.generator.generate(context)
            target = self._resolve_target(
                repo,
                generated.path,
            )
        except Exception as exc:
            return SkillResult(
                name=self.name,
                success=False,
                message=f"Failed to generate regression test: {exc}",
                data={"failure_kind": "generation_error"},
            )

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        existed_before = target.exists()
        original_content: str | None = None

        if existed_before:
            original_content = target.read_text(
                encoding="utf-8",
                errors="replace",
            )

        started = time.perf_counter()

        try:
            target.write_text(
                generated.content,
                encoding="utf-8",
            )

            relative_target = target.relative_to(repo)

            python = sys.executable if self._uses_default_commands else "python"
            command = subprocess.list2cmdline(
                [python, "-m", "pytest", "-q", str(relative_target)]
            )
            completed = self.commands.run(command=command, cwd=repo)

            duration = time.perf_counter() - started
            output = self._merge_output(
                completed.stdout,
                completed.stderr,
            )

            return SkillResult(
                name=self.name,
                success=completed.success,
                message=(
                    "Generated regression test passed."
                    if completed.success
                    else "Generated regression test failed."
                ),
                data={
                    "test_path": relative_target.as_posix(),
                    "test_content": generated.content,
                    "rationale": generated.rationale,
                    "exit_code": completed.exit_code,
                    "duration_seconds": round(duration, 4),
                    "output": output,
                    "timeout": completed.timeout,
                    "failure_kind": (
                        None
                        if completed.success
                        else "timeout"
                        if completed.timeout
                        else "test_failure"
                        if completed.exit_code == 1
                        else "execution_error"
                    ),
                    "model_calls": 1,
                    "input_tokens": generated.input_tokens,
                    "output_tokens": generated.output_tokens,
                    "estimated_cost": generated.estimated_cost,
                },
            )

        except Exception as exc:
            duration = time.perf_counter() - started

            return SkillResult(
                name=self.name,
                success=False,
                message=f"Regression test execution failed: {exc}",
                data={
                    "test_path": target.relative_to(repo).as_posix(),
                    "test_content": generated.content,
                    "rationale": generated.rationale,
                    "duration_seconds": round(duration, 4),
                    "failure_kind": "execution_error",
                    "model_calls": 1,
                    "input_tokens": generated.input_tokens,
                    "output_tokens": generated.output_tokens,
                    "estimated_cost": generated.estimated_cost,
                },
            )

        finally:
            if not self.keep_generated_test:
                self._restore_target(
                    repo=repo,
                    target=target,
                    existed_before=existed_before,
                    original_content=original_content,
                )

    @staticmethod
    def _resolve_target(
        repo: Path,
        generated_path: str,
    ) -> Path:
        raw = generated_path.strip().replace("\\\\", "/")

        if not raw:
            raise ValueError(
                "Generated test path must not be empty."
            )

        relative = Path(raw)

        if relative.is_absolute():
            raise ValueError(
                "Generated test path must be relative."
            )

        if relative.suffix != ".py":
            raise ValueError(
                "Generated regression test must be a Python file."
            )

        if not relative.name.startswith("test_"):
            raise ValueError(
                "Generated regression test filename must start with 'test_'."
            )

        target = (repo / relative).resolve()

        try:
            target.relative_to(repo)
        except ValueError as exc:
            raise ValueError(
                "Generated test path escapes the repository workspace."
            ) from exc

        return target

    @staticmethod
    def _restore_target(
        *,
        repo: Path,
        target: Path,
        existed_before: bool,
        original_content: str | None,
    ) -> None:
        if existed_before:
            target.write_text(
                (
                    original_content
                    if original_content is not None
                    else ""
                ),
                encoding="utf-8",
            )
            return

        try:
            target.unlink()
        except FileNotFoundError:
            return

        parent = target.parent

        while parent != repo:
            try:
                parent.rmdir()
            except OSError:
                break

            parent = parent.parent

    @staticmethod
    def _merge_output(
        stdout: str | None,
        stderr: str | None,
    ) -> str:
        parts: list[str] = []

        if stdout:
            parts.append(stdout.rstrip())

        if stderr:
            parts.append(stderr.rstrip())

        return "\\n".join(parts)

    @staticmethod
    def _to_text(
        value: str | bytes | None,
    ) -> str:
        if value is None:
            return ""

        if isinstance(value, bytes):
            return value.decode(
                "utf-8",
                errors="replace",
            )

        return value
