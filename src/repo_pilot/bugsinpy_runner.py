"""Sequential BugsInPy experiments on Linux (including WSL and containers)."""

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from repo_pilot.bugsinpy import BugsInPyAdapter
from repo_pilot.config import RepoPilotConfig
from repo_pilot.tools import CommandResult


class LoggedCommands:
    """Use a checkout's environment without changing the runner's environment."""

    def __init__(self, env: dict[str, str], log_dir: Path, timeout_sec: int):
        self.env = env
        self.log_dir = log_dir
        self.timeout_sec = timeout_sec
        self.counter = 0

    def run(self, command: str, cwd: Path) -> CommandResult:
        if command == "python -m compileall . -q":
            command = "python -m compileall -q -x '(^|/)(env|\\.git)/' ."
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.counter += 1
        started = time.monotonic()
        proc = subprocess.Popen(
            command, cwd=cwd, env=self.env, shell=True, executable="/bin/bash",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", start_new_session=True,
        )
        timeout = False
        try:
            stdout, stderr = proc.communicate(timeout=self.timeout_sec)
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
        except BaseException:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise
        result = CommandResult(
            command=command, exit_code=124 if timeout else proc.returncode,
            stdout=stdout, stderr=stderr,
            duration_seconds=time.monotonic() - started, timeout=timeout,
        )
        (self.log_dir / f"{self.counter:04d}.json").write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result


