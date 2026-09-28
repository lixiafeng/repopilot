import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from repo_pilot.provider import ModelResponse


@dataclass
class CostRecord:
    call_name: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float


class CostTracker:
    def __init__(self) -> None:
        self.records: list[CostRecord] = []

    def record(
        self,
        call_name: str,
        response: ModelResponse,
    ) -> None:
        self.record_usage(
            call_name=call_name,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            estimated_cost=response.estimated_cost,
        )

    def record_usage(
        self,
        call_name: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float = 0.0,
    ) -> None:
        """
        Record token/cost information when a component does not
        directly expose the original ModelResponse.

        This is useful for optional Skills that return aggregated
        execution metadata through SkillResult.
        """

        record = CostRecord(
            call_name=call_name,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            estimated_cost=float(
                estimated_cost
            ),
        )

        self.records.append(record)

    def summary(self) -> dict[str, Any]:
        total_input_tokens = sum(
            record.input_tokens
            for record in self.records
        )

        total_output_tokens = sum(
            record.output_tokens
            for record in self.records
        )

        total_cost = sum(
            record.estimated_cost
            for record in self.records
        )

        return {
            "calls": len(self.records),
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "estimated_cost": round(
                total_cost,
                8,
            ),
            "records": [
                asdict(record)
                for record in self.records
            ],
        }

    def save(
        self,
        run_dir: Path,
    ) -> Path:
        cost_path = run_dir / "cost.json"

        cost_path.write_text(
            json.dumps(
                self.summary(),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return cost_path