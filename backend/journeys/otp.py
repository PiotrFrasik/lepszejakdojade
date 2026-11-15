"""Minimal client for the OpenTripPlanner 2 GTFS GraphQL API (``/otp/gtfs/v1``).

Every failure (no URL configured, network error, timeout, HTTP error, invalid JSON,
GraphQL ``errors``) raises ``OtpUnavailable``. Details are logged, never shown to clients.
"""

from __future__ import annotations

import http.client
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

GRAPHQL_PATH = "/otp/gtfs/v1"


class OtpUnavailable(Exception):
    """OTP is not configured, unreachable, too slow or returned an error."""


def graphql(base_url: str | None, query: str, variables: dict) -> dict:
    """Run one GraphQL query and return its ``data``."""
    if not base_url:
        raise OtpUnavailable("OTP URL not configured")
    url = base_url.rstrip("/") + GRAPHQL_PATH
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.OTP_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    # URLError, HTTPError, timeouts, bad JSON, truncated or malformed HTTP responses
    except (OSError, ValueError, http.client.HTTPException) as exc:
        logger.warning("OTP request to %s failed: %s", url, exc)
        raise OtpUnavailable(str(exc)) from exc
    if not isinstance(payload, dict):
        logger.warning("OTP request to %s returned a non-object body", url)
        raise OtpUnavailable("unexpected response")
    if payload.get("errors"):
        logger.warning("OTP request to %s returned errors: %s", url, payload["errors"])
        raise OtpUnavailable("GraphQL errors")
    data = payload.get("data")
    if not isinstance(data, dict):
        logger.warning("OTP request to %s returned no data", url)
        raise OtpUnavailable("no data")
    return data
