"""Download a static GTFS feed to a temporary file, with conditional GET and sha256.

Settings (all optional, defaults in brackets):
- ``TRANSIT_GTFS_HTTP_TIMEOUT`` [120] seconds per socket operation.
- ``TRANSIT_GTFS_MAX_BYTES`` [1 GB] upper bound for one download.
- ``TRANSIT_GTFS_DOWNLOAD_MAX_SECONDS`` [900] overall deadline for one download, checked
  between chunks (a server trickling bytes never trips the per-socket timeout).
"""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

# Generic client name: no project or personal details are sent to publishers.
USER_AGENT = "gtfs-importer/1.0"
CHUNK_SIZE = 256 * 1024


class DownloadError(Exception):
    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


@dataclass
class FetchedFeed:
    """Result of a download. ``path`` is None when the server answered 304."""

    path: Path | None
    not_modified: bool = False
    sha256: str = ""
    size_bytes: int | None = None
    etag: str = ""
    last_modified: str = ""
    http_status: int | None = None


def download_feed(url: str, dest: Path, etag: str = "", last_modified: str = "") -> FetchedFeed:
    """Download ``url`` into the file ``dest``. Raises DownloadError.

    ``etag`` / ``last_modified`` from the previous download make the request conditional;
    a 304 answer returns ``FetchedFeed(path=None, not_modified=True)``.
    """
    timeout = getattr(settings, "TRANSIT_GTFS_HTTP_TIMEOUT", 120)
    max_bytes = getattr(settings, "TRANSIT_GTFS_MAX_BYTES", 1024 * 1024 * 1024)
    max_seconds = getattr(settings, "TRANSIT_GTFS_DOWNLOAD_MAX_SECONDS", 900)
    deadline = time.monotonic() + max_seconds
    headers = {"User-Agent": USER_AGENT, "Accept": "application/zip, */*"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    request = urllib.request.Request(url, headers=headers)
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            status = response.status
            response_etag = response.headers.get("ETag", "") or ""
            response_modified = response.headers.get("Last-Modified", "") or ""
            with open(dest, "wb") as out:
                while chunk := response.read(CHUNK_SIZE):
                    if time.monotonic() > deadline:
                        raise DownloadError(
                            f"download took longer than {max_seconds} seconds", status
                        )
                    size += len(chunk)
                    if size > max_bytes:
                        raise DownloadError(f"feed larger than {max_bytes} bytes", status)
                    digest.update(chunk)
                    out.write(chunk)
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return FetchedFeed(path=None, not_modified=True, http_status=304)
        raise DownloadError(f"HTTP {exc.code}", exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise DownloadError(f"network error: {reason}") from exc
    if size == 0:
        raise DownloadError("empty response", status)
    return FetchedFeed(
        path=dest,
        sha256=digest.hexdigest(),
        size_bytes=size,
        etag=response_etag,
        last_modified=response_modified,
        http_status=status,
    )


def local_feed(path: Path) -> FetchedFeed:
    """Describe a local zip file or GTFS directory like a download (for ``--file``)."""
    path = Path(path)
    digest = hashlib.sha256()
    size = 0
    if path.is_dir():
        files = sorted(p for p in path.iterdir() if p.is_file())
    elif path.is_file():
        files = [path]
    else:
        raise DownloadError(f"no such file or directory: {path}")
    for file in files:
        if path.is_dir():
            digest.update(file.name.encode() + b"\0")
        with open(file, "rb") as handle:
            while chunk := handle.read(CHUNK_SIZE):
                size += len(chunk)
                digest.update(chunk)
    return FetchedFeed(path=path, sha256=digest.hexdigest(), size_bytes=size)
