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

    # 案例名称，例如 divide_by_zero。
    name: str

    # 有 bug 的原始仓库目录。
    source_repo: Path

    # 交给 Agent 的问题描述。
    issue: str

    # 用于验证修复结果的测试命令。
    test_command: str = "python -m pytest -q"


@dataclass
class BenchmarkCaseResult:
    """保存一个评测案例的最终运行结果。"""

    # 案例名称。
    name: str

    # Agent 是否成功修复。
    success: bool

    # 最终执行到第几轮。
    # 注意字段名是 iteration，没有 s。
    iteration: int

    # Workflow 返回的结果说明。
    message: str

    # 当前案例总运行时间。
    duration_seconds: float

    # Agent 生成的最终代码差异。
    diff: str

    # 最终测试输出。
    test_output: str

    # 原始案例仓库位置。
    source_repo: str


@dataclass
class EvalReport:
    """EvalRunner.run() 返回的评测报告。"""

    # 本次评测的输出目录。
    run_dir: Path

    # 本次评测的汇总数据。
    summary: dict


class WorkflowLike(Protocol):
    """
    EvalRunner 对 Workflow 的最低要求。

    只要一个对象具有下面的 run() 方法，
    它就可以被 EvalRunner 使用。
    """

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
        workflow_factory: Callable[
            [],
            WorkflowLike,
        ],
        output_root: Path,
    ) -> None:
        """
        Args:
            workflow_factory:
                一个不接收参数的函数。

                每次调用它，都应该返回一个可以运行的
                BugfixWorkflow 对象。

            output_root:
                所有评测结果的根目录，例如 eval_runs。
        """

        # 保存 Workflow 创建函数。
        self.workflow_factory = workflow_factory

        # 保存评测结果根目录。
        self.output_root = output_root

    def run(
        self,
        cases: list[BenchmarkCase],
    ) -> EvalReport:
        """依次运行所有案例，并生成汇总结果。"""

        # 每次 Eval 创建一个独立目录。
        run_name = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        # 例如：
        # eval_runs/20260728_153000_123456
        run_dir = self.output_root / run_name

        # 确保输出目录存在。
        run_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # 保存每个案例的运行结果。
        case_results: list[
            BenchmarkCaseResult
        ] = []

        # 记录整个 Eval 的开始时间。
        eval_started_at = time.perf_counter()

        # 依次执行所有评测案例。
        for case in cases:
            print()
            print(
                f"===== Benchmark case: "
                f"{case.name} ====="
            )

            case_result = self._run_case(
                case=case,
            )

            # 保存当前案例结果。
            case_results.append(case_result)

            print(
                f"Case success: "
                f"{case_result.success}"
            )

            print(
                f"Case iteration: "
                f"{case_result.iteration}"
            )

        # 计算整个 Eval 的运行时间。
        total_duration_seconds = (
            time.perf_counter()
            - eval_started_at
        )

        # 统计成功案例数量。
        passed_cases = sum(
            1
            for result in case_results
            if result.success
        )

        # 总案例数量。
        total_cases = len(case_results)

        # 失败案例数量。
        failed_cases = (
            total_cases
            - passed_cases
        )

        # 避免 cases 为空时除以零。
        if total_cases == 0:
            pass_rate = 0.0
            average_iteration = 0.0
        else:
            # 成功率范围是 0 到 1。
            pass_rate = (
                passed_cases
                / total_cases
            )

            # 统计所有案例的平均修复轮次。
            average_iteration = (
                sum(
                    result.iteration
                    for result in case_results
                )
                / total_cases
            )

        # 构造最终评测摘要。
        summary = {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,

            # 保留 4 位小数。
            "pass_rate": round(
                pass_rate,
                4,
            ),

            # 保留 2 位小数。
            "average_iteration": round(
                average_iteration,
                2,
            ),

            "total_duration_seconds": round(
                total_duration_seconds,
                4,
            ),

            # 把每个 dataclass 转换成普通字典。
            "cases": [
                asdict(result)
                for result in case_results
            ],
        }

        # 保存 summary.json。
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

        # 记录当前案例开始时间。
        started_at = time.perf_counter()

        # 将源仓库转换成绝对路径。
        source_repo = (
            case.source_repo.resolve()
        )

        # 案例目录必须存在。
        if not source_repo.exists():
            raise FileNotFoundError(
                "Benchmark source repository "
                f"does not exist: {source_repo}"
            )

        # 案例目标必须是目录。
        if not source_repo.is_dir():
            raise ValueError(
                "Benchmark source repository "
                f"is not a directory: {source_repo}"
            )

        # TemporaryDirectory 会自动创建临时目录。
        #
        # 离开 with 代码块后，临时目录会被自动删除。
        with TemporaryDirectory(
            prefix=(
                f"repopilot_eval_"
                f"{case.name}_"
            ),
        ) as temp_dir_text:
            # 将临时目录字符串转换成 Path。
            temp_dir = Path(
                temp_dir_text
            )

            # 副本仓库放在临时目录的 repo 子目录中。
            working_repo = (
                temp_dir
                / "repo"
            )

            # 把原始案例复制到临时工作区。
            #
            # ignore 表示不复制缓存和 Git 数据。
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

            # 每个案例创建一个新的 Workflow。
            #
            # 这样不同案例之间不会共享运行状态。
            workflow = (
                self.workflow_factory()
            )

            # 在临时副本中运行修复流程。
            result = workflow.run(
                repo=working_repo,
                issue=case.issue,
                test_command=(
                    case.test_command
                ),
            )

        # 离开 with 后，临时仓库会自动删除。
        duration_seconds = (
            time.perf_counter()
            - started_at
        )

        # 把 WorkflowResult 转换为案例结果。
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
            test_output=(
                result.test_output
            ),
            source_repo=str(
                source_repo
            ),
        )