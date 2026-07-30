from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

import repo_pilot.api as api_module


# 直接测试 FastAPI 应用，
# 不需要启动 Uvicorn。
client = TestClient(
    api_module.app
)


def test_repair_api_runs_real_workflow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """
    测试完整的同步 API 修复流程。

    与 test_api.py 不同，这里不替换 Workflow，
    而是真正运行：

    API
    → BugfixWorkflow
    → FakeProvider
    → Patcher
    → Verifier
    """

    # 找到项目中的故障示例仓库。
    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    source_repo = (
        project_root
        / "examples"
        / "buggy_calculator"
    )

    assert source_repo.exists(), (
        f"Example repository not found: "
        f"{source_repo}"
    )

    # 将示例复制到 pytest 临时目录。
    #
    # 测试只修改副本，
    # 不修改 examples 中的原始文件。
    repo = (
        tmp_path
        / "buggy_calculator"
    )

    shutil.copytree(
        source_repo,
        repo,
    )

    # 强制把 calculator.py 恢复成有 Bug 的版本。
    #
    # 即使 examples 中的文件之前已经被修复，
    # 当前集成测试仍然能够稳定运行。
    calculator_file = (
        repo
        / "calculator.py"
    )

    calculator_file.write_text(
        (
            "def divide(a,b):\n"
            "    return a / b\n"
        ),
        encoding="utf-8",
    )

    # API 只能访问 tmp_path 下面的仓库。
    monkeypatch.setenv(
        "REPOPILOT_ALLOWED_ROOT",
        str(tmp_path),
    )

    # Trace 和结果也保存到临时目录。
    monkeypatch.setenv(
        "REPOPILOT_TRACE_DIR",
        str(tmp_path / "runs"),
    )

    # 提交同步修复请求。
    response = client.post(
        "/repair",
        json={
            "repo": str(repo),
            "issue": (
                "divide by zero should "
                "raise ValueError"
            ),
            "test_command": (
                "python -m pytest -q"
            ),
            "provider": "fake",
            "model": "fake-model",
            "max_iterations": 2,
            "apply_patch": True,
            "command_timeout_sec": 120,
        },
    )

    # response.text 会在测试失败时显示
    # API 返回的具体错误信息。
    assert response.status_code == 200, (
        response.text
    )

    body = response.json()

    # 临时打印 API 返回的完整修复结果。
 

    assert body["success"] is True, body

    # 字段名必须是 iteration，
    # 不能写成 iterations。
    assert "iteration" in body

    assert body["iteration"] >= 1

    # 成功修复后应该产生代码差异。
    assert body["diff"]

    # 最终测试输出应该存在。
    assert body["test_output"]

    # 检查文件确实被修改。
    updated_source = (
        calculator_file.read_text(
            encoding="utf-8"
        )
    )

    assert "raise ValueError" in (
        updated_source
    )

    # 再独立执行一次 pytest，
    # 确认 API 返回成功不是误判。
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    test_output = (
        completed.stdout
        + completed.stderr
    )

    assert completed.returncode == 0, (
        test_output
    )