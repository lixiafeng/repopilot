import math

import pytest

from geometry import circle_area


def test_circle_area() -> None:
    assert circle_area(2) == pytest.approx(4 * math.pi)


def test_circle_area_zero_radius() -> None:
    assert circle_area(0) == 0
