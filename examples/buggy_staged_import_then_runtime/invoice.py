def calculate_final_price(
    price: float,
    discount_percent: float,
) -> float:
    """
    Return the final price after applying
    a percentage discount.
    """

    return apply_discount(
        price,
        discount_percent,
    )