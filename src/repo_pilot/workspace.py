from __future__ import annotations

import shutil
from pathlib import Path


class WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def create(
        self,
        *,
        task_id: int,
        source_repo: Path,
    ) -> Path:
        source_repo = source_repo.resolve()

        if not source_repo.exists():
            raise FileNotFoundError(
                f"Repository does not exist: {source_repo}"
            )

        if not source_repo.is_dir():
            raise ValueError(
                f"Repository is not a directory: {source_repo}"
            )

        workspace = (
            self.root / f"task-{task_id}"
        ).resolve()

        # 防止旧任务残留影响当前执行。
        if workspace.exists():
            shutil.rmtree(workspace)

        shutil.copytree(
            source_repo,
            workspace,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
                ".venv",
                "venv",
            ),
        )

        return workspace

    def remove(
        self,
        workspace: Path,
    ) -> None:
        workspace = workspace.resolve()

        # 基础安全检查：
        # 绝不能删除 workspace root 之外的目录。
        if self.root not in workspace.parents:
            raise ValueError(
                f"Refusing to remove path outside workspace root: "
                f"{workspace}"
            )

        if workspace.exists():
            shutil.rmtree(workspace)