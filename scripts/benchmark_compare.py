import argparse
import json
from pathlib import Path

from repo_pilot.benchmark import EvalRunner
from repo_pilot.benchmark_cases import build_default_cases
from repo_pilot.config import RepoPilotConfig
from repo_pilot.single_shot import SingleShotWorkflow
from repo_pilot.workflow import BugfixWorkflow


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "benchmark_runs"


def build_config() -> RepoPilotConfig:
    """两种 strategy 必须使用完全相同的模型和基础配置。"""
    return RepoPilotConfig(
        provider="deepseek",
        model="deepseek-chat",
        max_iterations=3,
        apply_patch=True,
        command_timeout_sec=120,
    )


def make_context_single_shot() -> SingleShotWorkflow:
    return SingleShotWorkflow(
        config=build_config(),
    )


def make_agent() -> BugfixWorkflow:
    return BugfixWorkflow(
        config=build_config(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare context-aware single-shot "
            "with RepoPilot Agent."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Only run the first N benchmark cases. "
            "Use --limit 1 for a cheap smoke test."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = build_default_cases(PROJECT_ROOT)

    if args.limit is not None:
        if args.limit <= 0:
            raise ValueError(
                "--limit must be greater than 0."
            )
        cases = cases[:args.limit]

    if not cases:
        raise ValueError(
            "No benchmark cases were selected."
        )

    single_runner = EvalRunner(
        workflow_factory=make_context_single_shot,
        output_root=(
            OUTPUT_ROOT
            / "context_single_shot"
        ),
        strategy="context_single_shot",
    )

    agent_runner = EvalRunner(
        workflow_factory=make_agent,
        output_root=OUTPUT_ROOT / "agent",
        strategy="agent",
    )

    print()
    print("===== CONTEXT SINGLE SHOT =====")
    single_report = single_runner.run(cases)

    print()
    print("===== REPOPILOT AGENT =====")
    agent_report = agent_runner.run(cases)

    single = single_report.summary
    agent = agent_report.summary

    comparison = {
        "total_cases": len(cases),
        "context_single_shot": {
            "passed_cases": single["passed_cases"],
            "pass_rate": single["pass_rate"],
            "average_iteration": single["average_iteration"],
            "average_duration_seconds": single[
                "average_duration_seconds"
            ],
            "average_model_calls": single[
                "average_model_calls"
            ],
            "average_tokens": single["average_tokens"],
            "average_estimated_cost": single[
                "average_estimated_cost"
            ],
        },
        "agent": {
            "passed_cases": agent["passed_cases"],
            "pass_rate": agent["pass_rate"],
            "average_iteration": agent["average_iteration"],
            "average_duration_seconds": agent[
                "average_duration_seconds"
            ],
            "average_model_calls": agent[
                "average_model_calls"
            ],
            "average_tokens": agent["average_tokens"],
            "average_estimated_cost": agent[
                "average_estimated_cost"
            ],
        },
    }

    comparison["delta"] = {
        "pass_rate": round(
            agent["pass_rate"]
            - single["pass_rate"],
            4,
        ),
        "average_duration_seconds": round(
            agent["average_duration_seconds"]
            - single["average_duration_seconds"],
            4,
        ),
        "average_model_calls": round(
            agent["average_model_calls"]
            - single["average_model_calls"],
            2,
        ),
        "average_tokens": round(
            agent["average_tokens"]
            - single["average_tokens"],
            2,
        ),
        "average_estimated_cost": round(
            agent["average_estimated_cost"]
            - single["average_estimated_cost"],
            8,
        ),
    }

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    comparison_path = (
        OUTPUT_ROOT / "comparison.json"
    )
    comparison_path.write_text(
        json.dumps(
            comparison,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("===== COMPARISON =====")
    print(
        "Context single-shot:",
        f"{single['passed_cases']}/{single['total_cases']}",
        f"({single['pass_rate']:.2%})",
    )
    print(
        "RepoPilot Agent:",
        f"{agent['passed_cases']}/{agent['total_cases']}",
        f"({agent['pass_rate']:.2%})",
    )

    print()
    print(
        "Context single-shot avg calls:",
        single["average_model_calls"],
    )
    print(
        "RepoPilot avg calls:",
        agent["average_model_calls"],
    )

    print()
    print(
        "Context single-shot avg tokens:",
        single["average_tokens"],
    )
    print(
        "RepoPilot avg tokens:",
        agent["average_tokens"],
    )

    print()
    print(
        "Context single-shot avg cost:",
        single["average_estimated_cost"],
    )
    print(
        "RepoPilot avg cost:",
        agent["average_estimated_cost"],
    )

    print()
    print(
        "Context single-shot avg duration:",
        single["average_duration_seconds"],
    )
    print(
        "RepoPilot avg duration:",
        agent["average_duration_seconds"],
    )

    print()
    print(
        "Comparison saved to:",
        comparison_path,
    )


if __name__ == "__main__":
    main()
