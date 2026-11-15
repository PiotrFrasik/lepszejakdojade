"""GET /cities/{city}/stops/?q= (docs/api.md, "Stops (#59)")."""

import pytest
from django.contrib.gis.geos import Point

from transit_data.models import FeedVersion, Stop

from .conftest import BASE_LAT, BASE_LON, CITY, LAT_PER_100M, MAIN, SECOND, Builder

pytestmark = pytest.mark.django_db


def sid(gtfs_id, feed=MAIN):
    return f"{feed}:{gtfs_id}"


def search(api, q, **kwargs):
    return api.get("stops/", q=q, **kwargs)


def results(api, q, **kwargs):
    response = search(api, q, **kwargs)
    assert response.status_code == 200, response.content
    return response.json()


def names(api, q):
    return [r["name"] for r in results(api, q)]


@pytest.fixture
def named(db, city_config):
    """A small feed whose stop names exercise diacritics, case and ranking."""
    b = Builder(MAIN)
    b.calendar("WK", ["monday"])
    for index, name in enumerate(
        [
            "Żabłocie",
            "Łagiewniki",
            "Plac Wolnica",
            "Rondo Mogilskie",
            "Kopiec Placowy",  # "plac" only as the prefix of the second word
            "Aplacowa",  # "plac" as a mid-word substring
            "Dworzec Główny",
            "Dworcowa",
        ]
    ):
        # 1 km apart so nothing groups by accident
        b.stop(f"N{index}", name, dlat=LAT_PER_100M * 10 * index)
    return b


# ------------------------------------------------------------------ matching


@pytest.mark.parametrize("q", ["zabl", "ZABL", "żabł", "Żabł", "  zabl  "])
def test_diacritics_and_case_insensitive(api, named, q):
    assert names(api, q) == ["Żabłocie"]


@pytest.mark.parametrize("q", ["lag", "ŁAG", "łag", "Lagiew"])
def test_polish_l_with_stroke_folds_to_l(api, named, q):
    assert names(api, q) == ["Łagiewniki"]


def test_query_with_diacritics_matches_plain_and_accented_names(api, named):
    assert names(api, "główny") == ["Dworzec Główny"]
    assert names(api, "glowny") == ["Dworzec Główny"]


def test_word_prefix_ranks_before_other_substrings(api, named):
    # "Plac Wolnica" and "Kopiec Placowy" start a word with the query; "Aplacowa" only
    # contains it.
    assert names(api, "plac") == ["Kopiec Placowy", "Plac Wolnica", "Aplacowa"]


def test_each_rank_is_sorted_by_name(api, named):
    assert names(api, "dwor") == ["Dworcowa", "Dworzec Główny"]


def test_no_match_returns_empty_list(api, named):
    assert results(api, "qqqq") == []


def test_city_without_feeds_returns_empty_list(api, city_config, db):
    assert results(api, "al") == []


def test_exactly_two_characters_is_accepted(api, dataset):
    assert names(api, "al") == ["Alpha"]


def test_response_shape(api, dataset):
    [item] = results(api, "alpha")
    assert set(item) == {"stop_id", "name", "lat", "lon", "vehicle_types", "stop_ids"}
    assert item["stop_id"] == sid("S1")
    assert item["stop_ids"] == [sid("S1")]
    assert item["lat"] == pytest.approx(50.06)
    assert item["lon"] == pytest.approx(19.94)


# ------------------------------------------------------------------ grouping


def test_same_name_within_300_m_is_one_group_and_far_one_is_separate(api, dataset):
    found = results(api, "gamma")
    assert len(found) == 2
    near = next(r for r in found if sid("S3") in r["stop_ids"])
    far = next(r for r in found if sid("S3far") in r["stop_ids"])
    assert sorted(near["stop_ids"]) == [sid("S3"), sid("S3b")]
    assert far["stop_ids"] == [sid("S3far")]


def test_group_has_centroid_and_representative_from_the_group(api, dataset):
    near = next(r for r in results(api, "gamma") if sid("S3") in r["stop_ids"])
    # S3 at +2000 m and S3b at +2100 m of latitude: the centroid is midway.
    assert near["lat"] == pytest.approx(50.06 + LAT_PER_100M * 20.5, abs=1e-5)
    assert near["lon"] == pytest.approx(19.94)
    assert near["stop_id"] in near["stop_ids"]


def test_representative_is_platform_closest_to_centroid(api, city_config, db):
    b = Builder(MAIN)
    # Three platforms in a row, 100 m apart: the middle one is closest to the centroid.
    b.stop("E1", "Line up", dlat=0)
    b.stop("E2", "Line up", dlat=LAT_PER_100M)
    b.stop("E3", "Line up", dlat=LAT_PER_100M * 2)
    [item] = results(api, "line up")
    assert item["stop_id"] == sid("E2")
    assert sorted(item["stop_ids"]) == [sid("E1"), sid("E2"), sid("E3")]
    assert item["lat"] == pytest.approx(50.06 + LAT_PER_100M, abs=1e-5)


