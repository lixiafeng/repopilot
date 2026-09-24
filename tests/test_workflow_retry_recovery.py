from pathlib import Path

import repo_pilot.workflow as workflow_module

from repo_pilot.config import RepoPilotConfig
from repo_pilot.provider import ModelResponse
from repo_pilot.workflow import BugfixWorkflow


class RetrySequenceProvider:
    """
    一个确定性的测试 Provider：

    第一次生成错误 Patch：
        ValueError 写成 RuntimeError

    第二次生成正确 Patch：
        改成 ValueError

    用于验证：
        verification failed
        -> rollback
        -> retry
        -> success
    """

    def __init__(self) -> None:
        self.patch_calls = 0

    def complete(self, prompt: str) -> ModelResponse:

        if "TASK: CREATE_REPAIR_PLAN" in prompt:
            return ModelResponse(
                content="""
{
  "root_cause_hypothesis": "divide does not explicitly handle zero",
  "files_to_inspect": [
    "calculator.py",
    "tests/test_calculator.py"
  ],
  "files_to_modify": [
    "calculator.py"
  ],
  "patch_strategy": "check b before performing division",
  "verification_commands": [
    "python -m pytest -q"
  ],
  "risks": [
    "normal division behavior must remain unchanged"
  ]
}
""".strip(),
                input_tokens=20,
                output_tokens=10,
                estimated_cost=0.0,
            )

        if "TASK: CREATE_JSON_PATCH" in prompt:
            self.patch_calls += 1

            # 第一轮：故意生成一个“能应用但测试过不了”的 Patch
            if self.patch_calls == 1:
                return ModelResponse(
                    content="""
{
  "operations": [
    {
      "type": "replace_text",
      "path": "calculator.py",
      "old": "def divide(a,b):\\n    return a / b\\n",
      "new": "def divide(a,b):\\n    if b == 0:\\n        raise RuntimeError('Division by zero')\\n    return a / b\\n"
    }
  ],
  "notes": "Deliberately incorrect first attempt."
}
""".strip(),
                    input_tokens=20,
                    output_tokens=10,
                    estimated_cost=0.0,
                )

            # 第二轮：生成正确 Patch
            return ModelResponse(
                content="""
{
  "operations": [
    {
      "type": "replace_text",
      "path": "calculator.py",
      "old": "def divide(a,b):\\n    return a / b\\n",
      "new": "def divide(a,b):\\n    if b == 0:\\n        raise ValueError('Division by zero')\\n    return a / b\\n"
    }
  ],
  "notes": "Correct repair after failed verification."
}
""".strip(),
                input_tokens=20,
                output_tokens=10,
                estimated_cost=0.0,
            )

        return ModelResponse(
            content="ok",
            input_tokens=1,
            output_tokens=1,
            estimated_cost=0.0,
        )


def test_workflow_retry_and_rollback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    tests_dir = repo / "tests"

    repo.mkdir()
    tests_dir.mkdir()

    # 创建故障代码
    calculator = repo / "calculator.py"
    calculator.write_text(
        "def divide(a,b):\n"
        "    return a / b\n",
        encoding="utf-8",
    )

    # 创建测试
    test_file = tests_dir / "test_calculator.py"
    test_file.write_text(
        "import pytest\n"
        "\n"
        "from calculator import divide\n"
        "\n"
        "\n"
        "def test_normal_division():\n"
        "    assert divide(6, 2) == 3\n"
        "\n"
        "\n"
        "def test_divide_by_zero_raises_value_error():\n"
        "    with pytest.raises(ValueError):\n"
        "        divide(1, 0)\n",
        encoding="utf-8",
    )

    provider = RetrySequenceProvider()

    # BugfixWorkflow 初始化时会调用 create_provider。
    # 测试中替换成我们的确定性 Provider。
    monkeypatch.setattr(
        workflow_module,
        "create_provider",
        lambda provider_name, model: provider,
    )

    config = RepoPilotConfig(
        provider="fake",
        model="retry-test",
        apply_patch=True,
        max_iterations=2,
        trace_dir=tmp_path / "runs",
        command_timeout_sec=30,
    )

    workflow = BugfixWorkflow(config=config)

    result = workflow.run(
        repo=repo,
        issue="divide by zero should raise ValueError",
        test_command="python -m pytest -q",
    )

    # 最终应该修复成功
    assert result.success is True

    # 必须是第二轮才成功
    assert result.iteration == 2

    # Provider 必须生成了两次 Patch
    assert provider.patch_calls == 2

    final_code = calculator.read_text(encoding="utf-8")

    # 最终留下正确 Patch
    assert "raise ValueError" in final_code

    # 第一轮错误 Patch 必须被 rollback 掉
    assert "raise RuntimeError" not in final_code