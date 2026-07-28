from pathlib import Path

from repo_pilot.benchmark import BenchmarkCase


def build_default_cases(
    project_root: Path,
) -> list[BenchmarkCase]:
    """
    创建 RepoPilot 当前默认的 Benchmark 案例。

    project_root 是 RepoPilot 项目根目录，例如：

    D:/repopilot-handwrite
    """

    # 将项目根目录转换成绝对路径，
    # 避免程序受到当前终端目录的影响。
    resolved_root = project_root.resolve()

    # 返回当前要评测的案例列表。
    return [
        BenchmarkCase(
            # 案例的唯一名称。
            name="divide_by_zero",

            # 有 bug 的原始案例目录。
            #
            # EvalRunner 不会直接修改它，
            # 而是先复制到临时目录。
            source_repo=(
                resolved_root
                / "examples"
                / "buggy_calculator"
            ),

            # 交给 RepoPilot 的问题描述。
            issue=(
                "divide by zero should "
                "raise ValueError"
            ),

            # RepoPilot 应用补丁后，
            # 使用这条命令验证结果。
            test_command=(
                "python -m pytest -q"
            ),
        ),
        BenchmarkCase(
        # 第二个案例：元素数量少算一个。
        name="off_by_one_count",
        source_repo=(
            resolved_root
            / "examples"
            / "buggy_off_by_one"
        ),
        issue=(
            "count_items should return "
            "the actual number of items "
            "without subtracting one"
        ),
        test_command="python -m pytest -q",
    ),

    ]