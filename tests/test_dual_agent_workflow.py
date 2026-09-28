import json
from pathlib import Path

import repo_pilot.workflow as workflow_module
from repo_pilot.config import RepoPilotConfig
from repo_pilot.provider import ModelResponse
from repo_pilot.skills import SkillResult
from repo_pilot.workflow import BugfixWorkflow


class RepairProvider:
    def __init__(self) -> None:
        self.patch_calls = 0
        self.second_plan_received_test_feedback = False

    def complete(self, prompt: str) -> ModelResponse:
        if "TASK: CREATE_REPAIR_PLAN" in prompt:
            if self.patch_calls == 1:
                self.second_plan_received_test_feedback = (
                    "test_regression_divide" in prompt
                    and "assert divide(6, 2) == 999" in prompt
                )
            return ModelResponse(
                content=json.dumps(
                    {
                        "root_cause_hypothesis": "zero is not handled",
                        "files_to_inspect": ["calculator.py"],
                        "files_to_modify": ["calculator.py"],
                        "patch_strategy": "raise ValueError for zero",
                        "verification_commands": ["python -m pytest -q"],
                        "risks": [],
                    }
                )
            )
        if "TASK: CREATE_JSON_PATCH" in prompt:
            self.patch_calls += 1
            return ModelResponse(
                content=json.dumps(
                    {
                        "operations": [
                            {
                                "type": "replace_text",
                                "path": "calculator.py",
                                "old": "def divide(a, b):\n    return a / b\n",
                                "new": (
                                    "def divide(a, b):\n"
                                    "    if b == 0:\n"
                                    "        raise ValueError('zero')\n"
                                    "    return a / b\n"
                                ),
                            }
                        ],
                        "notes": "repair",
                    }
                )
            )
        raise AssertionError(f"Unexpected prompt: {prompt[:80]}")


class SequencedTestAgent:
    def __init__(self) -> None:
        self.calls = 0
        self.commands = None

    def run(self, **kwargs) -> SkillResult:
        self.calls += 1
        if self.calls == 1:
            return SkillResult(
                name="regression_test",
                success=False,
                message="Generated regression test failed.",
                data={
                    "failure_kind": "test_failure",
                    "test_path": "tests/test_generated.py",
                    "test_content": (
                        "def test_regression_divide():\n"
                        "    assert divide(6, 2) == 999\n"
                    ),
                    "output": "FAILED tests/test_generated.py::test_regression_divide",
                },
            )
        return SkillResult(
            name="regression_test",
            success=True,
            message="Generated regression test passed.",
            data={"failure_kind": None, "output": "1 passed"},
        )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "calculator.py").write_text(
        "def divide(a, b):\n    return a / b\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_calculator.py").write_text(
        "import pytest\n"
        "from calculator import divide\n\n"
        "def test_zero():\n"
        "    with pytest.raises(ValueError):\n"
        "        divide(1, 0)\n",
        encoding="utf-8",
    )
    return repo


def test_test_agent_failure_rolls_back_and_feeds_next_repair(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = RepairProvider()
    monkeypatch.setattr(
        workflow_module,
        "create_provider",
        lambda provider_name, model: provider,
    )
    workflow = BugfixWorkflow(
        RepoPilotConfig(
            test_agent_enabled=True,
            max_iterations=2,
            trace_dir=tmp_path / "runs",
        )
    )
    test_agent = SequencedTestAgent()
    workflow.test_agent = test_agent

    result = workflow.run(
        repo=_repo(tmp_path),
        issue="divide by zero should raise ValueError",
        test_command="python -m pytest -q",
    )

    assert result.success is True
    assert result.iteration == 2
    assert test_agent.calls == 2
    assert provider.patch_calls == 2
    assert provider.second_plan_received_test_feedback is True


def test_test_agent_generation_error_rejects_and_rolls_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider = RepairProvider()
    monkeypatch.setattr(
        workflow_module,
        "create_provider",
        lambda provider_name, model: provider,
    )
    repo = _repo(tmp_path)
    original = (repo / "calculator.py").read_text(encoding="utf-8")
    workflow = BugfixWorkflow(
        RepoPilotConfig(
            test_agent_enabled=True,
            max_iterations=2,
            trace_dir=tmp_path / "runs",
        )
    )
    workflow.test_agent = type(
        "BrokenTestAgent",
        (),
        {
            "run": lambda self, **kwargs: SkillResult(
                name="regression_test",
                success=False,
                message="Failed to generate regression test: invalid JSON",
                data={"failure_kind": "generation_error"},
            )
        },
    )()

    result = workflow.run(
        repo=repo,
        issue="divide by zero should raise ValueError",
        test_command="python -m pytest -q",
    )

    assert result.success is False
    assert "Test Agent failed" in result.message
    assert (repo / "calculator.py").read_text(encoding="utf-8") == original
