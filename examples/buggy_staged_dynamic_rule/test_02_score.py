from processor import (
    normalize_and_score,
)


def test_normal_score() -> None:
    assert normalize_and_score(
        "abc"
    ) == 3