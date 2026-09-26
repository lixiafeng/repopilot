import importlib


def normalize_and_score(
    value: str,
) -> int:
    """
    Normalize the input and return its score.
    """

    if value == "":
        raise ValueError(
            "value must not be empty"
        )

    rules = importlib.import_module(
        "score_rules"
    )

    return rules.score(value)