"""Area filter (`filter:`) of static GTFS feeds in city config (issue #43)."""

import copy
from pathlib import Path

import pytest
import yaml
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient

from cities import registry
from cities.registry import CityConfigError, FeedFilter, all_cities, get_city
from cities.tests.test_registry import valid_data, write

REAL_DIR = Path(settings.CITY_CONFIG_DIR)
GOOD_BBOX = [19.5, 49.8, 20.4, 50.3]


@pytest.fixture
def config_dir(tmp_path):
    with override_settings(CITY_CONFIG_DIR=tmp_path):
        registry.clear_cache()
        yield tmp_path
    registry.clear_cache()


def city_with_static_feed(feed: dict):
    data = valid_data()
    data["feeds"]["gtfs_static"] = [{"id": "rail", "url": "https://example.com/rail.zip", **feed}]
    return data


def load(config_dir, data):
    write(config_dir, data, "testville.yaml")
    registry.clear_cache()
    return get_city("testville")


def test_feed_without_filter_has_none(config_dir):
    city = load(config_dir, city_with_static_feed({}))
    assert city.feeds[0].filter is None


def test_filter_is_parsed_into_tuples(config_dir):
    city = load(
        config_dir,
        city_with_static_feed(
            {"filter": {"bbox": [19.5, 49.8, 20.4, 50.3], "exclude_agencies": ["SKM", "WKD"]}}
        ),
    )
    assert city.feeds[0].filter == FeedFilter(
        bbox=(19.5, 49.8, 20.4, 50.3), exclude_agencies=("SKM", "WKD")
    )
    assert isinstance(city.feeds[0].filter.exclude_agencies, tuple)


def test_exclude_agencies_is_optional(config_dir):
    city = load(config_dir, city_with_static_feed({"filter": {"bbox": [19, 49, 20, 50]}}))
    assert city.feeds[0].filter.exclude_agencies == ()


def test_integer_bbox_values_are_accepted(config_dir):
    city = load(config_dir, city_with_static_feed({"filter": {"bbox": [19, 49, 20, 50]}}))
    assert city.feeds[0].filter.bbox == (19, 49, 20, 50)


def test_exclude_agencies_values_stay_strings(config_dir):
    city = load(
        config_dir,
        city_with_static_feed({"filter": {"bbox": GOOD_BBOX, "exclude_agencies": ["12", "SKM"]}}),
    )
    assert city.feeds[0].filter.exclude_agencies == ("12", "SKM")


INVALID_FILTERS = {
    "bbox_missing": {"exclude_agencies": ["SKM"]},
    "empty_filter": {},
    "filter_not_a_mapping": [1, 2, 3],
    "filter_null": None,
    "bbox_three_numbers": {"bbox": [19, 49, 20]},
    "bbox_five_numbers": {"bbox": [19, 49, 20, 50, 51]},
    "bbox_not_a_list": {"bbox": "19,49,20,50"},
    "bbox_text_value": {"bbox": [19, "49", 20, 50]},
    "bbox_bool_value": {"bbox": [19, True, 20, 50]},
    "bbox_null_value": {"bbox": [19, None, 20, 50]},
    "min_lon_equals_max_lon": {"bbox": [19, 49, 19, 50]},
    "min_lon_above_max_lon": {"bbox": [20, 49, 19, 50]},
    "min_lat_above_max_lat": {"bbox": [19, 50, 20, 49]},
    "lon_out_of_range": {"bbox": [19, 49, 181, 50]},
    "lat_out_of_range": {"bbox": [19, -91, 20, 50]},
    "unknown_key": {"bbox": GOOD_BBOX, "min_stops": 3},
    "exclude_agencies_is_string": {"bbox": GOOD_BBOX, "exclude_agencies": "SKM"},
    "exclude_agencies_has_number": {"bbox": GOOD_BBOX, "exclude_agencies": ["SKM", 5]},
    "exclude_agencies_has_empty_string": {"bbox": GOOD_BBOX, "exclude_agencies": ["SKM", ""]},
    "exclude_agencies_has_blank_string": {"bbox": GOOD_BBOX, "exclude_agencies": ["  "]},
    "exclude_agencies_is_mapping": {"bbox": GOOD_BBOX, "exclude_agencies": {"a": "b"}},
}


@pytest.mark.parametrize("raw", INVALID_FILTERS.values(), ids=INVALID_FILTERS.keys())
def test_invalid_filter_is_rejected(config_dir, raw):
    write(config_dir, city_with_static_feed({"filter": raw}), "testville.yaml")
    registry.clear_cache()
    with pytest.raises(CityConfigError, match=r"testville\.yaml.*filter"):
        all_cities()


def test_filter_error_names_the_field(config_dir):
    write(
        config_dir,
        city_with_static_feed({"filter": {"bbox": [20, 49, 19, 50]}}),
        "testville.yaml",
    )
    with pytest.raises(CityConfigError, match=r"gtfs_static\[0\]\.filter\.bbox"):
        all_cities()


