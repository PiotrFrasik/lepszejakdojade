"""Backend language negotiation and translated errors (docs/api.md, "Language negotiation")."""

import pytest
from django.contrib.auth.models import Group
from django.db import connection, models
from django.test import Client
from django.utils import translation
from modeltranslation.translator import TranslationOptions, translator
from rest_framework.test import APIClient

from core.middleware import negotiate_language, parse_accept_language
from core.serializers import TranslatedModelSerializer, translation_column_names

URLS = "core.tests.i18n_urls"
CITY_404 = "/api/v1/cities/unknown/"


# --- parse_accept_language / negotiate_language ---------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, []),
        ("", []),
        ("en", ["en"]),
        ("de, en;q=0.8", ["de", "en"]),
        ("en;q=0.5, pl;q=0.9", ["pl", "en"]),
        ("en, pl", ["en", "pl"]),  # equal q keeps header order
        ("pl;q=0, en", ["en"]),  # q=0 means not acceptable
        ("en;q=abc, pl", ["pl"]),  # bad q skipped
        ("en;q=1.5, pl", ["pl"]),  # q out of range skipped
        ("*, en;q=0.5", ["en"]),  # wildcard skipped
        ("!!!, en", ["en"]),  # invalid tag skipped
        ("en-GB,en;q=0.9", ["en-GB", "en"]),
        (" en ; q=0.7 ", ["en"]),
    ],
)
def test_parse_accept_language(header, expected):
    assert parse_accept_language(header) == expected


def test_parse_accept_language_truncates_long_header_at_last_comma():
    header = "de," * 200 + "en"  # far longer than 500 chars; the trailing entry is cut
    tags = parse_accept_language(header)
    assert tags
    assert set(tags) == {"de"}


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, "pl"),
        ("", "pl"),
        ("pl", "pl"),
        ("en", "en"),
        ("EN", "en"),
        ("en-GB", "en"),
        ("en-US,en;q=0.9", "en"),
        ("pl-PL", "pl"),
        ("de", "pl"),
        ("de, fr;q=0.9", "pl"),
        ("de, en;q=0.8", "en"),
        ("*", "pl"),
        ("en;q=0", "pl"),
        ("en;q=0.4, pl;q=0.6", "pl"),
        ("garbage;;;", "pl"),
    ],
)
def test_negotiate_language(header, expected):
    assert negotiate_language(header) == expected


# --- end-to-end headers on a real endpoint --------------------------------------------------


@pytest.fixture
def client():
    return APIClient()


def get(client, url, lang=None, **extra):
    if lang is not None:
        extra["HTTP_ACCEPT_LANGUAGE"] = lang
    return client.get(url, **extra)


def test_contract_example_unknown_city_with_unsupported_then_english(client):
    response = get(client, CITY_404, "de, en;q=0.8")
    assert response.status_code == 404
    assert response["Content-Language"] == "en"
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    ("lang", "expected"),
    [(None, "pl"), ("", "pl"), ("pl", "pl"), ("en", "en"), ("en-GB", "en"), ("de", "pl")],
)
def test_content_language_header_on_error_response(client, lang, expected):
    response = get(client, CITY_404, lang)
    assert response.status_code == 404
    assert response["Content-Language"] == expected


def test_content_language_and_vary_on_success(client):
    response = get(client, "/api/v1/cities/", "en")
    assert response.status_code == 200
    assert response["Content-Language"] == "en"
    assert "Accept-Language" in response["Vary"]


def test_messages_differ_between_languages_but_code_is_stable(client):
    pl = get(client, CITY_404, "pl").json()["error"]
    en = get(client, CITY_404, "en").json()["error"]
    assert pl["code"] == en["code"] == "not_found"
    assert pl["message"] != en["message"]
    assert en["message"] == "City not found."


def test_unsupported_language_never_errors(client):
    response = get(client, CITY_404, "xx-YY;q=0.3, *;q=0.1")
    assert response.status_code == 404
    assert response["Content-Language"] == "pl"


def test_cookie_and_query_param_are_ignored(client):
    client.cookies["django_language"] = "en"
    response = get(client, CITY_404 + "?lang=en")
    assert response["Content-Language"] == "pl"
    assert response.json()["error"]["message"] != "City not found."


def test_language_does_not_leak_between_requests(client):
    assert get(client, CITY_404, "en")["Content-Language"] == "en"
    assert get(client, CITY_404)["Content-Language"] == "pl"


def test_url_language_prefix_is_not_supported(client):
    assert client.get("/en/api/v1/cities/").status_code == 404


