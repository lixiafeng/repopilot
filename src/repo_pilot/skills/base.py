from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SkillContext:
    """Runtime context shared with an optional RepoPilot skill."""

    repo_path: Path
    issue: str
    diff: str | None = None
    test_command: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkillResult:
    """Standardized result returned by every skill."""

    name: str
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class Skill(ABC):
    """Base interface for pluggable RepoPilot skills."""

    name: str

    @abstractmethod
    def run(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError
