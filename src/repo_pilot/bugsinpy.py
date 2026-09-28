"""Adapt locally prepared BugsInPy checkouts to RepoPilot benchmarks."""

import os
import re
import shlex
import subprocess
from pathlib import Path

from repo_pilot.benchmark import BenchmarkCase


class BugsInPyAdapter:
    """Read a BugsInPy dataset clone without downloading or changing repositories.

    ``source_repo`` must be a buggy checkout prepared with BugsInPy's tools,
    including its regression tests. Its dependencies must already be installed.
    Test commands run relative to EvalRunner's temporary repository copy.
    """

    def __init__(
        self, dataset_root: Path, *, python_executable: str = "python"
    ) -> None:
        self.dataset_root = Path(dataset_root).resolve()
        if not (self.dataset_root / "projects").is_dir():
            raise FileNotFoundError(
                f"BugsInPy projects directory not found: {self.dataset_root / 'projects'}"
            )
        if not python_executable.strip():
            raise ValueError("python_executable must not be empty")
        self.python_executable = python_executable

    def to_case(
        self,
        project: str,
        bug_id: int | str,
        *,
        source_repo: Path,
        issue: str | None = None,
        test_command: str | None = None,
    ) -> BenchmarkCase:
        """Convert one bug; explicit commands support nonstandard test scripts.

        An override must return a nonzero exit code on failure and operate on
        the current directory, not on the original checkout. No gold patch or
        fixed-commit information is included in the generated issue.
        """
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", project):
            raise ValueError(f"Invalid BugsInPy project name: {project!r}")
        if not re.fullmatch(r"[1-9][0-9]*", str(bug_id)):
            raise ValueError("bug_id must be a positive integer")
        bug_dir = (
            self.dataset_root / "projects" / project / "bugs" / str(bug_id)
        ).resolve()
        if not bug_dir.is_relative_to(self.dataset_root):
            raise ValueError("Bug metadata directory escapes the dataset root")
        metadata = self._read_info(bug_dir / "bug.info")
        for key in ("python_version", "buggy_commit_id", "test_file"):
            if not metadata.get(key):
                raise ValueError(f"Missing {key!r} in {bug_dir / 'bug.info'}")

        repo = Path(source_repo).resolve()
        if not repo.is_dir():
            raise FileNotFoundError(f"Prepared BugsInPy checkout not found: {repo}")
        compile_flag = repo / "bugsinpy_compile_flag"
        if not compile_flag.is_file():
            raise FileNotFoundError(
                f"BugsInPy compile flag missing or not a file: {compile_flag}. "
                "Run bugsinpy-compile in the checkout before converting this case."
            )
        for test_file in metadata["test_file"].split(";"):
            if not test_file.strip():
                continue
            target = (repo / test_file.strip()).resolve()
            if not target.is_relative_to(repo):
                raise ValueError(f"Test file escapes the checkout: {test_file}")
            if not target.is_file():
                raise FileNotFoundError(
                    f"BugsInPy regression test missing from checkout: {target}"
                )
        # Official checkout copies this file. If present, catch accidental
        # pairing of a checkout with a different bug's metadata.
        checkout_info = repo / "bugsinpy_bug.info"
        if checkout_info.exists():
            checkout_metadata = self._read_info(checkout_info)
            for key in ("buggy_commit_id", "test_file", "python_version"):
                if checkout_metadata.get(key) != metadata[key]:
                    raise ValueError(f"Checkout metadata differs for {key!r}: {repo}")

        if issue is None:
            issue = (
                f"Fix BugsInPy {project} bug {bug_id}. "
                "Reproduce the failure using the supplied test command, repair "
                "the implementation, and preserve existing behavior. "
                "Do not remove or weaken tests."
            )
        if not issue.strip():
            raise ValueError("issue must not be empty")
        if test_command is None:
            if metadata.get("pythonpath"):
                raise ValueError(
                    "This case requires a custom pythonpath; provide an explicit "
                    "test_command that sets PYTHONPATH relative to the working copy"
                )
            test_command = self._test_command(bug_dir / "run_test.sh")
        if not test_command.strip():
            raise ValueError("test_command must not be empty")
        return BenchmarkCase(
            name=f"bugsinpy_{project}_{bug_id}",
            source_repo=repo,
            issue=issue,
            test_command=test_command,
        )

    @staticmethod
    def _read_info(path: Path) -> dict[str, str]:
        """Parse key/value data, never source metadata as shell code."""
        values = {}
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator:
                raise ValueError(f"Invalid metadata at {path}:{number}")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value
        return values

    def _test_command(self, path: Path) -> str:
        commands = []
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            tokens = shlex.split(line, comments=True)
            if not tokens:
                continue
            # Only translate simple test invocations. Never silently discard
            # setup, pipelines, environment assignments, or shell expansion.
            if any(character in line for character in "$`;&|<>\\"):
                raise ValueError(
                    f"Unsupported shell syntax at {path}:{number}; "
                    "provide an explicit test_command"
                )
            if tokens[0] in {"pytest", "py.test"}:
                tokens = [self.python_executable, "-m", "pytest", *tokens[1:]]
            elif (
                tokens[0] in {"python", "python3"}
                and len(tokens) >= 3
                and tokens[1] == "-m"
                and tokens[2] in {"pytest", "unittest"}
            ):
                tokens[0] = self.python_executable
            else:
                raise ValueError(
                    f"Unsupported test invocation at {path}:{number}; "
                    "provide an explicit test_command"
                )
            commands.append(
                subprocess.list2cmdline(tokens) if os.name == "nt" else shlex.join(tokens)
            )
        if not commands:
            raise ValueError(f"No test commands found in {path}")
        # Both cmd.exe and POSIX shells stop at the first failed test command.
        return " && ".join(commands)
