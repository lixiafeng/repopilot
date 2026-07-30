import pytest

from calculator import divide


def test_divide_normal_numbers() -> None:
    assert divide(10, 2) == 5


def test_divide_by_zero_raises_value_error() -> None:
    with pytest.raises(ValueError):
        divide(10, 0)
