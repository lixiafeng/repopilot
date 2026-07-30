from counter import count_items


def test_count_items_with_values() -> None:
    assert count_items(["a", "b", "c"]) == 3


def test_count_items_empty_sequence() -> None:
    assert count_items([]) == 0
