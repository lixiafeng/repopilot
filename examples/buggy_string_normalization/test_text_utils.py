from text_utils import normalize_name


def test_normalize_name_removes_outer_whitespace() -> None:
    assert normalize_name("  Alice  ") == "alice"


def test_normalize_name_converts_to_lowercase() -> None:
    assert normalize_name("BOB") == "bob"
