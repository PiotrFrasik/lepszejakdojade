"""City registry: YAML validation and "adding a city = adding a file"."""

import copy
from pathlib import Path

import pytest
import yaml
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from cities import registry
from cities.registry import CityConfigError, all_cities, get_city

REAL_DIR = Path(settings.CITY_CONFIG_DIR)


def valid_data(city_id="testville"):
    return {
        "id": city_id,
        "names": {"pl": "Testowo", "en": "Testville"},
        "timezone": "Europe/Warsaw",
        "map": {"center": {"lat": 50.0, "lon": 19.9}, "zoom": 12},
        "vehicle_types": ["tram", "bus"],
        "line_groups": [
            {"id": "day", "names": {"pl": "Dzienne", "en": "Day"}, "colour": "#112233"},
        ],
        "realtime": {"departures": True, "vehicles": False},
        "feeds": {"gtfs_static": [], "gtfs_rt": [], "other": []},
        "ticket_zones": [],
        "attributions": [{"name": "Operator", "url": "https://example.com/", "licence": None}],
    }


def write(directory, data, name=None):
    name = name or f"{data['id']}.yaml"
    (directory / name).write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def config_dir(tmp_path):
    with override_settings(CITY_CONFIG_DIR=tmp_path):
        registry.clear_cache()
        yield tmp_path
    registry.clear_cache()


def test_valid_config_loads(config_dir):
    write(config_dir, valid_data())
    assert [c.id for c in all_cities()] == ["testville"]
    assert get_city("testville").timezone == "Europe/Warsaw"
    assert get_city("nope") is None


def test_real_configs_load():
    registry.clear_cache()
    assert [c.id for c in all_cities()] == ["krakow", "warszawa"]


def test_adding_a_city_is_adding_a_file(config_dir):
    write(config_dir, valid_data("aaa"))
    write(config_dir, valid_data("zzz"))
    assert [c.id for c in all_cities()] == ["aaa", "zzz"]
    write(config_dir, valid_data("mmm"))
    registry.clear_cache()
    assert [c.id for c in all_cities()] == ["aaa", "mmm", "zzz"]


def test_real_dir_plus_third_city(tmp_path):
    for f in REAL_DIR.glob("*.yaml"):
        (tmp_path / f.name).write_bytes(f.read_bytes())
    write(tmp_path, valid_data("gdansk"))
    with override_settings(CITY_CONFIG_DIR=tmp_path):
        assert [c.id for c in all_cities()] == ["gdansk", "krakow", "warszawa"]
    registry.clear_cache()


def set_path(data, *keys, value):
    for k in keys[:-1]:
        data = data[k]
    data[keys[-1]] = value


INVALID = {
    "unknown_top_level_key": lambda d: d.update(secret="x"),
    "unknown_nested_key": lambda d: d["map"].update(extra=1),
    "missing_top_level_key": lambda d: d.pop("realtime"),
    "id_mismatch_filename": lambda d: d.update(id="other"),
    "bad_id_chars": lambda d: d.update(id="Bad Id"),
    "missing_language_name": lambda d: d["names"].pop("en"),
    "unknown_language_name": lambda d: d["names"].update(de="Testdorf"),
    "empty_name": lambda d: d["names"].update(pl=" "),
    "bad_timezone": lambda d: d.update(timezone="Mars/Olympus"),
    "lat_too_high": lambda d: set_path(d, "map", "center", "lat", value=91),
    "lon_too_low": lambda d: set_path(d, "map", "center", "lon", value=-181),
    "lat_not_number": lambda d: set_path(d, "map", "center", "lat", value="50"),
    "zoom_negative": lambda d: set_path(d, "map", "zoom", value=-1),
    "zoom_too_high": lambda d: set_path(d, "map", "zoom", value=23),
    "zoom_float": lambda d: set_path(d, "map", "zoom", value=12.5),
    "zoom_bool": lambda d: set_path(d, "map", "zoom", value=True),
    "vehicle_type_unknown": lambda d: d.update(vehicle_types=["tram", "boat"]),
    "vehicle_type_duplicate": lambda d: d.update(vehicle_types=["tram", "tram"]),
    "vehicle_types_empty": lambda d: d.update(vehicle_types=[]),
    "colour_uppercase": lambda d: d["line_groups"][0].update(colour="#AABBCC"),
    "colour_short": lambda d: d["line_groups"][0].update(colour="#abc"),
    "colour_no_hash": lambda d: d["line_groups"][0].update(colour="aabbcc"),
    "line_group_duplicate_id": lambda d: d["line_groups"].append(
        copy.deepcopy(d["line_groups"][0])
    ),
    "line_group_missing_language": lambda d: d["line_groups"][0]["names"].pop("pl"),
    "realtime_not_bool": lambda d: d["realtime"].update(departures="yes"),
}


@pytest.mark.parametrize("mutate", INVALID.values(), ids=INVALID.keys())
def test_invalid_config_is_rejected(config_dir, mutate):
    data = valid_data()
    mutate(data)
    write(config_dir, data, "testville.yaml")
    registry.clear_cache()
    with pytest.raises(CityConfigError):
        all_cities()


def test_error_names_file_and_field(config_dir):
    data = valid_data()
    data["timezone"] = "Mars/Olympus"
    write(config_dir, data)
    with pytest.raises(CityConfigError, match=r"testville\.yaml.*timezone"):
        all_cities()


def test_languages_setting_drives_required_names(config_dir):
    write(config_dir, valid_data())
    with (
        override_settings(LANGUAGES=[("pl", "Polski"), ("en", "English"), ("de", "Deutsch")]),
        pytest.raises(CityConfigError),
    ):
        all_cities()


def test_malformed_yaml(config_dir):
    (config_dir / "broken.yaml").write_text("id: [unclosed\n  : :", encoding="utf-8")
    with pytest.raises(CityConfigError, match="broken.yaml"):
        all_cities()


def test_yaml_not_a_mapping(config_dir):
    (config_dir / "testville.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(CityConfigError):
        all_cities()


def test_missing_directory(tmp_path):
    with (
        override_settings(CITY_CONFIG_DIR=tmp_path / "does-not-exist"),
        pytest.raises(CityConfigError, match="does not exist"),
    ):
        all_cities()
    registry.clear_cache()


def test_empty_directory(config_dir):
    with pytest.raises(CityConfigError):
        all_cities()


def test_config_error_is_improperly_configured():
    assert issubclass(CityConfigError, ImproperlyConfigured)


def test_registry_is_cached_until_cleared(config_dir):
    write(config_dir, valid_data("aaa"))
    assert len(all_cities()) == 1
    write(config_dir, valid_data("bbb"))
    assert len(all_cities()) == 1
    registry.clear_cache()
    assert len(all_cities()) == 2
