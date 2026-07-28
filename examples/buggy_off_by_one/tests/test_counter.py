from counter import count_items


def test_count_three_items() -> None:
    """三个元素的数量应该是 3。"""

    result = count_items(
        ["apple", "banana", "orange"]
    )

    assert result == 3


def test_count_empty_items() -> None:
    """空列表的元素数量应该是 0。"""

    result = count_items([])

    assert result == 0