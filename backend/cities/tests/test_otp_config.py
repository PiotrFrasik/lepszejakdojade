"""Optional `otp` section of the city config, and get_otp_url()."""

import copy
import importlib
import re
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, override_settings

from cities import registry
from cities.registry import CityConfigError, OtpConfig, all_cities, get_city, get_otp_url
from cities.tests.test_registry import valid_data, write

OSM = "https://download.example.com/testland.osm.pbf"
GOOD = [19.0, 49.9, 20.1, 50.2]


@pytest.fixture
def config_dir(tmp_path):
    with override_settings(CITY_CONFIG_DIR=tmp_path):
        registry.clear_cache()
        yield tmp_path
    registry.clear_cache()


def load(config_dir, otp):
    data = valid_data()
    data["otp"] = otp
    write(config_dir, data)
    registry.clear_cache()
    return get_city("testville")


def test_city_without_otp_section_has_none(config_dir):
    write(config_dir, valid_data())
    assert get_city("testville").otp is None


def test_otp_with_bbox(config_dir):
    city = load(config_dir, {"osm_url": OSM, "bbox": GOOD})
    assert city.otp == OtpConfig(osm_url=OSM, bbox=(19.0, 49.9, 20.1, 50.2))


def test_otp_without_bbox_key(config_dir):
    assert load(config_dir, {"osm_url": OSM}).otp == OtpConfig(osm_url=OSM, bbox=None)


def test_otp_null_bbox_means_absent(config_dir):
    assert load(config_dir, {"osm_url": OSM, "bbox": None}).otp.bbox is None


def test_otp_integer_bbox_values_become_floats(config_dir):
    bbox = load(config_dir, {"osm_url": OSM, "bbox": [19, 49, 20, 50]}).otp.bbox
    assert bbox == (19.0, 49.0, 20.0, 50.0)
    assert all(isinstance(x, float) for x in bbox)


def test_otp_config_is_immutable(config_dir):
    city = load(config_dir, {"osm_url": OSM})
    with pytest.raises(AttributeError):
        city.otp.osm_url = "https://other.example.com/x.pbf"


def test_bbox_boundary_values_are_accepted(config_dir):
    city = load(config_dir, {"osm_url": OSM, "bbox": [-180, -90, 180, 90]})
    assert city.otp.bbox == (-180.0, -90.0, 180.0, 90.0)


def bbox_with(index, value):
    bbox = list(GOOD)
    bbox[index] = value
    return {"osm_url": OSM, "bbox": bbox}


INVALID_OTP = {
    "not_a_mapping": ("otp", ["x"]),
    "unknown_key": ("otp", {"osm_url": OSM, "graph": "x"}),
    "missing_osm_url": ("otp", {"bbox": GOOD}),
    "empty_otp": ("otp", {}),
    "osm_url_http": ("otp.osm_url", {"osm_url": "http://example.com/x.pbf"}),
    "osm_url_not_url": ("otp.osm_url", {"osm_url": "not a url"}),
    "osm_url_null": ("otp.osm_url", {"osm_url": None}),
    "osm_url_number": ("otp.osm_url", {"osm_url": 5}),
    "osm_url_ftp": ("otp.osm_url", {"osm_url": "ftp://example.com/x.pbf"}),
    "bbox_not_list": ("otp.bbox", {"osm_url": OSM, "bbox": "19,49,20,50"}),
    "bbox_too_short": ("otp.bbox", {"osm_url": OSM, "bbox": [19, 49, 20]}),
    "bbox_too_long": ("otp.bbox", {"osm_url": OSM, "bbox": [19, 49, 20, 50, 1]}),
    "bbox_empty": ("otp.bbox", {"osm_url": OSM, "bbox": []}),
    "bbox_string_value": ("otp.bbox[0]", bbox_with(0, "19")),
    "bbox_bool_value": ("otp.bbox[2]", bbox_with(2, True)),
    "bbox_null_value": ("otp.bbox[3]", bbox_with(3, None)),
    "min_lon_too_low": ("otp.bbox[0]", bbox_with(0, -180.5)),
    "min_lat_too_low": ("otp.bbox[1]", bbox_with(1, -90.1)),
    "max_lon_too_high": ("otp.bbox[2]", bbox_with(2, 181)),
    "max_lat_too_high": ("otp.bbox[3]", bbox_with(3, 91)),
    "min_lon_equal_max": ("otp.bbox", {"osm_url": OSM, "bbox": [19, 49, 19, 50]}),
    "min_lon_greater_max": ("otp.bbox", {"osm_url": OSM, "bbox": [21, 49, 20, 50]}),
    "min_lat_equal_max": ("otp.bbox", {"osm_url": OSM, "bbox": [19, 50, 20, 50]}),
    "min_lat_greater_max": ("otp.bbox", {"osm_url": OSM, "bbox": [19, 51, 20, 50]}),
}


