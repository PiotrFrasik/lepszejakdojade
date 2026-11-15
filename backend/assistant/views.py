"""Chat API (docs/api.md, "POST /api/v1/assistant/chat/"). No auth, rate-limited per IP."""

from __future__ import annotations

from django.utils import translation
from django.utils.translation import gettext_lazy
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from cities.registry import get_city
from cities.views import ACCEPT_LANGUAGE
from core.serializers import ErrorSerializer

from . import chat
from .serializers import ChatRequestSerializer, ChatResponseSerializer
from .throttling import ChatDayThrottle, ChatMinuteThrottle, RateLimited


class AssistantUnavailableError(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "assistant_unavailable"
    default_detail = gettext_lazy("The assistant is unavailable right now. Try again later.")


class ChatView(APIView):
    """One assistant answer for a conversation kept by the client."""

    authentication_classes: list = []
    permission_classes: list = []
    throttle_classes = [ChatMinuteThrottle, ChatDayThrottle]

    def throttled(self, request, wait):
        raise RateLimited(wait)

    @extend_schema(
        operation_id="assistant_chat",
        summary="Chat with the assistant",
        description="Stateless: send the whole conversation (max 20 messages). The answer is "
        "in the negotiated language (Accept-Language). Cards are built only from tool results.",
        parameters=[ACCEPT_LANGUAGE],
        request=ChatRequestSerializer,
        responses={
            200: ChatResponseSerializer,
            400: ErrorSerializer,
            429: OpenApiResponse(
                ErrorSerializer, description="Rate limited; see the Retry-After header."
            ),
            503: ErrorSerializer,
        },
        tags=["assistant"],
    )
    def post(self, request: Request) -> Response:
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            raise ValidationError(serializer.errors)
        data = serializer.validated_data
        language = getattr(request, "LANGUAGE_CODE", None) or translation.get_language()
        try:
            result = chat.answer(get_city(data["city"]), data["messages"], language)
        except chat.AssistantUnavailable:
            raise AssistantUnavailableError() from None
        return Response(result)
