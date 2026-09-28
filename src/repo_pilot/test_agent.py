from __future__ import annotations

from pathlib import Path

from repo_pilot.provider import Provider
from repo_pilot.skills import (
    ProviderRegressionTestGenerator,
    RegressionTestSkill,
    SkillContext,
    SkillResult,
)
from repo_pilot.tools import CommandTools


class TestAgent:
    """Generate and run a focused regression test for a candidate repair."""

    def __init__(
        self,
        provider: Provider,
        commands: CommandTools | None = None,
        *,
        timeout_seconds: int = 60,
    ) -> None:
        self._skill = RegressionTestSkill(
            generator=ProviderRegressionTestGenerator(provider=provider),
            commands=commands,
            timeout_seconds=timeout_seconds,
        )

    @property
    def commands(self) -> CommandTools:
        return self._skill.commands

    @commands.setter
    def commands(self, value: CommandTools) -> None:
        self._skill.commands = value

    def run(
        self,
        *,
        repo_path: Path,
        issue: str,
        diff: str,
        test_command: str,
    ) -> SkillResult:
        return self._skill.run(
            SkillContext(
                repo_path=repo_path,
                issue=issue,
                diff=diff,
                test_command=test_command,
            )
        )
