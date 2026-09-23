from __future__ import annotations

import os
from pathlib import Path

from repo_pilot.config import RepoPilotConfig
from repo_pilot.workflow import BugfixWorkflow


def resolve_repo_path(repo_text: str) -> Path:
    allowed_root = Path(
        os.getenv("REPOPILOT_ALLOWED_ROOT", ".")
    ).expanduser().resolve()

    repo = Path(repo_text).expanduser().resolve()

    if not repo.exists():
        raise FileNotFoundError(f"Repository does not exist: {repo}")
    if not repo.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {repo}")

    try:
        repo.relative_to(allowed_root)
    except ValueError as exc:
        raise PermissionError(
            "Repository is outside REPOPILOT_ALLOWED_ROOT. "
            f"Allowed root: {allowed_root}"
        ) from exc

    return repo


def create_workflow(
    *,
    provider: str,
    model: str,
    max_iterations: int,
    apply_patch: bool,
    command_timeout_sec: int,
) -> BugfixWorkflow:
    trace_dir = Path(
        os.getenv("REPOPILOT_TRACE_DIR", "runs")
    ).expanduser().resolve()
    trace_dir.mkdir(parents=True, exist_ok=True)

    config = RepoPilotConfig(
        provider=provider,
        model=model,
        max_iterations=max_iterations,
        apply_patch=apply_patch,
        command_timeout_sec=command_timeout_sec,
        trace_dir=trace_dir,
    )
    return BugfixWorkflow(config=config)
