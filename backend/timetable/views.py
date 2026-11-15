"""Timetable API views (docs/api.md, "Timetable (#10)"). No auth, read-only."""

from __future__ import annotations

from datetime import date, datetime

from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.views import APIView

from cities.registry import VEHICLE_TYPES, City, get_city
from cities.views import ACCEPT_LANGUAGE
from core.serializers import ErrorSerializer

from . import services
from .lines import Feeds, Line, get_line, get_stop, get_trip, lines_by_pk, list_lines
from .serializers import (
    DateQuerySerializer,
    DirectionDateQuerySerializer,
    LineListItemSerializer,
    LineRouteSerializer,
    LinesQuerySerializer,
    StopSearchQuerySerializer,
    StopSearchResultSerializer,
    StopTimetableSerializer,
    TripSerializer,
)
from .stops import search_stops

CITY_PARAM = OpenApiParameter("city", str, OpenApiParameter.PATH, description="City id.")
LINE_PARAM = OpenApiParameter(
    "line_id", str, OpenApiParameter.PATH, description="Line id `{feed_id}:{gtfs_id}`, URL-encoded."
)
STOP_PARAM = OpenApiParameter(
    "stop_id", str, OpenApiParameter.PATH, description="Stop id `{feed_id}:{gtfs_id}`, URL-encoded."
)
TRIP_PARAM = OpenApiParameter(
    "trip_id", str, OpenApiParameter.PATH, description="Trip id `{feed_id}:{gtfs_id}`, URL-encoded."
)
DIRECTION_PARAM = OpenApiParameter(
    "direction",
    int,
    OpenApiParameter.QUERY,
    enum=[0, 1],
    description="Direction. Default: the lowest direction the line has (0 if it exists).",
)
DATE_PARAM = OpenApiParameter(
    "date",
    str,
    OpenApiParameter.QUERY,
    description="Service date YYYY-MM-DD in the city time zone. Default: today there.",
)
VEHICLE_TYPE_PARAM = OpenApiParameter(
    "vehicle_type", str, OpenApiParameter.QUERY, enum=list(VEHICLE_TYPES), required=False
)
Q_PARAM = OpenApiParameter(
    "q",
    str,
    OpenApiParameter.QUERY,
    required=True,
    description="Stop name fragment, at least 2 characters after trimming; case- and "
    "diacritics-insensitive.",
)
ERRORS = {400: ErrorSerializer, 404: ErrorSerializer}


def _query(serializer_class: type[Serializer], request: Request) -> dict:
    serializer = serializer_class(data=request.query_params)
    if not serializer.is_valid():
        raise ValidationError(serializer.errors)
    return serializer.validated_data


def _city(city_id: str) -> City:
    city = get_city(city_id)
    if city is None:
        raise NotFound(_("City not found."))
    return city


def _today(city: City) -> date:
    return datetime.now(city.zoneinfo).date()


def _line(city: City, feeds: Feeds, line_id: str) -> Line:
    line = get_line(city, feeds, line_id)
    if line is None:
        raise NotFound(_("Line not found."))
    return line


def _direction_context(line: Line, direction: int, day: date) -> services.DirectionContext:
    try:
        return services.direction_context(line, direction, day)
    except services.DirectionNotFound:
        raise NotFound(_("This line does not run in this direction.")) from None


class _PublicView(APIView):
    authentication_classes: list = []
    permission_classes: list = []


class LineListView(_PublicView):
    """All lines of a city. Not paginated."""

    @extend_schema(
        operation_id="lines_list",
        summary="List lines",
        parameters=[CITY_PARAM, VEHICLE_TYPE_PARAM, ACCEPT_LANGUAGE],
        responses={200: LineListItemSerializer(many=True), **ERRORS},
        tags=["timetable"],
    )
    def get(self, request: Request, city: str) -> Response:
        found = _city(city)
        params = _query(LinesQuerySerializer, request)
        lines = list_lines(found, Feeds(found), params.get("vehicle_type"))
        return Response(
            LineListItemSerializer([line.list_item() for line in lines], many=True).data
        )


