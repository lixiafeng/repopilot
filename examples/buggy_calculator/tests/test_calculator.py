import pytest

from calculator  import divide

def test_divide_normal_numbers():
    assert divide(6,2)==3

def test_divide_by_zero_raises_value_error():
    with pytest.raises(ValueError):
        divide(1,0)
