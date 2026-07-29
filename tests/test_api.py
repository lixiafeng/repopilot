from pathlib import Path

from fastapi.testclient import TestClient

import repo_pilot.api as api_module
from repo_pilot.api import app
from repo_pilot.result import WorkflowResult


client = TestClient(app)


class DummyWorkflow:
    """API 测试使用的假 Workflow。"""

    def run(
        self,
        repo: Path,
        issue: str,
        test_command: str,
    ) -> WorkflowResult:
        # 验证 API 确实把参数传给了 Workflow。
        assert repo.exists()
        assert issue == "fix test bug"
        assert (
            test_command
            == "python -m pytest -q"
        )

        # 返回固定结果，不调用模型，也不修改文件。
        return WorkflowResult(
            success=True,
            message="dummy repair succeeded",
            iteration=1,
            diff="dummy diff",
            test_output="dummy tests passed",
        )


def test_health_endpoint() -> None:
    """健康检查应返回 HTTP 200。"""

    response = client.get(
        "/health"
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok",
    }


def test_repair_endpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """POST /repair 应运行 Workflow 并返回结果。"""

    # 创建一个临时仓库目录。
    repo = tmp_path / "repo"

    repo.mkdir()

    # 允许 API 访问本测试的临时目录。
    monkeypatch.setenv(
        "REPOPILOT_ALLOWED_ROOT",
        str(tmp_path),
    )

    # 把真正的 create_workflow 替换成假函数。
    #
    # 因此测试不会调用 FakeProvider 或真实模型。
    monkeypatch.setattr(
        api_module,
        "create_workflow",
        lambda request: DummyWorkflow(),
    )

    response = client.post(
        "/repair",
        json={
            "repo": str(repo),
            "issue": "fix test bug",
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

    assert response.status_code == 200

    assert response.json() == {
        "success": True,
        "message": "dummy repair succeeded",
        "iteration": 1,
        "diff": "dummy diff",
        "test_output": "dummy tests passed",
    }


def test_repair_rejects_missing_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """仓库不存在时应返回 HTTP 404。"""

    monkeypatch.setenv(
        "REPOPILOT_ALLOWED_ROOT",
        str(tmp_path),
    )

    missing_repo = (
        tmp_path
        / "missing_repo"
    )

    response = client.post(
        "/repair",
        json={
            "repo": str(missing_repo),
            "issue": "fix test bug",
        },
    )

    assert response.status_code == 404

    assert (
        "Repository does not exist"
        in response.json()["detail"]
    )


def test_repair_rejects_repo_outside_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """允许目录外部的仓库应被拒绝。"""

    allowed_root = (
        tmp_path
        / "allowed"
    )

    outside_repo = (
        tmp_path
        / "outside"
    )

    allowed_root.mkdir()
    outside_repo.mkdir()

    monkeypatch.setenv(
        "REPOPILOT_ALLOWED_ROOT",
        str(allowed_root),
    )

    response = client.post(
        "/repair",
        json={
            "repo": str(outside_repo),
            "issue": "fix test bug",
        },
    )

    assert response.status_code == 403

    assert (
        "outside REPOPILOT_ALLOWED_ROOT"
        in response.json()["detail"]
    )