"""Date range, default direction and OpenAPI schema checks (review fixes for #10)."""

import io

import pytest
from django.core.management import call_command

from .conftest import MAIN, MONDAY

pytestmark = pytest.mark.django_db

LINE = f"{MAIN}:R10"
ONLY_ONE = f"{MAIN}:RD1"
OUT_OF_RANGE = ["0001-01-01", "9999-12-31", "9998-12-31"]


def paths(line=LINE):
    return [
        f"lines/{line}/route/",
        f"lines/{line}/stops/{MAIN}:S1/timetable/",
        f"trips/{MAIN}:m1/",
    ]


@pytest.mark.parametrize("value", OUT_OF_RANGE)
@pytest.mark.parametrize("index", [0, 1, 2])
def test_out_of_range_date_is_400(api, dataset, value, index):
    for lang, message in (
        ("en", "Date is out of range."),
        ("pl", "Data jest poza obsługiwanym zakresem."),
    ):
        response = api.get(paths()[index], lang=lang, date=value)
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert error["message"] == message
        assert "date" in error["details"]


def test_line_with_only_direction_one_defaults_to_it(api, dataset):
    route = api.get(f"lines/{ONLY_ONE}/route/", date=MONDAY)
    assert route.status_code == 200
    assert route.json()["direction"] == 1
    assert [d["direction"] for d in route.json()["directions"]] == [1]
    table = api.get(f"lines/{ONLY_ONE}/stops/{MAIN}:S2/timetable/", date=MONDAY)
    assert table.status_code == 200
    assert table.json()["direction"] == 1
    assert [d["time"] for h in table.json()["columns"][0]["hours"] for d in h["departures"]] == [
        "09:30"
    ]


def test_explicit_direction_zero_on_direction_one_only_line_is_404(api, dataset):
    assert api.get(f"lines/{ONLY_ONE}/route/", direction=0, date=MONDAY).status_code == 404
    url = f"lines/{ONLY_ONE}/stops/{MAIN}:S2/timetable/"
    assert api.get(url, direction=0, date=MONDAY).status_code == 404


def test_line_with_both_directions_defaults_to_zero(api, dataset):
    assert api.get(f"lines/{LINE}/route/", date=MONDAY).json()["direction"] == 0
    url = f"lines/{LINE}/stops/{MAIN}:S1/timetable/"
    assert api.get(url, date=MONDAY).json()["direction"] == 0


def test_openapi_schema_has_no_warnings():
    out, err = io.StringIO(), io.StringIO()
    call_command("spectacular", "--validate", "--fail-on-warn", stdout=out, stderr=err)
    assert "/lines/{line_id}/route/" in out.getvalue()