@pytest.mark.parametrize(("field", "otp"), INVALID_OTP.values(), ids=INVALID_OTP.keys())
def test_invalid_otp_is_rejected_with_field_path(config_dir, field, otp):
    data = valid_data()
    data["otp"] = copy.deepcopy(otp)
    write(config_dir, data)
    registry.clear_cache()
    with pytest.raises(CityConfigError, match=r"testville\.yaml.*" + re.escape(field)):
        all_cities()


def test_bbox_latitude_message_uses_field_path(config_dir):
    data = valid_data()
    data["otp"] = bbox_with(1, -91)
    write(config_dir, data)
    with pytest.raises(CityConfigError, match=r"otp\.bbox\[1\]: must be between -90 and 90"):
        all_cities()


def test_shipped_configs_have_otp_with_https_osm_url():
    registry.clear_cache()
    cities = {c.id: c for c in all_cities()}
    for city_id in ("krakow", "warszawa"):
        otp = cities[city_id].otp
        assert otp is not None
        assert otp.osm_url.startswith("https://")
        assert otp.osm_url.endswith(".osm.pbf")


# ------------------------------------------------------------------ get_otp_url


def test_get_otp_url_reads_env(monkeypatch):
    monkeypatch.setenv("OTP_URL_KRAKOW", "http://otp-krakow:8080")
    assert get_otp_url("krakow") == "http://otp-krakow:8080"


def test_get_otp_url_unset_is_none(monkeypatch):
    monkeypatch.delenv("OTP_URL_KRAKOW", raising=False)
    assert get_otp_url("krakow") is None


@pytest.mark.parametrize("value", ["", " ", "   \t "])
def test_get_otp_url_blank_is_none(monkeypatch, value):
    monkeypatch.setenv("OTP_URL_KRAKOW", value)
    assert get_otp_url("krakow") is None


def test_get_otp_url_is_stripped(monkeypatch):
    monkeypatch.setenv("OTP_URL_WARSZAWA", "  http://otp-warszawa:8080 \n")
    assert get_otp_url("warszawa") == "http://otp-warszawa:8080"


def test_get_otp_url_hyphenated_city_id(monkeypatch):
    monkeypatch.setenv("OTP_URL_NEW_TOWN", "http://otp-new-town:8080")
    assert get_otp_url("new-town") == "http://otp-new-town:8080"


def test_get_otp_url_is_per_city(monkeypatch):
    monkeypatch.setenv("OTP_URL_KRAKOW", "http://a:1")
    monkeypatch.delenv("OTP_URL_WARSZAWA", raising=False)
    assert get_otp_url("krakow") == "http://a:1"
    assert get_otp_url("warszawa") is None


def test_get_otp_url_ignores_legacy_otp_url(monkeypatch):
    monkeypatch.delenv("OTP_URL_KRAKOW", raising=False)
    monkeypatch.setenv("OTP_URL", "http://legacy:8080")
    assert get_otp_url("krakow") is None


# ------------------------------------------------------------------ settings


OTP_ENV = ("OTP_DATA_DIR", "OTP_CONFIG_DIR", "OTP_OSMIUM_BIN", "OTP_BBOX_BUFFER_KM")


def reloaded_settings(monkeypatch, **env):
    """Reload the base settings module with only the given OTP_* env vars set."""
    from config.settings import base

    for name in OTP_ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    try:
        importlib.reload(base)
        return {name: getattr(base, name) for name in (*OTP_ENV, "BASE_DIR")}
    finally:
        monkeypatch.undo()
        importlib.reload(base)


def test_otp_settings_defaults(monkeypatch):
    s = reloaded_settings(monkeypatch)
    assert s["OTP_DATA_DIR"] == Path(s["BASE_DIR"]).parent / "otp" / "data"
    assert s["OTP_CONFIG_DIR"] == Path(s["BASE_DIR"]).parent / "otp"
    assert s["OTP_OSMIUM_BIN"] == "osmium"
    assert s["OTP_BBOX_BUFFER_KM"] == 3.0
    assert isinstance(s["OTP_BBOX_BUFFER_KM"], float)


