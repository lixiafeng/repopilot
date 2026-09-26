import math


def discounted_circle_area(
    radius: float,
    discount_percent: float,
) -> float:
    """
    Return the discounted area of a circle.
    """

    area = math.pi * radius

    discount_rate = (
        discount_percent / 100
    )

    return area * discount_rate