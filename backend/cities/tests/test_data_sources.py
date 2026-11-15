"""GET /api/v1/data-sources/ against docs/api.md, plus attribution `descriptions` validation."""

from datetime import UTC, datetime

import pytest
import yaml
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from cities import registry
from cities.registry import CityConfigError, all_cities, get_city
from cities.serializers import parse_http_date
from transit_data.models import FeedVersion

URL = "/api/v1/data-sources/"
Status = FeedVersion.Status


@pytest.fixture(autouse=True)
def _fresh_registry():
    registry.clear_cache()
    yield
    registry.clear_cache()


@pytest.fixture
def client():
    return APIClient()


def get(client, lang=None):
    kwargs = {"HTTP_ACCEPT_LANGUAGE": lang} if lang else {}
    return client.get(URL, **kwargs)


def make_feed(city_id="krakow", feed_id="ztp_tram", status=Status.ACTIVE, **kwargs):
    kwargs.setdefault("downloaded_at", datetime(2026, 11, 14, 2, 0, 12, tzinfo=UTC))
    return FeedVersion.objects.create(city_id=city_id, feed_id=feed_id, status=status, **kwargs)


def city_entry(body, city_id):
    return next(c for c in body["cities"] if c["id"] == city_id)


# ------------------------------------------------------------------ shape and sources


@pytest.mark.django_db
@pytest.mark.parametrize("lang", [None, "pl", "en"])
def test_shape_and_city_order(client, lang):
    resp = get(client, lang)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"cities"}
    assert [c["id"] for c in body["cities"]] == ["krakow", "warszawa"]
    names = {None: "Kraków", "pl": "Kraków", "en": "Cracow"}
    assert body["cities"][0]["name"] == names[lang]
    for city in body["cities"]:
        assert set(city) == {"id", "name", "sources", "feeds"}
        assert city["sources"]
        for source in city["sources"]:
            assert set(source) == {"name", "url", "licence", "licence_url", "description"}


@pytest.mark.django_db
def test_no_auth_required_and_content_language_header(client):
    assert get(client, "en")["Content-Language"] == "en"
    assert get(client, "pl")["Content-Language"] == "pl"


@pytest.mark.django_db
def test_sources_follow_config_order_and_values(client):
    body = get(client, "pl").json()
    for city in all_cities():
        got = city_entry(body, city.id)["sources"]
        assert [s["name"] for s in got] == [a.name for a in city.attributions]
        assert [s["url"] for s in got] == [a.url for a in city.attributions]
        assert [s["licence"] for s in got] == [a.licence for a in city.attributions]
        assert [s["licence_url"] for s in got] == [a.licence_url for a in city.attributions]


@pytest.mark.django_db
def test_description_is_translated_but_names_and_licences_are_not(client):
    pl = city_entry(get(client, "pl").json(), "krakow")["sources"]
    en = city_entry(get(client, "en").json(), "krakow")["sources"]
    assert pl[0]["description"] != en[0]["description"]
    assert pl[0]["description"].startswith("Rozkłady")
    assert en[0]["description"].startswith("Timetables")
    for p, e in zip(pl, en, strict=True):
        assert (p["name"], p["url"], p["licence"], p["licence_url"]) == (
            e["name"],
            e["url"],
            e["licence"],
            e["licence_url"],
        )


@pytest.mark.django_db
def test_unsupported_language_falls_back_to_polish(client):
    de = city_entry(get(client, "de").json(), "krakow")["sources"]
    pl = city_entry(get(client, "pl").json(), "krakow")["sources"]
    assert de == pl


@pytest.mark.django_db
def test_every_shipped_source_has_both_descriptions(client):
    for lang in ("pl", "en"):
        for city in get(client, lang).json()["cities"]:
            assert all(s["description"] for s in city["sources"]), (city["id"], lang)


# ------------------------------------------------------------------ custom config


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
        "feeds": {
            "gtfs_static": [
                {"id": "b_feed", "url": "https://example.com/b.zip"},
                {"id": "a_feed", "url": "https://example.com/a.zip"},
            ],
            "gtfs_rt": [],
            "other": [],
        },
        "ticket_zones": [],
        "attributions": [
            {
                "name": "With both",
                "url": "https://example.com/",
                "licence": "CC0",
                "descriptions": {"pl": "Opis", "en": "Description"},
            },
            {"name": "Without", "url": "https://example.org/", "licence": None},
        ],
    }


def write(directory, data):
    (directory / f"{data['id']}.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
    )


@pytest.fixture
def config_dir(tmp_path):
    with override_settings(CITY_CONFIG_DIR=tmp_path):
        registry.clear_cache()
        yield tmp_path
    registry.clear_cache()


@pytest.fixture
def custom(config_dir):
    write(config_dir, valid_data())
    registry.clear_cache()
    return config_dir


