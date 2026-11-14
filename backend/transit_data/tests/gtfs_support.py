"""Helpers for the static GTFS import tests (no network, no shipped feed URLs)."""

from __future__ import annotations

import io
import shutil
import urllib.error
import zipfile
from collections.abc import Callable
from pathlib import Path

FIXTURE_FEED = Path(__file__).resolve().parent.parent / "fixtures" / "gtfs" / "minimal"

CITY = "gtfsville"
FEED = "gv_main"
FEED_URL = "http://gtfsville.invalid/main.zip"


def copy_feed(dest: Path, mutations: dict[str, Callable[[str], str] | None] | None = None) -> Path:
    """Copy the minimal fixture feed to ``dest`` and apply per-file mutations.

    ``mutations`` maps a file name to a text transform, or to None to delete the file.
    """
    shutil.copytree(FIXTURE_FEED, dest)
    for name, transform in (mutations or {}).items():
        path = dest / name
        if transform is None:
            path.unlink()
        else:
            path.write_text(transform(path.read_text(encoding="utf-8")), encoding="utf-8")
    return dest


def replace_in(old: str, new: str) -> Callable[[str], str]:
    def transform(text: str) -> str:
        assert old in text, f"{old!r} not found in fixture text"
        return text.replace(old, new)

    return transform


def zip_directory(directory: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.iterdir()):
            archive.write(path, path.name)
    return buffer.getvalue()


class FakeResponse:
    """Minimal stand-in for the object returned by ``urllib.request.urlopen``."""

    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        self._stream = io.BytesIO(body)
        self.status = status
        self.headers = headers or {}

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeServer:
    """Replacement for ``urlopen`` that records requests and serves one body.

    Answers 304 when the request carries ``If-None-Match`` equal to ``etag``.
    """

    def __init__(self, body: bytes = b"", etag: str = '"v1"', last_modified: str = ""):
        self.body = body
        self.etag = etag
        self.last_modified = last_modified
        self.requests: list = []
        self.error: Exception | None = None

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if request.get_header("If-none-match") and request.get_header("If-none-match") == self.etag:
            raise urllib.error.HTTPError(request.full_url, 304, "Not Modified", {}, None)
        headers = {}
        if self.etag:
            headers["ETag"] = self.etag
        if self.last_modified:
            headers["Last-Modified"] = self.last_modified
        return FakeResponse(self.body, headers=headers)
