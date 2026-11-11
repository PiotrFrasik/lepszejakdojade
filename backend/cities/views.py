"""Cities API: public city configuration, translated to the request language."""

from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import ErrorSerializer

from .registry import all_cities, get_city
from .serializers import CityDetailSerializer, CitySerializer

ACCEPT_LANGUAGE = OpenApiParameter(
    name="Accept-Language",
    type=str,
    location=OpenApiParameter.HEADER,
    required=False,
    enum=["pl", "en"],
    description="Language of translated fields. Default: pl.",
)


class CityListView(APIView):
    """All configured cities. No auth, not paginated, ordered by id."""

    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(
        operation_id="cities_list",
        summary="List cities",
        parameters=[ACCEPT_LANGUAGE],
        responses={200: CitySerializer(many=True)},
        tags=["cities"],
    )
    def get(self, request: Request) -> Response:
        return Response(CitySerializer(all_cities(), many=True).data)


class CityDetailView(APIView):
    """One city with its vehicle types, line groups and realtime capabilities."""

    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(
        operation_id="cities_retrieve",
        summary="Get city",
        parameters=[
            OpenApiParameter("city", str, OpenApiParameter.PATH, description="City id."),
            ACCEPT_LANGUAGE,
        ],
        responses={200: CityDetailSerializer, 404: ErrorSerializer},
        tags=["cities"],
    )
    def get(self, request: Request, city: str) -> Response:
        found = get_city(city)
        if found is None:
            raise NotFound(_("City not found."))
        return Response(CityDetailSerializer(found).data)