class StageError(RuntimeError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


class BugsInPyRunner:
    """Prepare, reproduce, repair and independently evaluate each strategy.

    The dataset clone is mutable in upstream checkout scripts: do not share it
    between simultaneous runners. Results and workspaces are retained for audit.
    """

    def __init__(
        self, dataset_root: Path, output_root: Path, config: RepoPilotConfig,
        *, setup_timeout: int = 1800,
        workflow_factories: dict[str, Callable] | None = None,
    ):
        self.dataset_root = Path(dataset_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.config = config
        self.setup_timeout = setup_timeout
        self.workflow_factories = workflow_factories
        if setup_timeout <= 0 or config.command_timeout_sec <= 0:
            raise ValueError("Timeouts must be positive")
        if config.max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        for tool in ("bugsinpy-checkout", "bugsinpy-compile"):
            if not (self.dataset_root / "framework" / "bin" / tool).is_file():
                raise FileNotFoundError(f"Missing BugsInPy tool: {tool}")

    def run(self, cases: list[tuple[str, int]]) -> Path:
        if sys.platform != "linux":
            raise RuntimeError("Run BugsInPyRunner inside Linux, WSL, or Docker")
        if not cases or len(set(cases)) != len(cases):
            raise ValueError("Provide a nonempty list of unique (project, bug_id) cases")
        for project, bug_id in cases:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", project):
                raise ValueError(f"Invalid project: {project!r}")
            if not re.fullmatch(r"[1-9][0-9]*", str(bug_id)):
                raise ValueError(f"Invalid bug ID: {bug_id!r}")
        run_dir = self.output_root / (
            datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:8]
        )
        run_dir.mkdir(parents=True)
        report = {
            "schema_version": 1, "status": "running",
            "dataset_root": str(self.dataset_root),
            "config": asdict(self.config), "setup_timeout": self.setup_timeout,
            "evaluation_scope": "BugsInPy relevant tests, original test files preserved",
            "cases": [],
        }
        result_path = run_dir / "results.json"
        self._save(result_path, report)
        try:
            for project, bug_id in cases:
                entry = {"project": project, "bug_id": bug_id, "strategies": {}}
                report["cases"].append(entry)
                case_dir = run_dir / f"{project}_{bug_id}"
                for strategy in ("single_shot", "agent"):
                    print(f"{project}:{bug_id} {strategy}", flush=True)
                    entry["strategies"][strategy] = self._run_strategy(
                        project, bug_id, strategy, case_dir / strategy,
                    )
                    self._save(result_path, report)
            report["status"] = "completed"
        except KeyboardInterrupt:
            report["status"] = "interrupted"
            raise
        finally:
            report["summary"] = {
                strategy: {
                    "total": len(cases),
                    "evaluated": sum(
                        e["strategies"].get(strategy, {}).get("status") in
                        {"resolved", "unresolved"} for e in report["cases"]
                    ),
                    "resolved": sum(
                        e["strategies"].get(strategy, {}).get("status") == "resolved"
                        for e in report["cases"]
                    ),
                }
                for strategy in ("single_shot", "agent")
            }
            self._save(result_path, report)
        return result_path

    @staticmethod
    def _save(path: Path, report: dict) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        temporary.replace(path)

    def _prepare(self, project: str, bug_id: int, root: Path, version: int = 0):
        root.mkdir(parents=True)
        env = os.environ.copy()
        tools_dir = self.dataset_root / "framework" / "bin"
        env["PATH"] = str(tools_dir) + os.pathsep + env.get("PATH", "")
        setup = LoggedCommands(env, root / "setup_logs", self.setup_timeout)
        checkout = shlex.join([
            "bash", str(tools_dir / "bugsinpy-checkout"), "-p", project,
            "-i", str(bug_id), "-v", str(version), "-w", str(root / "checkout"),
        ])
        self._require(setup.run(checkout, self.dataset_root), "checkout_failed")
        repo = root / "checkout" / project
        if not (repo / "bugsinpy_bug.info").is_file():
            raise StageError("checkout_failed", f"No checkout metadata: {repo}")
        self._require(
            setup.run(shlex.join(["bash", str(tools_dir / "bugsinpy-compile")]), repo),
            "compile_failed",
        )
        python = repo / "env" / "bin" / "python"
        if not python.is_file() or not (repo / "bugsinpy_compile_flag").is_file():
            raise StageError("compile_failed", "Missing environment or compile flag")
        env["PATH"] = str(python.parent) + os.pathsep + env["PATH"]
        env["VIRTUAL_ENV"] = str(python.parent.parent)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        metadata = BugsInPyAdapter._read_info(repo / "bugsinpy_bug.info")
        paths = [repo]
        for raw in metadata.get("pythonpath", "").split(";"):
            if raw.strip():
                path = (repo / raw.strip()).resolve()
                if not path.is_relative_to(repo):
                    raise StageError("compile_failed", "pythonpath escapes checkout")
                paths.append(path)
        env["PYTHONPATH"] = os.pathsep.join(map(str, paths))
        commands = LoggedCommands(env, root / "test_logs", self.config.command_timeout_sec)
        adapter = BugsInPyAdapter(self.dataset_root, python_executable=str(python))
        test_command = adapter._test_command(
            self.dataset_root / "projects" / project / "bugs" / str(bug_id) / "run_test.sh"
        )
        case = adapter.to_case(
            project, bug_id, source_repo=repo, test_command=test_command,
        )
        return case, commands, metadata

    @staticmethod
    def _require(result: CommandResult, status: str) -> None:
        if not result.success:
            raise StageError(status, (result.stdout + result.stderr)[-4000:])

    def _run_strategy(self, project: str, bug_id: int, strategy: str, root: Path) -> dict:
        record = {"status": "preparing", "workspace": str(root)}
        started = time.monotonic()
        stage = "prepare"
        try:
            case, commands, metadata = self._prepare(project, bug_id, root / "repair")
            stage = "reproduce"
            reproduced = commands.run(case.test_command, case.source_repo)
            record["reproduction"] = asdict(reproduced)
            if reproduced.timeout or reproduced.exit_code != 1:
                raise StageError(
                    "not_reproduced" if reproduced.success else "reproduction_error",
                    "Expected a test failure with exit code 1; see reproduction output",
                )
            # A failing test alone could be a broken dependency. Require the
            # same relevant tests to pass in an independently compiled fixed tree.
            stage = "fixed_control"
            fixed, fixed_commands, _ = self._prepare(project, bug_id, root / "control", 1)
            control = fixed_commands.run(fixed.test_command, fixed.source_repo)
            record["fixed_control"] = asdict(control)
            self._require(control, "environment_error")
            stage = "workflow"
            workflow = self._workflow(strategy, root, commands)
            outcome = workflow.run(
                repo=case.source_repo, issue=case.issue, test_command=case.test_command,
            )
            record["workflow"] = asdict(outcome)
            record["cost"] = getattr(workflow, "last_cost_summary", {})
            patch_path = root / "candidate.patch"
            patch_path.write_text(outcome.diff, encoding="utf-8")
            if not outcome.diff.strip():
                record["status"] = "unresolved"
                return record
            stage = "evaluate"
            fresh, evaluator, fresh_metadata = self._prepare(project, bug_id, root / "evaluation")
            originals = {
                name.strip(): (fresh.source_repo / name.strip()).read_bytes()
                for name in fresh_metadata["test_file"].split(";") if name.strip()
            }
            apply_result = evaluator.run(
                shlex.join(["git", "apply", "--", str(patch_path)]), fresh.source_repo,
            )
            record["patch_apply"] = asdict(apply_result)
            if not apply_result.success:
                record["status"] = "unresolved"
                return record
            for name, content in originals.items():
                target = fresh.source_repo / name
                if not target.is_file() or target.read_bytes() != content:
                    raise StageError("invalid_patch", f"Patch modifies evaluation test: {name}")
            evaluated = evaluator.run(fresh.test_command, fresh.source_repo)
            record["evaluation"] = asdict(evaluated)
            record["status"] = "resolved" if evaluated.success else "unresolved"
        except Exception as exc:
            record["status"] = exc.status if isinstance(exc, StageError) else "runner_error"
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["stage"] = stage
        finally:
            record["duration_seconds"] = round(time.monotonic() - started, 4)
        return record

    def _workflow(self, strategy: str, root: Path, commands: LoggedCommands):
        config = replace(self.config, apply_patch=True, trace_dir=root / "traces")
        if self.workflow_factories is not None:
            workflow = self.workflow_factories[strategy](config)
        else:
            from repo_pilot.single_shot import SingleShotWorkflow
            from repo_pilot.workflow import BugfixWorkflow

            workflow = (SingleShotWorkflow if strategy == "single_shot" else BugfixWorkflow)(config)
        workflow.commands = commands
        if hasattr(workflow, "verifier"):
            workflow.verifier.commands = commands
        if hasattr(workflow, "scanner"):
            workflow.scanner.IGNORED_DIRS = workflow.scanner.IGNORED_DIRS | {"env"}
        if hasattr(workflow, "enabled_skills"):
            workflow.enabled_skills = set()
        return workflow


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("benchmark_runs/bugsinpy"))
    parser.add_argument("--case", action="append", required=True, metavar="PROJECT:BUG_ID")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--test-timeout", type=int, default=120)
    parser.add_argument("--setup-timeout", type=int, default=1800)
    args = parser.parse_args()
    try:
        cases = [(item.rsplit(":", 1)[0], int(item.rsplit(":", 1)[1])) for item in args.case]
    except (ValueError, IndexError):
        parser.error("--case must be PROJECT:BUG_ID")
    runner = BugsInPyRunner(
        args.dataset_root, args.output_root,
        RepoPilotConfig(
            provider=args.provider, model=args.model, max_iterations=args.max_iterations,
            command_timeout_sec=args.test_timeout,
        ),
        setup_timeout=args.setup_timeout,
    )
    print(runner.run(cases))


if __name__ == "__main__":
    main()
