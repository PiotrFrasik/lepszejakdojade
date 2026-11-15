"""Journey search API (docs/api.md, "POST /api/v1/cities/{city}/journeys/search/"). No auth."""

from __future__ import annotations

from datetime import datetime

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from cities.registry import City, get_city
from cities.views import ACCEPT_LANGUAGE
from core.serializers import ErrorSerializer
from timetable.lines import Feeds

from . import services
from .otp import OtpUnavailable
from .serializers import JourneySearchRequestSerializer, JourneySearchResponseSerializer

CITY_PARAM = OpenApiParameter("city", str, OpenApiParameter.PATH, description="City id.")


class JourneyPlannerUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "journey_planner_unavailable"
    default_detail = gettext_lazy("The journey planner is unavailable. Try again later.")


def _resolve_place(
    feeds: Feeds, bbox, data: dict, field: str, errors: dict
) -> services.Place | None:
    """A Place from validated request data; records a field error and returns None if invalid."""
    name = (data.get("name") or "").strip() or None
    if "stop_id" in data:
        stop = services.resolve_stop(feeds, data["stop_id"])
        if stop is None:
            errors[field] = {"stop_id": [_("Unknown stop.")]}
            return None
        return services.Place(name=name or stop.name or None, lat=stop.point.y, lon=stop.point.x)
    if bbox is not None and not services.in_bbox(bbox, data["lat"], data["lon"]):
        errors[field] = [_("This point is outside the city's area.")]
        return None
    return services.Place(name=name, lat=data["lat"], lon=data["lon"])


class JourneySearchView(APIView):
    """Journey planning A to B with walk and bike comparison."""

    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(
        operation_id="journeys_search",
        summary="Search journeys",
        parameters=[CITY_PARAM, ACCEPT_LANGUAGE],
        request=JourneySearchRequestSerializer,
        responses={
            200: JourneySearchResponseSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
            503: ErrorSerializer,
        },
        tags=["journeys"],
    )
    def post(self, request: Request, city: str) -> Response:
        found = get_city(city)
        if found is None:
            raise NotFound(_("City not found."))
        serializer = JourneySearchRequestSerializer(data=request.data)
        if not serializer.is_valid():
            raise ValidationError(serializer.errors)
        params = serializer.validated_data

        feeds = Feeds(found)
        origin, destination = self._places(found, feeds, params)
        when = self._when(found, params.get("time"))
        preferences = services.Preferences(**params.get("preferences", {}))
        try:
            data = services.search(
                found, feeds, origin, destination, when, params["time_mode"], preferences
            )
        except OtpUnavailable:
            raise JourneyPlannerUnavailable() from None
        return Response(JourneySearchResponseSerializer(data).data)

    @staticmethod
    def _places(city: City, feeds: Feeds, params: dict) -> tuple[services.Place, services.Place]:
        needs_bbox = "stop_id" not in params["from"] or "stop_id" not in params["to"]
        bbox = services.city_bbox(city, feeds) if needs_bbox else None
        errors: dict = {}
        origin = _resolve_place(feeds, bbox, params["from"], "from", errors)
        destination = _resolve_place(feeds, bbox, params["to"], "to", errors)
        if errors:
            raise ValidationError(errors)
        if (round(origin.lat, 6), round(origin.lon, 6)) == (
            round(destination.lat, 6),
            round(destination.lon, 6),
        ):
            raise ValidationError(
                {"non_field_errors": [_("The start and the destination must be different.")]}
            )
        return origin, destination

    @staticmethod
    def _when(city: City, value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(city.zoneinfo)
        if value.tzinfo is None:
            return value.replace(tzinfo=city.zoneinfo)
        return value.astimezone(city.zoneinfo)
