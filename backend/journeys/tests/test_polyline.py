import pytest

from journeys.polyline import decode


def test_decodes_reference_polyline_to_lon_lat_order():
    # Reference example from the Google polyline documentation.
    result = decode("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert result == [[-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]]


def test_empty_string_gives_no_points():
    assert decode("") == []


def test_truncated_string_raises_value_error():
    with pytest.raises(ValueError):
        decode("_p~iF~ps|U_")


def test_invalid_character_raises_value_error():
    with pytest.raises(ValueError):
        decode("\x01\x02")
