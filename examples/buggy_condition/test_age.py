from age import is_adult


def test_age_below_eighteen_is_not_adult() -> None:
    assert is_adult(17) is False


def test_age_eighteen_is_adult() -> None:
    assert is_adult(18) is True


def test_age_above_eighteen_is_adult() -> None:
    assert is_adult(21) is True
