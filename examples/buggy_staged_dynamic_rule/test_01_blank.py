from processor import (
    normalize_and_score,
)


def test_blank_returns_zero() -> None:
    assert normalize_and_score("") == 0