from __future__ import annotations

from pathlib import Path

import pytest

from repo_pilot.skills import (
    Skill,
    SkillContext,
    SkillRegistry,
    SkillResult,
)


class EchoSkill(Skill):
    name = "echo"

    def run(self, context: SkillContext) -> SkillResult:
        return SkillResult(
            name=self.name,
            success=True,
            message=context.issue,
        )


def test_registry_registers_and_runs_skill(tmp_path: Path) -> None:
    registry = SkillRegistry()
    registry.register(EchoSkill())

    result = registry.run(
        "echo",
        SkillContext(
            repo_path=tmp_path,
            issue="fix the bug",
        ),
    )

    assert registry.names() == ["echo"]
    assert result.success is True
    assert result.message == "fix the bug"


def test_registry_rejects_duplicate_skill() -> None:
    registry = SkillRegistry([EchoSkill()])

    with pytest.raises(
        ValueError,
        match="already registered",
    ):
        registry.register(EchoSkill())


def test_registry_raises_for_unknown_skill() -> None:
    registry = SkillRegistry()

    with pytest.raises(
        KeyError,
        match="Skill not found",
    ):
        registry.get("missing")