# --- error formats in both languages --------------------------------------------------------


@pytest.fixture
def plain_client():
    return Client(raise_request_exception=False)


def error_of(response):
    body = response.json()
    assert set(body) == {"error"}
    return body["error"]


@pytest.mark.urls(URLS)
@pytest.mark.parametrize("lang", ["pl", "en"])
def test_405_has_contract_format_and_content_language(client, lang):
    response = client.post("/api/boom/", HTTP_ACCEPT_LANGUAGE=lang)
    assert response.status_code == 405
    assert error_of(response)["code"] == "method_not_allowed"
    assert response["Content-Language"] == lang


@pytest.mark.urls(URLS)
def test_405_message_is_translated(client):
    pl = error_of(client.post("/api/boom/", HTTP_ACCEPT_LANGUAGE="pl"))["message"]
    en = error_of(client.post("/api/boom/", HTTP_ACCEPT_LANGUAGE="en"))["message"]
    assert pl != en


@pytest.mark.urls(URLS)
def test_415_unsupported_media_type(client):
    response = client.post(
        "/api/echo/", data="x", content_type="text/plain", HTTP_ACCEPT_LANGUAGE="en"
    )
    assert response.status_code == 415
    assert error_of(response)["code"] == "unsupported_media_type"
    assert response["Content-Language"] == "en"


@pytest.mark.urls(URLS)
def test_parse_error_has_fixed_translated_message(client):
    pl = client.post(
        "/api/echo/", data="{bad", content_type="application/json", HTTP_ACCEPT_LANGUAGE="pl"
    )
    en = client.post(
        "/api/echo/", data="{bad", content_type="application/json", HTTP_ACCEPT_LANGUAGE="en"
    )
    assert pl.status_code == en.status_code == 400
    assert error_of(pl)["code"] == error_of(en)["code"] == "parse_error"
    assert error_of(pl)["message"] == "Nie udało się odczytać treści żądania."
    assert error_of(en)["message"] == "The request body could not be parsed."


@pytest.mark.urls(URLS)
def test_validation_error_nested_details_in_both_languages(client):
    payload = {"items": [{"n": 1}, {"n": "x"}]}
    en = client.post("/api/echo/", payload, format="json", HTTP_ACCEPT_LANGUAGE="en")
    pl = client.post("/api/echo/", payload, format="json", HTTP_ACCEPT_LANGUAGE="pl")
    for response in (en, pl):
        assert response.status_code == 400
        error = error_of(response)
        assert error["code"] == "validation_error"
        assert set(error["details"]) == {"name", "items.1.n"}
        assert all(isinstance(v, list) and v for v in error["details"].values())
    assert error_of(en)["details"]["name"] == ["This field is required."]
    assert error_of(pl)["details"]["name"] == ["To pole jest wymagane."]
    assert error_of(en)["details"]["items.1.n"] != error_of(pl)["details"]["items.1.n"]
    assert error_of(en)["message"] == "This field is required."


@pytest.mark.urls(URLS)
@pytest.mark.parametrize(
    ("wait", "expected"),
    [
        ("1", "Zbyt wiele żądań. Spróbuj ponownie za 1 sekundę."),
        ("2", "Zbyt wiele żądań. Spróbuj ponownie za 2 sekundy."),
        ("5", "Zbyt wiele żądań. Spróbuj ponownie za 5 sekund."),
        ("12", "Zbyt wiele żądań. Spróbuj ponownie za 12 sekund."),
        ("22", "Zbyt wiele żądań. Spróbuj ponownie za 22 sekundy."),
    ],
)
def test_429_polish_plurals(client, wait, expected):
    response = client.get(f"/api/throttle/?wait={wait}", HTTP_ACCEPT_LANGUAGE="pl")
    assert response.status_code == 429
    assert error_of(response)["code"] == "throttled"
    assert error_of(response)["message"] == expected


@pytest.mark.urls(URLS)
@pytest.mark.parametrize(
    ("wait", "expected"),
    [
        ("1", "Too many requests. Try again in 1 second."),
        ("5", "Too many requests. Try again in 5 seconds."),
    ],
)
def test_429_english_plurals(client, wait, expected):
    response = client.get(f"/api/throttle/?wait={wait}", HTTP_ACCEPT_LANGUAGE="en")
    assert error_of(response)["message"] == expected


