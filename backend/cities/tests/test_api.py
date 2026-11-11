"""GET /api/v1/cities/ and /api/v1/cities/{city}/ against docs/api.md."""

from pathlib import Path

import pytest
import yaml
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient

from cities import registry

LIST_URL = "/api/v1/cities/"


@pytest.fixture(autouse=True)
def _fresh_registry():
    registry.clear_cache()
    yield
    registry.clear_cache()


@pytest.fixture
def client():
    return APIClient()


def get(client, url, lang=None):
    kwargs = {"HTTP_ACCEPT_LANGUAGE": lang} if lang else {}
    return client.get(url, **kwargs)


NAMES = {
    "krakow": {None: "Kraków", "pl": "Kraków", "en": "Cracow"},
    "warszawa": {None: "Warszawa", "pl": "Warszawa", "en": "Warsaw"},
}


@pytest.mark.parametrize("lang", [None, "pl", "en"])
def test_list_shape_and_names(client, lang):
    resp = get(client, LIST_URL, lang)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert [c["id"] for c in body] == ["krakow", "warszawa"]
    for city in body:
        assert set(city) == {"id", "name", "map"}
        assert set(city["map"]) == {"center", "zoom"}
        assert set(city["map"]["center"]) == {"lat", "lon"}
        assert isinstance(city["map"]["zoom"], int)
        assert city["name"] == NAMES[city["id"]][lang]


def test_list_map_values_match_config(client):
    body = {c["id"]: c for c in get(client, LIST_URL).json()}
    assert body["krakow"]["map"]["center"] == {"lat": 50.0614, "lon": 19.9383}
    assert body["krakow"]["map"]["zoom"] == 12
    w = body["warszawa"]["map"]["center"]
    assert 52 < w["lat"] < 52.5 and 20.8 < w["lon"] < 21.2


@pytest.mark.parametrize("lang", [None, "pl", "en"])
@pytest.mark.parametrize("city", ["krakow", "warszawa"])
def test_detail_shape(client, city, lang):
    resp = get(client, f"{LIST_URL}{city}/", lang)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "id", "name", "timezone", "map", "vehicle_types", "line_groups", "realtime",
    }
    assert body["id"] == city
    assert body["name"] == NAMES[city][lang]
    assert body["timezone"] == "Europe/Warsaw"
    assert set(body["map"]) == {"center", "zoom"}
    assert set(body["realtime"]) == {"departures", "vehicles"}
    assert all(isinstance(v, bool) for v in body["realtime"].values())
    assert body["line_groups"]
    for g in body["line_groups"]:
        assert set(g) == {"id", "name", "colour"}
        assert g["name"]
        assert len(g["colour"]) == 7 and g["colour"] == g["colour"].lower()
    ids = [g["id"] for g in body["line_groups"]]
    assert len(ids) == len(set(ids))


def test_vehicle_types(client):
    krakow = get(client, f"{LIST_URL}krakow/").json()["vehicle_types"]
    warsaw = get(client, f"{LIST_URL}warszawa/").json()["vehicle_types"]
    assert "metro" not in krakow
    assert "tram" in krakow and "bus" in krakow
    assert "metro" in warsaw


def test_line_group_names_translated(client):
    pl = get(client, f"{LIST_URL}krakow/", "pl").json()["line_groups"]
    en = get(client, f"{LIST_URL}krakow/", "en").json()["line_groups"]
    assert [g["id"] for g in pl] == [g["id"] for g in en]
    assert [g["name"] for g in pl] != [g["name"] for g in en]
    assert {g["colour"] for g in pl} == {g["colour"] for g in en}


def test_unsupported_language_falls_back_to_default(client):
    assert get(client, f"{LIST_URL}krakow/", "de").json()["name"] == "Kraków"


def test_regional_language_tag(client):
    assert get(client, f"{LIST_URL}krakow/", "en-GB").json()["name"] == "Cracow"


def test_no_internal_data_leaked(client):
    text = ""
    for url in (LIST_URL, f"{LIST_URL}krakow/", f"{LIST_URL}warszawa/"):
        text += get(client, url).content.decode()
    for word in ("feeds", "ticket_zones", "attribution", "gtfs", ".pb", "http", "licence"):
        assert word not in text


@pytest.mark.parametrize(
    "lang,message",
    [(None, "Nie znaleziono miasta."), ("pl", "Nie znaleziono miasta."),
     ("en", "City not found.")],
)
def test_unknown_city_404(client, lang, message):
    resp = get(client, f"{LIST_URL}atlantis/", lang)
    assert resp.status_code == 404
    assert resp.json() == {"error": {"code": "not_found", "message": message}}


def test_wrong_case_city_is_404(client):
    assert get(client, f"{LIST_URL}Krakow/").status_code == 404


def test_post_not_allowed(client):
    assert client.post(LIST_URL, {}, format="json").status_code == 405
    assert client.post(f"{LIST_URL}krakow/", {}, format="json").status_code == 405


def test_new_city_file_appears_in_api(client, tmp_path):
    for f in Path(settings.CITY_CONFIG_DIR).glob("*.yaml"):
        (tmp_path / f.name).write_bytes(f.read_bytes())
    data = yaml.safe_load((tmp_path / "krakow.yaml").read_text(encoding="utf-8"))
    data["id"] = "gdansk"
    data["names"] = {"pl": "Gdańsk", "en": "Gdansk"}
    (tmp_path / "gdansk.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
    )
    with override_settings(CITY_CONFIG_DIR=tmp_path):
        body = get(client, LIST_URL, "en").json()
        assert [c["id"] for c in body] == ["gdansk", "krakow", "warszawa"]
        assert body[0]["name"] == "Gdansk"
        assert get(client, f"{LIST_URL}gdansk/").status_code == 200


def test_openapi_schema_contains_paths(client):
    resp = client.get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/api/v1/cities/" in paths
    assert "/api/v1/cities/{city}/" in paths
    assert "get" in paths["/api/v1/cities/"]
    assert "404" in paths["/api/v1/cities/{city}/"]["get"]["responses"]
