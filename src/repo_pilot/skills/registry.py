from __future__ import annotations

from collections.abc import Iterable

from repo_pilot.skills.base import Skill, SkillContext, SkillResult


class SkillRegistry:
    """Registry that decouples optional skills from the core repair loop."""

    def __init__(self, skills: Iterable[Skill] | None = None) -> None:
        self._skills: dict[str, Skill] = {}

        for skill in skills or ():
            self.register(skill)

    def register(self, skill: Skill) -> None:
        name = skill.name.strip()

        if not name:
            raise ValueError("Skill name must not be empty.")

        if name in self._skills:
            raise ValueError(f"Skill already registered: {name}")

        self._skills[name] = skill

    def unregister(self, name: str) -> None:
        self._skills.pop(name, None)

    def get(self, name: str) -> Skill:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"Skill not found: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._skills)

    def run(self, name: str, context: SkillContext) -> SkillResult:
        return self.get(name).run(context)
