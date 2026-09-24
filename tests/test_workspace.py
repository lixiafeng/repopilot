from pathlib import Path

from repo_pilot.workspace import WorkspaceManager


def test_workspace_isolated_from_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()

    source_file = source / "calculator.py"
    source_file.write_text(
        "value = 1\n",
        encoding="utf-8",
    )

    manager = WorkspaceManager(
        tmp_path / "workspaces"
    )

    workspace = manager.create(
        task_id=1,
        source_repo=source,
    )

    workspace_file = (
        workspace / "calculator.py"
    )

    assert workspace_file.exists()

    workspace_file.write_text(
        "value = 999\n",
        encoding="utf-8",
    )

    assert source_file.read_text(
        encoding="utf-8"
    ) == "value = 1\n"

    assert workspace_file.read_text(
        encoding="utf-8"
    ) == "value = 999\n"