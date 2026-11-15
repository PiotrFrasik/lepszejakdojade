"""Tickets API (docs/api.md, "Tickets (#14)"). No auth, read-only."""

from __future__ import annotations

from django.utils.cache import patch_cache_control
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from cities.registry import City, get_city
from cities.views import ACCEPT_LANGUAGE
from core.serializers import ErrorSerializer

from . import services
from .serializers import (
    TicketCatalogueQuerySerializer,
    TicketCatalogueSerializer,
    TicketSuggestionSerializer,
    TicketSuggestRequestSerializer,
)

CITY_PARAM = OpenApiParameter("city", str, OpenApiParameter.PATH, description="City id.")
REDUCED_PARAM = OpenApiParameter(
    "reduced",
    str,
    OpenApiParameter.QUERY,
    required=False,
    enum=["true", "false"],
    description="Only reduced (`true`) or only standard (`false`) fares. Default: both.",
)
CATALOGUE_MAX_AGE = 300


def _city(city_id: str) -> City:
    city = get_city(city_id)
    if city is None:
        raise NotFound(_("City not found."))
    return city


class _PublicView(APIView):
    authentication_classes: list = []
    permission_classes: list = []


class TicketCatalogueView(_PublicView):
    """Whole ticket catalogue of a city (active tickets only). Not paginated."""

    @extend_schema(
        operation_id="tickets_list",
        summary="List tickets",
        parameters=[CITY_PARAM, REDUCED_PARAM, ACCEPT_LANGUAGE],
        responses={200: TicketCatalogueSerializer, 400: ErrorSerializer, 404: ErrorSerializer},
        tags=["tickets"],
    )
    def get(self, request: Request, city: str) -> Response:
        found = _city(city)
        query = TicketCatalogueQuerySerializer(data=request.query_params)
        if not query.is_valid():
            raise ValidationError(query.errors)
        reduced = query.validated_data.get("reduced")
        tickets = services.catalogue(found, None if reduced is None else reduced == "true")
        data = {"zones": found.ticket_zones, "tickets": tickets}
        response = Response(TicketCatalogueSerializer(data).data)
        patch_cache_control(response, max_age=CATALOGUE_MAX_AGE)
        return response


class TicketSuggestView(_PublicView):
    """Cheapest single or time ticket that covers one journey."""

    @extend_schema(
        operation_id="tickets_suggest",
        summary="Suggest a ticket for a journey",
        parameters=[CITY_PARAM, ACCEPT_LANGUAGE],
        request=TicketSuggestRequestSerializer,
        responses={200: TicketSuggestionSerializer, 400: ErrorSerializer, 404: ErrorSerializer},
        tags=["tickets"],
    )
    def post(self, request: Request, city: str) -> Response:
        found = _city(city)
        serializer = TicketSuggestRequestSerializer(data=request.data, context={"city": found})
        if not serializer.is_valid():
            raise ValidationError(serializer.errors)
        params = serializer.validated_data
        suggestion = services.suggest(
            found,
            duration_seconds=params["duration_seconds"],
            transfers=params["transfers"],
            zones=params["zones"],
            reduced=params["reduced"],
        )
        return Response(TicketSuggestionSerializer(suggestion).data)
