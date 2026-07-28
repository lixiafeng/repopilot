from repo_pilot.retry import RetryPolicy

def test_classify_syntax_error()->None:
    policy=RetryPolicy()
    failure_type = policy.classify(
    stage="compile",
    output="SyntaxError: expected ':'",
)

    assert failure_type == "syntax_error"

def test_classify_import_error() -> None:
    """ModuleNotFoundError 应该被分类为 import_error。"""

    policy = RetryPolicy()

    failure_type = policy.classify(
        stage="tests",
        output=(
            "ModuleNotFoundError: "
            "No module named 'calculator'"
        ),
    )
    assert failure_type == "import_error"

def test_classify_patch_apply_error() -> None:
    """old text 不存在属于补丁应用错误。"""

    policy = RetryPolicy()

    failure_type = policy.classify(
        stage="patch_apply",
        output="",
        error_message=(
            "Old text was not found in calculator.py"
        ),
    )

    assert failure_type == "patch_apply_error"


def test_should_retry_before_max_iteration() -> None:
    """第一轮失败且允许两轮时，应该继续重试。"""

    policy = RetryPolicy()

    result = policy.should_retry(
        failure_type="syntax_error",

        # 当前执行完第一轮。
        iteration=1,

        # 最多允许两轮。
        max_iterations=2,
    )

    assert result is True


def test_should_not_retry_at_max_iteration() -> None:
    """达到最大轮次后，不能继续重试。"""

    policy = RetryPolicy()

    result = policy.should_retry(
        failure_type="syntax_error",
        iteration=2,
        max_iterations=2,
    )

    assert result is False


def test_timeout_is_not_retryable() -> None:
    """按照当前规则，测试超时不进入 Agent 下一轮。"""

    policy = RetryPolicy()

    result = policy.should_retry(
        failure_type="timeout",
        iteration=1,
        max_iterations=3,
    )

    assert result is False