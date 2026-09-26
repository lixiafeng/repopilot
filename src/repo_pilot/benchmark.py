import json
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Protocol

from repo_pilot.result import WorkflowResult


@dataclass(frozen=True)
class BenchmarkCase:
    """描述一个需要 RepoPilot 修复的评测案例。"""

    name: str
    source_repo: Path
    issue: str
    test_command: str = "python -m pytest -q"


@dataclass
class BenchmarkCaseResult:
    """保存一个评测案例的最终运行结果。"""

    # 保留原有字段在前，保证旧代码手动构造时尽量兼容。
    name: str
    success: bool
    iteration: int
    message: str
    duration_seconds: float
    diff: str
    test_output: str
    source_repo: str

    # Benchmark V2 新增指标。
    strategy: str = "agent"
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0


@dataclass
class EvalReport:
    """EvalRunner.run() 返回的评测报告。"""

    run_dir: Path
    summary: dict


class WorkflowLike(Protocol):
    """EvalRunner 对 Workflow 的最低要求。"""

    def run(
        self,
        repo: Path,
        issue: str,
        test_command: str,
    ) -> WorkflowResult:
        ...


class EvalRunner:
    """运行多个 BenchmarkCase，并统计评测结果。"""

    def __init__(
        self,
        workflow_factory: Callable[[], WorkflowLike],
        output_root: Path,
        strategy: str = "agent",
    ) -> None:
        self.workflow_factory = workflow_factory
        self.output_root = output_root
        self.strategy = strategy

    def run(
        self,
        cases: list[BenchmarkCase],
    ) -> EvalReport:
        """依次运行所有案例，并生成汇总结果。"""

        run_name = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        run_dir = self.output_root / run_name
        run_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        case_results: list[BenchmarkCaseResult] = []
        eval_started_at = time.perf_counter()

        for case in cases:
            print()
            print(
                f"===== Benchmark case: "
                f"{case.name} ====="
            )

            case_result = self._run_case(
                case=case,
            )

            case_results.append(case_result)

            print(
                f"Case success: "
                f"{case_result.success}"
            )
            print(
                f"Case iteration: "
                f"{case_result.iteration}"
            )
            print(
                f"Model calls: "
                f"{case_result.model_calls}"
            )
            print(
                f"Tokens: "
                f"{case_result.input_tokens + case_result.output_tokens}"
            )

        total_duration_seconds = (
            time.perf_counter()
            - eval_started_at
        )

        passed_cases = sum(
            1
            for result in case_results
            if result.success
        )

        total_cases = len(case_results)
        failed_cases = total_cases - passed_cases

        total_model_calls = sum(
            result.model_calls
            for result in case_results
        )
        total_input_tokens = sum(
            result.input_tokens
            for result in case_results
        )
        total_output_tokens = sum(
            result.output_tokens
            for result in case_results
        )
        total_tokens = (
            total_input_tokens
            + total_output_tokens
        )
        total_estimated_cost = sum(
            result.estimated_cost
            for result in case_results
        )

        if total_cases == 0:
            pass_rate = 0.0
            average_iteration = 0.0
            average_duration_seconds = 0.0
            average_model_calls = 0.0
            average_tokens = 0.0
            average_estimated_cost = 0.0
        else:
            pass_rate = (
                passed_cases
                / total_cases
            )

            average_iteration = (
                sum(
                    result.iteration
                    for result in case_results
                )
                / total_cases
            )

            average_duration_seconds = (
                total_duration_seconds
                / total_cases
            )

            average_model_calls = (
                total_model_calls
                / total_cases
            )

            average_tokens = (
                total_tokens
                / total_cases
            )

            average_estimated_cost = (
                total_estimated_cost
                / total_cases
            )

        summary = {
            "strategy": self.strategy,
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "pass_rate": round(
                pass_rate,
                4,
            ),
            "average_iteration": round(
                average_iteration,
                2,
            ),
            "total_duration_seconds": round(
                total_duration_seconds,
                4,
            ),
            "average_duration_seconds": round(
                average_duration_seconds,
                4,
            ),
            "total_model_calls": (
                total_model_calls
            ),
            "average_model_calls": round(
                average_model_calls,
                2,
            ),
            "total_input_tokens": (
                total_input_tokens
            ),
            "total_output_tokens": (
                total_output_tokens
            ),
            "total_tokens": total_tokens,
            "average_tokens": round(
                average_tokens,
                2,
            ),
            "total_estimated_cost": round(
                total_estimated_cost,
                8,
            ),
            "average_estimated_cost": round(
                average_estimated_cost,
                8,
            ),
            "cases": [
                asdict(result)
                for result in case_results
            ],
        }

        summary_path = (
            run_dir
            / "summary.json"
        )

        summary_path.write_text(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print()
        print(
            f"Eval summary saved to: "
            f"{summary_path}"
        )

        return EvalReport(
            run_dir=run_dir,
            summary=summary,
        )

    def _run_case(
        self,
        case: BenchmarkCase,
    ) -> BenchmarkCaseResult:
        """在临时仓库副本中运行一个案例。"""

        started_at = time.perf_counter()
        source_repo = case.source_repo.resolve()

        if not source_repo.exists():
            raise FileNotFoundError(
                "Benchmark source repository "
                f"does not exist: {source_repo}"
            )

        if not source_repo.is_dir():
            raise ValueError(
                "Benchmark source repository "
                f"is not a directory: {source_repo}"
            )

        cost_summary: dict = {}

        with TemporaryDirectory(
            prefix=(
                f"repopilot_eval_"
                f"{case.name}_"
            ),
        ) as temp_dir_text:
            temp_dir = Path(
                temp_dir_text
            )

            working_repo = (
                temp_dir
                / "repo"
            )

            shutil.copytree(
                src=source_repo,
                dst=working_repo,
                ignore=shutil.ignore_patterns(
                    ".git",
                    "__pycache__",
                    ".pytest_cache",
                    "*.pyc",
                    "runs",
                ),
            )

            workflow = self.workflow_factory()

            result = workflow.run(
                repo=working_repo,
                issue=case.issue,
                test_command=case.test_command,
            )

            cost_summary = (
                getattr(
                    workflow,
                    "last_cost_summary",
                    {},
                )
                or {}
            )

        duration_seconds = (
            time.perf_counter()
            - started_at
        )

        return BenchmarkCaseResult(
            name=case.name,
            success=result.success,
            iteration=result.iteration,
            message=result.message,
            duration_seconds=round(
                duration_seconds,
                4,
            ),
            diff=result.diff,
            test_output=result.test_output,
            source_repo=str(
                source_repo
            ),
            strategy=self.strategy,
            model_calls=int(
                cost_summary.get(
                    "calls",
                    0,
                )
            ),
            input_tokens=int(
                cost_summary.get(
                    "input_tokens",
                    0,
                )
            ),
            output_tokens=int(
                cost_summary.get(
                    "output_tokens",
                    0,
                )
            ),
            estimated_cost=float(
                cost_summary.get(
                    "estimated_cost",
                    0.0,
                )
            ),
        )
