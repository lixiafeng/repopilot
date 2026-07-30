import pytest

from pricing import calculate_final_price


def test_twenty_percent_discount() -> None:
    assert calculate_final_price(100, 20) == pytest.approx(80)


def test_twenty_five_percent_discount() -> None:
    assert calculate_final_price(200, 25) == pytest.approx(150)


def test_zero_percent_discount() -> None:
    assert calculate_final_price(50, 0) == pytest.approx(50)