@pytest.mark.django_db
def test_custom_city_sources_null_description_and_licence(client, custom):
    body = get(client, "en").json()
    assert [c["id"] for c in body["cities"]] == ["testville"]
    first, second = body["cities"][0]["sources"]
    assert first["description"] == "Description"
    assert get(client, "pl").json()["cities"][0]["sources"][0]["description"] == "Opis"
    assert second["description"] is None
    assert second["licence"] is None
    assert second["licence_url"] is None


def test_description_property_on_attribution(custom):
    sources = get_city("testville").attributions
    assert sources[0].descriptions is not None
    assert sources[1].descriptions is None
    assert sources[1].description is None


@pytest.mark.parametrize(
    "value",
    [
        {"pl": "tylko pl"},
        {"en": "only en"},
        {},
        {"pl": "a", "en": "b", "de": "c"},
        {"pl": "a", "en": 5},
        {"pl": "", "en": "b"},
        "plain string",
        ["pl", "en"],
        None,
        42,
    ],
)
def test_invalid_descriptions_are_rejected_with_path(config_dir, value):
    data = valid_data()
    data["attributions"][1]["descriptions"] = value
    write(config_dir, data)
    registry.clear_cache()
    with pytest.raises(CityConfigError, match=r"attributions\[1\]\.descriptions"):
        all_cities()


# ------------------------------------------------------------------ feeds


@pytest.mark.django_db
def test_feeds_empty_when_nothing_imported(client):
    body = get(client).json()
    assert all(c["feeds"] == [] for c in body["cities"])


@pytest.mark.django_db
def test_only_active_versions_are_listed(client):
    make_feed(feed_id="ztp_tram", status=Status.ACTIVE)
    make_feed(feed_id="ztp_tram", status=Status.SUPERSEDED)
    make_feed(feed_id="ztp_tram", status=Status.FAILED)
    make_feed(feed_id="ztp_bus", status=Status.IMPORTING)
    make_feed(feed_id="ztp_mobilis_bus", status=Status.SUPERSEDED)
    feeds = city_entry(get(client).json(), "krakow")["feeds"]
    assert [f["feed_id"] for f in feeds] == ["ztp_tram"]


@pytest.mark.django_db
def test_feeds_ordered_by_feed_id_and_scoped_to_city(client):
    make_feed(feed_id="ztp_tram")
    make_feed(feed_id="rail")
    make_feed(feed_id="ztp_bus")
    make_feed(city_id="warszawa", feed_id="ztm")
    body = get(client).json()
    assert [f["feed_id"] for f in city_entry(body, "krakow")["feeds"]] == [
        "rail",
        "ztp_bus",
        "ztp_tram",
    ]
    assert [f["feed_id"] for f in city_entry(body, "warszawa")["feeds"]] == ["ztm"]


@pytest.mark.django_db
def test_feed_not_in_city_config_is_excluded(client):
    make_feed(feed_id="ztp_tram")
    make_feed(feed_id="removed_feed")
    make_feed(city_id="atlantis", feed_id="ztm")
    make_feed(city_id="warszawa", feed_id="ztp_tram")  # feed id belongs to another city
    body = get(client).json()
    assert [f["feed_id"] for f in city_entry(body, "krakow")["feeds"]] == ["ztp_tram"]
    assert city_entry(body, "warszawa")["feeds"] == []


@pytest.mark.django_db
def test_feed_shape_and_values(client):
    make_feed(
        publisher_name="ZTP Kraków",
        last_modified="Fri, 13 Nov 2026 21:10:00 GMT",
        downloaded_at=datetime(2026, 11, 14, 2, 0, 12, tzinfo=UTC),
        imported_at=datetime(2026, 11, 14, 2, 2, 40, tzinfo=UTC),
        service_start_date="2026-11-14",
        service_end_date="2026-12-31",
    )
    (feed,) = city_entry(get(client).json(), "krakow")["feeds"]
    assert feed == {
        "feed_id": "ztp_tram",
        "publisher_name": "ZTP Kraków",
        "last_modified": "2026-11-13T22:10:00+01:00",
        "downloaded_at": "2026-11-14T03:00:12+01:00",
        "imported_at": "2026-11-14T03:02:40+01:00",
        "service_start_date": "2026-11-14",
        "service_end_date": "2026-12-31",
    }


@pytest.mark.django_db
def test_nullable_feed_fields(client):
    make_feed(publisher_name="", last_modified="")
    (feed,) = city_entry(get(client).json(), "krakow")["feeds"]
    assert feed["publisher_name"] is None
    assert feed["last_modified"] is None
    assert feed["imported_at"] is None
    assert feed["service_start_date"] is None
    assert feed["service_end_date"] is None
    assert feed["downloaded_at"] is not None


@pytest.mark.django_db
def test_whitespace_publisher_name_is_null(client):
    make_feed(publisher_name="   ")
    (feed,) = city_entry(get(client).json(), "krakow")["feeds"]
    assert feed["publisher_name"] is None


