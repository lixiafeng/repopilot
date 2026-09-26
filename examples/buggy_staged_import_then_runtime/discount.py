def apply_discount(
    price: float,
    discount_percent: float,
) -> float:
    """
    Apply a percentage discount to price.
    """

    discount_rate = (
        discount_percent / 100
    )

    return price * (
        1 - discount_multiplier
    )