def test_different_name_nearby_is_not_grouped(api, dataset):
    [item] = results(api, "other name")
    assert item["stop_ids"] == [sid("S3near")]


def test_groups_across_feeds(api, dataset):
    second = FeedVersion.objects.get(feed_id=SECOND, status=FeedVersion.Status.ACTIVE)
    Stop.objects.create(
        feed_version=second,
        city_id=CITY,
        gtfs_id="G1",
        name="Gamma",
        point=Point(BASE_LON, BASE_LAT + LAT_PER_100M * 20.2, srid=4326),
    )
    near = next(r for r in results(api, "gamma") if sid("S3") in r["stop_ids"])
    assert sid("G1", SECOND) in near["stop_ids"]


# ------------------------------------------------------------------ vehicle types


def test_vehicle_types_of_group_in_canonical_order(api, dataset):
    near = next(r for r in results(api, "gamma") if sid("S3") in r["stop_ids"])
    # S3: tram 10 and bus N1; S3b: tram 52.
    assert near["vehicle_types"] == ["tram", "bus"]


def test_vehicle_types_single_and_multiple(api, dataset):
    [alpha] = results(api, "alpha")
    assert alpha["vehicle_types"] == ["tram", "metro"]
    far = next(r for r in results(api, "gamma") if sid("S3far") in r["stop_ids"])
    assert far["vehicle_types"] == ["bus"]


def test_stop_without_service_has_no_vehicle_types(api, named):
    [item] = results(api, "zabl")
    assert item["vehicle_types"] == []


# ------------------------------------------------------------------ limits and feeds


def test_at_most_20_results(api, city_config, db):
    b = Builder(MAIN)
    for index in range(30):
        b.stop(f"M{index}", f"Marsz {index:02d}", dlat=LAT_PER_100M * 10 * index)
    found = names(api, "marsz")
    assert found == [f"Marsz {i:02d}" for i in range(20)]


def test_only_active_feeds_of_the_city_are_searched(api, dataset):
    old = FeedVersion.objects.get(feed_id=MAIN, status=FeedVersion.Status.SUPERSEDED)
    point = Point(BASE_LON, BASE_LAT, srid=4326)
    Stop.objects.create(
        feed_version=old, city_id=CITY, gtfs_id="OLDSTOP", name="Superseded stop", point=point
    )
    outside = FeedVersion.objects.get(feed_id="not_in_config")
    Stop.objects.create(
        feed_version=outside, city_id=CITY, gtfs_id="ZZ1", name="Outside config stop", point=point
    )
    Builder(MAIN, city_id="elsewhere").stop("EL1", "Elsewhere stop")
    assert results(api, "superseded") == []
    assert results(api, "outside") == []
    assert results(api, "elsewhere") == []


def test_cache_follows_the_set_of_active_versions(api, dataset):
    assert results(api, "newstop") == []
    assert names(api, "alpha") == ["Alpha"]  # warms the cache
    FeedVersion.objects.filter(feed_id=MAIN, status=FeedVersion.Status.ACTIVE).update(
        status=FeedVersion.Status.SUPERSEDED
    )
    Builder(MAIN).stop("NEW", "Newstop")
    assert [r["stop_id"] for r in results(api, "newstop")] == [sid("NEW")]
    assert results(api, "alpha") == []


# ------------------------------------------------------------------ validation and errors


@pytest.mark.parametrize("q", ["a", " a ", "", "   "])
def test_short_or_blank_query_is_400(api, dataset, q):
    response = search(api, q)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "q" in error["details"]


def test_missing_query_is_400(api, dataset):
    response = api.get("stops/")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "q" in error["details"]


def test_short_query_message_is_translated(api, dataset):
    pl = search(api, "a", lang="pl").json()["error"]["details"]["q"]
    en = search(api, "a", lang="en").json()["error"]["details"]["q"]
    assert "Wpisz co najmniej 2 znaki." in str(pl)
    assert "Enter at least 2 characters." in str(en)


def test_blank_query_message_is_translated(api, dataset):
    pl = search(api, "  ", lang="pl").json()["error"]["details"]["q"]
    en = search(api, "  ", lang="en").json()["error"]["details"]["q"]
    assert "Wpisz co najmniej 2 znaki." in str(pl)
    assert "Enter at least 2 characters." in str(en)


def test_unknown_city_is_404(api, dataset):
    response = search(api, "alpha", city="nowhere")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_search_needs_no_auth_and_is_get_only(api, dataset):
    assert search(api, "alpha").status_code == 200
    assert api.client.post(f"/api/v1/cities/{CITY}/stops/", {"q": "alpha"}).status_code == 405


def test_stop_names_are_not_translated(api, dataset):
    assert results(api, "alpha", lang="en") == results(api, "alpha", lang="pl")
