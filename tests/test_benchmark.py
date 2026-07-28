from pathlib import Path

from repo_pilot.benchmark import (
    BenchmarkCase,
    EvalRunner,
)
from repo_pilot.result import WorkflowResult


class DummyWorkflow:
    """
    测试 EvalRunner 使用的假 Workflow。

    它不调用模型，也不运行 pytest。
    """

    def run(
        self,
        repo: Path,
        issue: str,
        test_command: str,
    ) -> WorkflowResult:
        # 修改临时仓库中的 marker.txt。
        #
        # 用它验证 EvalRunner 修改的是副本，
        # 而不是原始案例目录。
        marker_path = (
            repo
            / "marker.txt"
        )

        marker_path.write_text(
            "modified by workflow",
            encoding="utf-8",
        )

        # issue 为 pass 时模拟成功。
        success = issue == "pass"

        return WorkflowResult(
            success=success,
            message=(
                "dummy success"
                if success
                else "dummy failure"
            ),

            # 字段名是 iteration。
            iteration=1,

            diff=(
                "dummy diff"
                if success
                else ""
            ),
            test_output=(
                "dummy test output"
            ),
        )


def create_dummy_workflow() -> DummyWorkflow:
    """每次调用都返回一个新的 DummyWorkflow。"""

    return DummyWorkflow()


def create_source_repo(
    path: Path,
) -> None:
    """创建一个最小测试案例目录。"""

    # 创建案例目录。
    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 写入原始 marker 文件。
    path.joinpath(
        "marker.txt"
    ).write_text(
        "original",
        encoding="utf-8",
    )


def test_eval_runner_aggregates_results(
    tmp_path: Path,
) -> None:
    """EvalRunner 应正确统计成功数和失败数。"""

    # 创建两个原始案例目录。
    success_repo = (
        tmp_path
        / "success_repo"
    )

    failed_repo = (
        tmp_path
        / "failed_repo"
    )

    create_source_repo(success_repo)
    create_source_repo(failed_repo)

    # 创建 EvalRunner。
    runner = EvalRunner(
        workflow_factory=(
            create_dummy_workflow
        ),
        output_root=(
            tmp_path
            / "eval_runs"
        ),
    )

    # 运行两个案例。
    report = runner.run(
        cases=[
            BenchmarkCase(
                name="success_case",
                source_repo=success_repo,
                issue="pass",
            ),
            BenchmarkCase(
                name="failed_case",
                source_repo=failed_repo,
                issue="fail",
            ),
        ]
    )

    # 总共运行两个案例。
    assert (
        report.summary["total_cases"]
        == 2
    )

    # 一个成功。
    assert (
        report.summary["passed_cases"]
        == 1
    )

    # 一个失败。
    assert (
        report.summary["failed_cases"]
        == 1
    )

    # 成功率应该是 1 / 2。
    assert (
        report.summary["pass_rate"]
        == 0.5
    )

    # summary.json 应该已经生成。
    assert (
        report.run_dir
        .joinpath("summary.json")
        .exists()
    )

    # DummyWorkflow 修改的是临时副本。
    #
    # 原始案例文件必须保持 original。
    assert (
        success_repo
        .joinpath("marker.txt")
        .read_text(encoding="utf-8")
        == "original"
    )

    assert (
        failed_repo
        .joinpath("marker.txt")
        .read_text(encoding="utf-8")
        == "original"
    )