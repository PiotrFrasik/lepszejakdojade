"""Cities API: public city configuration, translated to the request language."""

from collections import defaultdict

from django.db.models import Q
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import ErrorSerializer
from transit_data.models import FeedVersion

from .registry import all_cities, get_city
from .serializers import CityDetailSerializer, CitySerializer, DataSourcesSerializer

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


class DataSourcesView(APIView):
    """Licence attributions and the age of the static data of every city."""

    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(
        operation_id="data_sources_list",
        summary="List data sources and attributions",
        parameters=[ACCEPT_LANGUAGE],
        responses={200: DataSourcesSerializer},
        tags=["cities"],
    )
    def get(self, request: Request) -> Response:
        cities = all_cities()
        feeds: dict[str, list[FeedVersion]] = defaultdict(list)
        if cities:
            configured = Q()
            for city in cities:
                feed_ids = [feed.id for feed in city.feeds if feed.kind == "gtfs_static"]
                configured |= Q(city_id=city.id, feed_id__in=feed_ids)
            rows = (
                FeedVersion.objects.filter(configured, status=FeedVersion.Status.ACTIVE)
                .only(
                    "city_id",
                    "feed_id",
                    "publisher_name",
                    "last_modified",
                    "downloaded_at",
                    "imported_at",
                    "service_start_date",
                    "service_end_date",
                )
                .order_by("city_id", "feed_id")
            )
            for row in rows:
                feeds[row.city_id].append(row)
        serializer = DataSourcesSerializer({"cities": cities}, context={"feeds": feeds})
        return Response(serializer.data)