def test_filter_is_rejected_on_gtfs_rt_feed(config_dir):
    data = valid_data()
    data["feeds"]["gtfs_rt"] = [
        {
            "id": "rt",
            "entity": "trip_updates",
            "url": "https://example.com/rt.pb",
            "filter": {"bbox": GOOD_BBOX},
        }
    ]
    write(config_dir, data, "testville.yaml")
    with pytest.raises(CityConfigError):
        all_cities()


def test_filter_is_rejected_on_other_feed(config_dir):
    data = valid_data()
    data["feeds"]["other"] = [
        {
            "id": "misc",
            "kind": "vehicles_json",
            "url": "https://example.com/x",
            "filter": {"bbox": GOOD_BBOX},
        }
    ]
    write(config_dir, data, "testville.yaml")
    with pytest.raises(CityConfigError):
        all_cities()


# --------------------------------------------------------- otp.bbox shares the parser


def otp_data(bbox):
    data = copy.deepcopy(valid_data())
    data["otp"] = {"osm_url": "https://example.com/region.osm.pbf", "bbox": bbox}
    return data


def test_otp_bbox_still_valid_when_correct(config_dir):
    city = load(config_dir, otp_data([19, 49, 20, 50]))
    assert city.otp.bbox == (19, 49, 20, 50)


@pytest.mark.parametrize(
    "bbox",
    [[19, 49, 20], [20, 49, 19, 50], [19, 50, 20, 49], [19, "x", 20, 50], [19, 49, 200, 50]],
)
def test_otp_bbox_still_rejected_when_invalid(config_dir, bbox):
    write(config_dir, otp_data(bbox), "testville.yaml")
    with pytest.raises(CityConfigError, match=r"otp\.bbox"):
        all_cities()


# ------------------------------------------------------------------ shipped configs


@pytest.fixture
def real_cities():
    registry.clear_cache()
    yield {c.id: c for c in all_cities()}
    registry.clear_cache()


def rail_feed(city):
    return next(f for f in city.feeds if f.id == "rail")


def test_krakow_rail_feed_filter(real_cities):
    feed = rail_feed(real_cities["krakow"])
    assert feed.url == "https://mkuran.pl/gtfs/polish_trains.zip"
    assert feed.filter == FeedFilter(bbox=(19.55, 49.88, 20.40, 50.27))


def test_warszawa_rail_feed_filter_excludes_skm(real_cities):
    feed = rail_feed(real_cities["warszawa"])
    assert feed.url == "https://mkuran.pl/gtfs/polish_trains.zip"
    assert feed.filter == FeedFilter(bbox=(20.55, 51.90, 21.50, 52.52), exclude_agencies=("SKM",))


def test_only_the_rail_feeds_have_a_filter(real_cities):
    for city in real_cities.values():
        filtered = [f.id for f in city.feeds if f.filter is not None]
        assert filtered == ["rail"], city.id


@pytest.mark.parametrize("city_id", ["krakow", "warszawa"])
def test_rail_attributions_are_present(real_cities, city_id):
    names = {a.name for a in real_cities[city_id].attributions}
    assert "PKP Polskie Linie Kolejowe S.A." in names
    assert any("Polish Trains GTFS" in name for name in names)


def test_krakow_has_three_new_rail_attributions(real_cities):
    # Krakow gains PKP PLK, the mkuran feed and a third rail-related source.
    urls = {a.url for a in real_cities["krakow"].attributions}
    assert "https://mkuran.pl/gtfs/" in urls
    assert "https://www.plk-sa.pl/klienci-i-kontrahenci/api-otwarte-dane" in urls


def test_warszawa_has_koleje_mazowieckie_attribution(real_cities):
    names = {a.name for a in real_cities["warszawa"].attributions}
    assert any(name.startswith("Koleje Mazowieckie") for name in names)


def test_shipped_rail_bbox_contains_the_city_centre(real_cities):
    for city in real_cities.values():
        min_lon, min_lat, max_lon, max_lat = rail_feed(city).filter.bbox
        assert min_lon < city.map.lon < max_lon
        assert min_lat < city.map.lat < max_lat


def test_shipped_yaml_files_carry_the_filter_key():
    for name in ("krakow.yaml", "warszawa.yaml"):
        data = yaml.safe_load((REAL_DIR / name).read_text(encoding="utf-8"))
        rail = next(f for f in data["feeds"]["gtfs_static"] if f["id"] == "rail")
        assert "filter" in rail


# ------------------------------------------------------------------- not exposed


@pytest.mark.parametrize(
    "path", ["/api/v1/cities/", "/api/v1/cities/krakow/", "/api/v1/cities/warszawa/"]
)
def test_cities_api_does_not_expose_the_filter(real_cities, path):
    body = APIClient().get(path).content.decode()
    for word in ("filter", "bbox", "exclude_agencies", "SKM", "polish_trains"):
        assert word not in body
