from lib.helper_functions import is_zero

def test_iszero():
    assert is_zero(0)
    assert is_zero(0+1e-14)
    assert is_zero(0-1e-14)
    assert not is_zero(0.5)