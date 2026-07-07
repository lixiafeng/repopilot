from dataclasses import dataclass
from pathlib import Path

@dataclass
class RepoPilotConfig:
    provider: str = "fake"
    model: str = "fake-model"
    apply_patch: bool = True
    max_iterations:  int = 2
    trace_dir: Path = Path("runs")
    command_timeout_sec: int = 30