def test_otp_settings_env_overrides(monkeypatch):
    s = reloaded_settings(
        monkeypatch,
        OTP_DATA_DIR="/srv/otp-data",
        OTP_CONFIG_DIR="/srv/otp-config",
        OTP_OSMIUM_BIN="/usr/local/bin/osmium",
        OTP_BBOX_BUFFER_KM="7.5",
    )
    assert s["OTP_DATA_DIR"] == Path("/srv/otp-data")
    assert s["OTP_CONFIG_DIR"] == Path("/srv/otp-config")
    assert s["OTP_OSMIUM_BIN"] == "/usr/local/bin/osmium"
    assert s["OTP_BBOX_BUFFER_KM"] == 7.5


@pytest.mark.parametrize("value", ["", " ", "  \t "])
def test_otp_bbox_buffer_blank_falls_back_to_default(monkeypatch, value):
    assert reloaded_settings(monkeypatch, OTP_BBOX_BUFFER_KM=value)["OTP_BBOX_BUFFER_KM"] == 3.0


@pytest.mark.parametrize(("value", "expected"), [("0", 0.0), ("10", 10.0), (" 2.5 ", 2.5)])
def test_otp_bbox_buffer_numeric_values(monkeypatch, value, expected):
    s = reloaded_settings(monkeypatch, OTP_BBOX_BUFFER_KM=value)
    assert s["OTP_BBOX_BUFFER_KM"] == expected
    assert isinstance(s["OTP_BBOX_BUFFER_KM"], float)


@pytest.mark.parametrize("value", ["abc", "3km", "1,5"])
def test_otp_bbox_buffer_non_numeric_names_the_variable(monkeypatch, value):
    with pytest.raises(ImproperlyConfigured, match="OTP_BBOX_BUFFER_KM"):
        reloaded_settings(monkeypatch, OTP_BBOX_BUFFER_KM=value)


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-1", "-0.5"])
def test_otp_bbox_buffer_rejects_non_finite_and_negative(monkeypatch, value):
    with pytest.raises(ImproperlyConfigured, match="OTP_BBOX_BUFFER_KM"):
        reloaded_settings(monkeypatch, OTP_BBOX_BUFFER_KM=value)


@pytest.mark.parametrize("value", ["", " ", " \t "])
def test_otp_osmium_bin_blank_falls_back_to_default(monkeypatch, value):
    assert reloaded_settings(monkeypatch, OTP_OSMIUM_BIN=value)["OTP_OSMIUM_BIN"] == "osmium"


def test_otp_osmium_bin_custom_path_is_kept(monkeypatch):
    s = reloaded_settings(monkeypatch, OTP_OSMIUM_BIN="/usr/bin/osmium")
    assert s["OTP_OSMIUM_BIN"] == "/usr/bin/osmium"


def test_settings_still_importable_after_invalid_value_test(monkeypatch):
    assert reloaded_settings(monkeypatch)["OTP_BBOX_BUFFER_KM"] == 3.0


def test_otp_settings_blank_path_env_falls_back_to_default(monkeypatch):
    s = reloaded_settings(monkeypatch, OTP_DATA_DIR="", OTP_CONFIG_DIR="")
    assert s["OTP_DATA_DIR"] == Path(s["BASE_DIR"]).parent / "otp" / "data"
    assert s["OTP_CONFIG_DIR"] == Path(s["BASE_DIR"]).parent / "otp"


# ------------------------------------------------------------------ public API


@pytest.fixture
def otp_city_dir(tmp_path):
    data = valid_data("otpville")
    data["otp"] = {"osm_url": OSM, "bbox": GOOD}
    write(tmp_path, data)
    with override_settings(CITY_CONFIG_DIR=tmp_path):
        registry.clear_cache()
        yield tmp_path
    registry.clear_cache()


def _contains_key(obj, key):
    if isinstance(obj, dict):
        return key in obj or any(_contains_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_key(v, key) for v in obj)
    return False


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_api_does_not_expose_otp_for_city_with_otp(otp_city_dir, lang):
    client = Client(HTTP_ACCEPT_LANGUAGE=lang)
    listing = client.get("/api/v1/cities/")
    detail = client.get("/api/v1/cities/otpville/")
    assert listing.status_code == detail.status_code == 200
    for response in (listing, detail):
        for key in ("otp", "osm_url", "bbox"):
            assert not _contains_key(response.json(), key)
        assert "download.example.com" not in response.content.decode()


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_api_does_not_expose_otp_for_shipped_cities(lang):
    registry.clear_cache()
    client = Client(HTTP_ACCEPT_LANGUAGE=lang)
    for url in ("/api/v1/cities/", "/api/v1/cities/krakow/", "/api/v1/cities/warszawa/"):
        response = client.get(url)
        assert response.status_code == 200
        assert not _contains_key(response.json(), "otp")
        assert b"osm_url" not in response.content
        assert b"geofabrik" not in response.content.lower()