@pytest.mark.urls(URLS)
def test_429_without_wait_uses_generic_message(client):
    en = error_of(client.get("/api/throttle/", HTTP_ACCEPT_LANGUAGE="en"))
    pl = error_of(client.get("/api/throttle/", HTTP_ACCEPT_LANGUAGE="pl"))
    assert en["message"] == "Too many requests. Try again later."
    assert pl["message"] == "Zbyt wiele żądań. Spróbuj ponownie później."


@pytest.mark.urls(URLS)
@pytest.mark.parametrize(
    ("lang", "message"),
    [("pl", "Wystąpił błąd serwera."), ("en", "A server error occurred.")],
)
def test_500_is_translated(plain_client, lang, message):
    response = plain_client.get("/api/boom/", HTTP_ACCEPT_LANGUAGE=lang)
    assert response.status_code == 500
    assert error_of(response) == {"code": "server_error", "message": message}
    assert response["Content-Language"] == lang


@pytest.mark.urls(URLS)
@pytest.mark.parametrize(
    ("lang", "message"),
    [("pl", "Nieprawidłowe żądanie."), ("en", "Bad request.")],
)
def test_handler400_under_api_uses_contract_format(plain_client, lang, message):
    response = plain_client.get("/api/suspicious/", HTTP_ACCEPT_LANGUAGE=lang)
    assert response.status_code == 400
    assert error_of(response) == {"code": "bad_request", "message": message}
    assert response["Content-Language"] == lang


@pytest.mark.urls(URLS)
@pytest.mark.parametrize(
    ("lang", "message"),
    [
        ("pl", "Nie masz uprawnień do wykonania tej czynności."),
        ("en", "You do not have permission to perform this action."),
    ],
)
def test_handler403_under_api_uses_contract_format(plain_client, lang, message):
    response = plain_client.get("/api/denied/", HTTP_ACCEPT_LANGUAGE=lang)
    assert response.status_code == 403
    assert error_of(response) == {"code": "permission_denied", "message": message}


@pytest.mark.urls(URLS)
@pytest.mark.parametrize("path", ["/other/suspicious/", "/other/denied/"])
def test_handlers_outside_api_use_django_default(plain_client, path):
    response = plain_client.get(path)
    assert response.status_code in (400, 403)
    assert response["Content-Type"].startswith("text/html")
    assert response["Content-Language"] == "pl"


@pytest.mark.urls(URLS)
def test_non_api_response_gets_headers(plain_client):
    response = plain_client.get("/plain/", HTTP_ACCEPT_LANGUAGE="en-GB")
    assert response["Content-Language"] == "en"
    assert "Accept-Language" in response["Vary"]


# --- TranslatedModelSerializer --------------------------------------------------------------


class I18nProbe(models.Model):
    name = models.CharField(max_length=50, blank=True, default="")
    note = models.CharField(max_length=50, blank=True, default="")
    price = models.IntegerField(default=0)

    class Meta:
        app_label = "core"

    def __str__(self):
        return self.name


class I18nProbeOptions(TranslationOptions):
    fields = ("name", "note")


translator.register(I18nProbe, I18nProbeOptions)


class ProbeSerializer(TranslatedModelSerializer):
    class Meta:
        model = I18nProbe
        fields = "__all__"


@pytest.fixture
def probe_table(db):
    with connection.schema_editor() as editor:
        editor.create_model(I18nProbe)
    yield
    with connection.schema_editor() as editor:
        editor.delete_model(I18nProbe)


def test_translation_column_names(probe_table):
    assert translation_column_names(I18nProbe) == {"name_pl", "name_en", "note_pl", "note_en"}


def test_translation_column_names_for_unregistered_model():
    assert translation_column_names(Group) == set()


def test_serializer_returns_one_string_in_request_language(probe_table):
    obj = I18nProbe.objects.create(name_pl="Bilet", name_en="Ticket", price=3)
    with translation.override("en"):
        data = ProbeSerializer(obj).data
    assert data["name"] == "Ticket"
    with translation.override("pl"):
        data = ProbeSerializer(obj).data
    assert data["name"] == "Bilet"
    assert data["price"] == 3


def test_serializer_empty_translation_falls_back_to_polish(probe_table):
    obj = I18nProbe.objects.create(name_pl="Bilet", name_en="")
    with translation.override("en"):
        data = ProbeSerializer(obj).data
    assert data["name"] == "Bilet"


def test_serializer_never_outputs_per_language_columns(probe_table):
    obj = I18nProbe.objects.create(name_pl="Bilet", name_en="Ticket")
    data = ProbeSerializer(obj).data
    assert not {"name_pl", "name_en", "note_pl", "note_en"} & set(data)
    assert {"id", "name", "note", "price"} <= set(data)
