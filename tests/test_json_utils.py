import pytest
from repo_pilot.json_utils import(
    ModelOutputError,
    parse_json_object,
)
def test_parse_json_object()->None:
    text = '{"ok": true, "count": 2}'

    # 调用被测试函数。
    result = parse_json_object(
        text=text,
        source_name="test output",
    )

    # JSON 中的 true 会被转换成 Python 的 True。
    assert result == {
        "ok": True,
        "count": 2,
    }
def test_parse_markdown_json_block() -> None:
    """Markdown 代码块中的 JSON 应该可以被提取。"""

    # 真实模型有时会使用 ```json 包裹结果。
    text = """
        '''json
        {
        "operations": []
        }

        """
    result = parse_json_object(
        text=text,
        source_name="JSON patch",
    )

    assert result == {
        "operations": [],
    }
def test_parse_json_with_explanation_text() -> None:
    text="""
        Here is the requested result:

        {
        "success": true
        }

        Finished.

"""
    result = parse_json_object(
        text=text,
        source_name="model output",
    )

    assert result == {
        "success": True,
    }

def test_reject_json_array() -> None:

    text = '["calculator.py", "tests/test_calculator.py"]'


    with pytest.raises(
        ModelOutputError,
        match="must be a JSON object",
    ):
        parse_json_object(
            text=text,
            source_name="repair plan",
        )

def test_reject_invalid_json() -> None:
    """完全无法解析的内容应该抛出明确错误。"""

    text = "This is not JSON."

    with pytest.raises(
        ModelOutputError,
        match="could not be parsed as JSON",
    ):
        parse_json_object(
            text=text,
            source_name="JSON patch",
        )

