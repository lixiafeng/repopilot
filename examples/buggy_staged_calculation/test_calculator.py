import math

import pytest

from calculator import (
    discounted_circle_area,
)


def test_zero_discount() -> None:
    assert discounted_circle_area(
        2,
        0,
    ) == pytest.approx(
        math.pi * 4
    )


def test_twenty_percent_discount() -> None:
    assert discounted_circle_area(
        2,
        20,
    ) == pytest.approx(
        math.pi * 4 * 0.8
    )