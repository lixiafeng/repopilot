from __future__ import annotations

from pathlib import Path

from repo_pilot.skills import (
    GeneratedRegressionTest,
    RegressionTestSkill,
    SkillContext,
)
from repo_pilot.tools import CommandResult


class PassingGenerator:
    def generate(
        self,
        context: SkillContext,
    ) -> GeneratedRegressionTest:
        return GeneratedRegressionTest(
            path="tests/test_repopilot_regression.py",
            content=(
                "from calculator import add\n\n"
                "def test_regression_add():\n"
                "    assert add(2, 3) == 5\n"
            ),
            rationale="Protect the repaired addition behavior.",
        )


class FailingGenerator:
    def generate(
        self,
        context: SkillContext,
    ) -> GeneratedRegressionTest:
        return GeneratedRegressionTest(
            path="tests/test_repopilot_regression.py",
            content=(
                "from calculator import add\n\n"
                "def test_regression_add():\n"
                "    assert add(2, 3) == 999\n"
            ),
        )


class EscapingGenerator:
    def generate(
        self,
        context: SkillContext,
    ) -> GeneratedRegressionTest:
        return GeneratedRegressionTest(
            path="../test_escape.py",
            content="def test_escape():\n    assert True\n",
        )


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "calculator.py").write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    return repo


def test_regression_test_skill_runs_generated_test(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)

    skill = RegressionTestSkill(
        PassingGenerator(),
    )

    result = skill.run(
        SkillContext(
            repo_path=repo,
            issue="addition should work",
            diff="+ return a + b",
        )
    )

    assert result.success is True
    assert result.data["exit_code"] == 0
    assert result.data["test_path"] == (
        "tests/test_repopilot_regression.py"
    )

    assert not (
        repo
        / "tests"
        / "test_repopilot_regression.py"
    ).exists()


def test_regression_test_skill_reports_failure(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)

    skill = RegressionTestSkill(
        FailingGenerator(),
    )

    result = skill.run(
        SkillContext(
            repo_path=repo,
            issue="addition should work",
        )
    )

    assert result.success is False
    assert result.data["exit_code"] != 0


def test_regression_test_skill_blocks_path_escape(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)

    skill = RegressionTestSkill(
        EscapingGenerator(),
    )

    result = skill.run(
        SkillContext(
            repo_path=repo,
            issue="test",
        )
    )

    assert result.success is False
    assert "escapes" in result.message


class ExitCodeCommands:
    def __init__(self, exit_code: int) -> None:
        self.exit_code = exit_code

    def run(self, command: str, cwd: Path) -> CommandResult:
        return CommandResult(
            command=command,
            exit_code=self.exit_code,
            stdout="pytest output",
            stderr="",
            duration_seconds=0.01,
        )


def test_regression_test_skill_distinguishes_test_and_execution_failures(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)

    assertion_failure = RegressionTestSkill(
        PassingGenerator(),
        commands=ExitCodeCommands(1),
    ).run(SkillContext(repo_path=repo, issue="test"))
    collection_error = RegressionTestSkill(
        PassingGenerator(),
        commands=ExitCodeCommands(2),
    ).run(SkillContext(repo_path=repo, issue="test"))

    assert assertion_failure.data["failure_kind"] == "test_failure"
    assert collection_error.data["failure_kind"] == "execution_error"
