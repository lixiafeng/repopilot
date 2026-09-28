import json
from pathlib import Path

from repo_pilot.provider import ModelResponse
from repo_pilot.test_agent import TestAgent as RepoPilotTestAgent


class RegressionProvider:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> ModelResponse:
        self.prompts.append(prompt)
        return ModelResponse(
            content=json.dumps(
                {
                    "path": "tests/test_generated_regression.py",
                    "content": (
                        "from calculator import add\n\n"
                        "def test_generated_regression():\n"
                        "    assert add(2, 3) == 5\n"
                    ),
                    "rationale": "Protect addition behavior.",
                }
            ),
            input_tokens=12,
            output_tokens=8,
            estimated_cost=0.001,
        )


def test_test_agent_generates_runs_and_removes_temporary_test(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    provider = RegressionProvider()
    agent = RepoPilotTestAgent(provider=provider)

    result = agent.run(
        repo_path=repo,
        issue="addition returned the wrong result",
        diff="--- a/calculator.py\n+++ b/calculator.py",
        test_command="python -m pytest -q",
    )

    generated = repo / "tests" / "test_generated_regression.py"
    assert result.success is True
    assert result.data["test_path"] == "tests/test_generated_regression.py"
    assert result.data["model_calls"] == 1
    assert result.data["test_content"].startswith("from calculator import add")
    assert not generated.exists()
    assert len(provider.prompts) == 1
    assert "TASK: GENERATE_REGRESSION_TEST" in provider.prompts[0]
