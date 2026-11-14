"""URL configuration with small views that trigger each error type (tests only)."""

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import HttpResponse
from django.urls import path
from rest_framework import serializers
from rest_framework.exceptions import Throttled
from rest_framework.response import Response
from rest_framework.views import APIView

handler400 = "core.views.bad_request"
handler403 = "core.views.permission_denied"
handler404 = "core.views.not_found"
handler500 = "core.views.server_error"


class ItemSerializer(serializers.Serializer):
    n = serializers.IntegerField()


class PayloadSerializer(serializers.Serializer):
    name = serializers.CharField()
    items = ItemSerializer(many=True)


class EchoView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        serializer = PayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class ThrottleView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        wait = request.query_params.get("wait")
        raise Throttled(wait=float(wait) if wait else None)


class BoomView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        raise RuntimeError("boom")


def plain_suspicious(request):
    raise SuspiciousOperation("bad")


def plain_denied(request):
    raise PermissionDenied


def plain_ok(request):
    return HttpResponse("ok")


urlpatterns = [
    path("api/echo/", EchoView.as_view()),
    path("api/throttle/", ThrottleView.as_view()),
    path("api/boom/", BoomView.as_view()),
    path("api/suspicious/", plain_suspicious),
    path("api/denied/", plain_denied),
    path("other/suspicious/", plain_suspicious),
    path("other/denied/", plain_denied),
    path("plain/", plain_ok),
]
