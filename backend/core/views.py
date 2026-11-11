"""Core API views: health check and JSON error handlers."""

import logging

import redis
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views import defaults
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import error_body
from .serializers import HealthSerializer

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_ERROR = "error"


def check_database() -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Health check failed: database")
        return STATUS_ERROR
    return STATUS_OK


def check_redis() -> str:
    timeout = settings.HEALTH_CHECK_TIMEOUT
    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=timeout, socket_timeout=timeout
        )
        try:
            client.ping()
        finally:
            client.close()
    except Exception:
        logger.exception("Health check failed: redis")
        return STATUS_ERROR
    return STATUS_OK


class HealthView(APIView):
    """Liveness and dependency check. No auth, not paginated, not translated."""

    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(
        operation_id="health",
        summary="Health check",
        responses={200: HealthSerializer, 503: HealthSerializer},
        tags=["health"],
    )
    def get(self, request: Request) -> Response:
        checks = {"database": check_database(), "redis": check_redis()}
        healthy = all(value == STATUS_OK for value in checks.values())
        body = {
            "status": STATUS_OK if healthy else STATUS_ERROR,
            "checks": checks,
            "version": settings.APP_VERSION,
        }
        return Response(
            body,
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def _is_api_request(request) -> bool:
    return request.path.startswith("/api/")


def not_found(request, exception=None):
    """404 handler: contract error format for /api/ paths, Django default elsewhere."""
    if _is_api_request(request):
        return JsonResponse(error_body("not_found", _("Not found.")), status=404)
    return defaults.page_not_found(request, exception)


def server_error(request):
    """500 handler: contract error format for /api/ paths, Django default elsewhere."""
    if _is_api_request(request):
        return JsonResponse(error_body("server_error", _("A server error occurred.")), status=500)
    return defaults.server_error(request)