class LineRouteView(_PublicView):
    """Line diagram for one direction."""

    @extend_schema(
        operation_id="lines_route",
        summary="Line route diagram",
        parameters=[CITY_PARAM, LINE_PARAM, DIRECTION_PARAM, DATE_PARAM, ACCEPT_LANGUAGE],
        responses={200: LineRouteSerializer, **ERRORS},
        tags=["timetable"],
    )
    def get(self, request: Request, city: str, line_id: str) -> Response:
        found = _city(city)
        params = _query(DirectionDateQuerySerializer, request)
        feeds = Feeds(found)
        line = _line(found, feeds, line_id)
        day = params.get("date") or _today(found)
        context = _direction_context(line, params.get("direction"), day)
        data = services.build_route(found, feeds, context)
        return Response(LineRouteSerializer(data).data)


class StopTimetableView(_PublicView):
    """Timetable of one line at one stop: weekday, Saturday and Sunday columns."""

    @extend_schema(
        operation_id="lines_stop_timetable",
        summary="Stop timetable of a line",
        parameters=[
            CITY_PARAM,
            LINE_PARAM,
            STOP_PARAM,
            DIRECTION_PARAM,
            DATE_PARAM,
            ACCEPT_LANGUAGE,
        ],
        responses={200: StopTimetableSerializer, **ERRORS},
        tags=["timetable"],
    )
    def get(self, request: Request, city: str, line_id: str, stop_id: str) -> Response:
        found = _city(city)
        params = _query(DirectionDateQuerySerializer, request)
        feeds = Feeds(found)
        line = _line(found, feeds, line_id)
        stop = get_stop(feeds, line, stop_id)
        if stop is None:
            raise NotFound(_("Stop not found."))
        day = params.get("date") or _today(found)
        context = _direction_context(line, params.get("direction"), day)
        if not services.stop_served(line, context.direction, stop):
            raise NotFound(_("This line does not stop here in this direction."))
        data = services.build_timetable(found, feeds, context, stop, day)
        return Response(StopTimetableSerializer(data).data)


class TripView(_PublicView):
    """One trip on one service date with times at every stop."""

    @extend_schema(
        operation_id="trips_retrieve",
        summary="Get trip",
        parameters=[CITY_PARAM, TRIP_PARAM, DATE_PARAM, ACCEPT_LANGUAGE],
        responses={200: TripSerializer, **ERRORS},
        tags=["timetable"],
    )
    def get(self, request: Request, city: str, trip_id: str) -> Response:
        found = _city(city)
        params = _query(DateQuerySerializer, request)
        feeds = Feeds(found)
        trip = get_trip(feeds, trip_id)
        line = None
        if trip is not None:
            line = next(iter(lines_by_pk(found, feeds, [trip.route_id]).values()), None)
        if trip is None or line is None:
            raise NotFound(_("Trip not found."))
        day = params.get("date") or _today(found)
        if not services.trip_runs_on(trip, day):
            raise NotFound(_("This trip does not run on this date."))
        data = services.build_trip(found, line, trip, day)
        return Response(TripSerializer(data).data)


class StopSearchView(_PublicView):
    """Stop name search for autocomplete. Not paginated, at most 20 results."""

    @extend_schema(
        operation_id="stops_search",
        summary="Search stops by name",
        parameters=[CITY_PARAM, Q_PARAM, ACCEPT_LANGUAGE],
        responses={200: StopSearchResultSerializer(many=True), **ERRORS},
        tags=["timetable"],
    )
    def get(self, request: Request, city: str) -> Response:
        found = _city(city)
        params = _query(StopSearchQuerySerializer, request)
        results = search_stops(found, Feeds(found), params["q"])
        return Response(StopSearchResultSerializer(results, many=True).data)