@pytest.mark.django_db
def test_unparsable_last_modified_is_null(client):
    make_feed(last_modified="yesterday-ish")
    (feed,) = city_entry(get(client).json(), "krakow")["feeds"]
    assert feed["last_modified"] is None


@pytest.mark.django_db
def test_timestamps_carry_the_city_offset_in_summer_and_winter(client):
    make_feed(
        feed_id="ztp_tram",
        last_modified="Wed, 01 Jul 2026 10:00:00 GMT",
        downloaded_at=datetime(2026, 7, 1, 10, 0, 0, tzinfo=UTC),
    )
    make_feed(
        feed_id="ztp_bus",
        last_modified="Thu, 01 Jan 2026 10:00:00 GMT",
        downloaded_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
    )
    feeds = {f["feed_id"]: f for f in city_entry(get(client).json(), "krakow")["feeds"]}
    assert feeds["ztp_tram"]["downloaded_at"] == "2026-07-01T12:00:00+02:00"
    assert feeds["ztp_tram"]["last_modified"] == "2026-07-01T12:00:00+02:00"
    assert feeds["ztp_bus"]["downloaded_at"] == "2026-01-01T11:00:00+01:00"
    assert feeds["ztp_bus"]["last_modified"] == "2026-01-01T11:00:00+01:00"


@pytest.mark.django_db
def test_timestamps_use_each_cities_own_timezone(client, config_dir):
    data = valid_data()
    data["timezone"] = "America/New_York"
    write(config_dir, data)
    registry.clear_cache()
    make_feed(
        city_id="testville",
        feed_id="a_feed",
        last_modified="Wed, 01 Jul 2026 10:00:00 GMT",
        downloaded_at=datetime(2026, 7, 1, 10, 0, 0, tzinfo=UTC),
    )
    (feed,) = get(client).json()["cities"][0]["feeds"]
    assert feed["downloaded_at"] == "2026-07-01T06:00:00-04:00"
    assert feed["last_modified"] == "2026-07-01T06:00:00-04:00"


@pytest.mark.django_db
def test_custom_city_feeds_ordered_by_feed_id(client, custom):
    make_feed(city_id="testville", feed_id="b_feed")
    make_feed(city_id="testville", feed_id="a_feed")
    feeds = get(client).json()["cities"][0]["feeds"]
    assert [f["feed_id"] for f in feeds] == ["a_feed", "b_feed"]


@pytest.mark.django_db
def test_internal_fields_are_not_exposed(client):
    make_feed(
        source_url="https://secret.example/feed.zip",
        sha256="deadbeef" * 8,
        etag='"etag-123"',
        size_bytes=123456789,
        publisher_url="https://publisher.example/",
        last_modified="Fri, 13 Nov 2026 21:10:00 GMT",
    )
    resp = get(client)
    text = resp.content.decode()
    for leaked in ("secret.example", "deadbeef", "etag-123", "123456789", "publisher.example"):
        assert leaked not in text
    (feed,) = city_entry(resp.json(), "krakow")["feeds"]
    assert set(feed) == {
        "feed_id",
        "publisher_name",
        "last_modified",
        "downloaded_at",
        "imported_at",
        "service_start_date",
        "service_end_date",
    }
    # Feed URLs from city config (internal) are not exposed either.
    assert "GTFS_KRK_T.zip" not in text


@pytest.mark.django_db
def test_query_count_does_not_grow_with_feeds(client, django_assert_max_num_queries):
    for feed_id in ("ztp_tram", "ztp_bus", "ztp_mobilis_bus", "rail"):
        make_feed(feed_id=feed_id)
    with django_assert_max_num_queries(2):
        assert get(client).status_code == 200


# ------------------------------------------------------------------ parse_http_date


def test_parse_http_date_valid_gmt():
    assert parse_http_date("Fri, 13 Nov 2026 21:10:00 GMT") == datetime(
        2026, 11, 13, 21, 10, tzinfo=UTC
    )


def test_parse_http_date_minus_zero_is_utc():
    parsed = parse_http_date("Fri, 13 Nov 2026 21:10:00 -0000")
    assert parsed is not None and timezone.is_aware(parsed)
    assert parsed == datetime(2026, 11, 13, 21, 10, tzinfo=UTC)


def test_parse_http_date_numeric_offset():
    assert parse_http_date("Fri, 13 Nov 2026 22:10:00 +0100") == datetime(
        2026, 11, 13, 21, 10, tzinfo=UTC
    )


def test_parse_http_date_result_is_always_aware():
    assert timezone.is_aware(parse_http_date("Fri, 13 Nov 2026 21:10:00 GMT"))


@pytest.mark.parametrize(
    "value",
    ["", "   ", None, "garbage", "2026-11-13", "Fri, 99 Nov 2026 21:10:00 GMT", "Fri, 13 Foo 2026"],
)
def test_parse_http_date_invalid_or_empty_is_none(value):
    assert parse_http_date(value) is None
