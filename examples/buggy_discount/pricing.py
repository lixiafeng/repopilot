from discount import percentage_to_rate


def calculate_final_price(
    price: float,
    discount_percent: float,
) -> float:
    """Return the price after applying a percentage discount."""
    discount_rate = percentage_to_rate(discount_percent)
    return price * discount_rate
