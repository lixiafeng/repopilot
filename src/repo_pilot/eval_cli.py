from pathlib import Path

import typer

from repo_pilot.benchmark import EvalRunner
from repo_pilot.benchmark_cases import (
    build_default_cases,
)
from repo_pilot.config import RepoPilotConfig
from repo_pilot.workflow import BugfixWorkflow


def main(
    provider: str = typer.Option(
        "fake",
        "--provider",
        help="Model provider used by the benchmark.",
    ),
    model: str = typer.Option(
        "fake-model",
        "--model",
        help="Model name used by the benchmark.",
    ),
    max_iterations: int = typer.Option(
        2,
        "--max-iterations",
        min=1,
        help="Maximum repair iterations per case.",
    ),
    project_root: Path = typer.Option(
        Path("."),
        "--project-root",
        help="RepoPilot project root directory.",
    ),
    case_name: str | None = typer.Option(
    None,
    "--case",
    help=(
        "Run only one benchmark case."
    ),
),
    output_root: Path = typer.Option(
        Path("eval_runs"),
        "--output-root",
        help="Directory used to save eval summaries.",
    ),
) -> None:
    """
    运行 RepoPilot Benchmark。

    当前会运行 build_default_cases()
    中定义的全部案例。
    """

    # 把项目目录转换为绝对路径。
    resolved_project_root = (
        project_root.resolve()
    )

    # 检查项目目录是否存在。
    if not resolved_project_root.exists():
        raise typer.BadParameter(
            "Project root does not exist: "
            f"{resolved_project_root}"
        )

    # 构造 Workflow 配置。
    #
    # 这里的字段必须与当前 config.py 中
    # RepoPilotConfig 的实际定义保持一致。
    config = RepoPilotConfig(
        provider=provider,
        model=model,
        max_iterations=max_iterations,

        # Benchmark 需要真正应用补丁，
        # 但修改的是临时仓库副本。
        apply_patch=True,
        command_timeout_sec=120,

        # 每个案例自己的 trace 会保存在 runs 中。
        trace_dir=(
            resolved_project_root
            / "runs"
        ),
    )

    def create_workflow() -> BugfixWorkflow:
        """
        每运行一个 BenchmarkCase，
        都创建一个新的 BugfixWorkflow。

        这样不同案例不会共享 Workflow 对象。
        """

        return BugfixWorkflow(
            config=config,
        )

    # 创建 EvalRunner。
    runner = EvalRunner(
        # 传入的是创建 Workflow 的函数，
        # 不是已经创建好的 Workflow 对象。
        workflow_factory=create_workflow,

        # 所有 Eval 汇总写到 eval_runs。
        output_root=(
            resolved_project_root
            / output_root
        ),
    )

    # 加载所有默认 Benchmark 案例。
    all_cases = build_default_cases(
        project_root=resolved_project_root,
    )

# 没有指定 --case 时，运行全部案例。
    if case_name is None:
        cases = all_cases

    else:
        # 只保留名称完全匹配的案例。
        cases = [
            benchmark_case
            for benchmark_case in all_cases
            if benchmark_case.name == case_name
        ]

        # 没有找到指定案例时，
        # 给出全部有效名称。
        if not cases:
            available_names = ", ".join(
                benchmark_case.name
                for benchmark_case in all_cases
            )

            raise typer.BadParameter(
                f"Unknown benchmark case: "
                f"{case_name}. "
                f"Available cases: "
                f"{available_names}"
            )

    typer.echo(
        f"Loaded benchmark cases: {len(cases)}"
    )

    # 正式运行 Benchmark。
    report = runner.run(
        cases=cases,
    )

    # 从报告中取出汇总结果。
    summary = report.summary

    typer.echo("")
    typer.echo("===== Eval Result =====")

    typer.echo(
        f"Total cases: "
        f"{summary['total_cases']}"
    )

    typer.echo(
        f"Passed cases: "
        f"{summary['passed_cases']}"
    )

    typer.echo(
        f"Failed cases: "
        f"{summary['failed_cases']}"
    )

    typer.echo(
        f"Pass rate: "
        f"{summary['pass_rate']:.2%}"
    )

    typer.echo(
        f"Average iteration: "
        f"{summary['average_iteration']}"
    )

    typer.echo(
        f"Eval output: "
        f"{report.run_dir}"
    )

    # 有案例失败时，使用非零退出码。
    if summary["failed_cases"] > 0:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    # 执行：
    #
    # python -m repo_pilot.eval_cli
    #
    # 时，从这里启动 Typer。
    typer.run(main)