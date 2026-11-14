"""Static GTFS download: conditional GET, size cap, errors. HTTP is always mocked."""

from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest

from cities.registry import get_city
from transit_data.models import FeedVersion, Stop
from transit_data.static_gtfs import download
from transit_data.static_gtfs.download import DownloadError, download_feed, local_feed
from transit_data.static_gtfs.pipeline import Outcome, import_feed

from .gtfs_support import CITY, FEED, FEED_URL, FakeServer, copy_feed, zip_directory


@pytest.fixture
def server(tmp_path, monkeypatch):
    srv = FakeServer(zip_directory(copy_feed(tmp_path / "served")), etag='"v1"')
    monkeypatch.setattr(download.urllib.request, "urlopen", srv)
    return srv


def feed_obj():
    city = get_city(CITY)
    return city, next(f for f in city.feeds if f.id == FEED)


# ------------------------------------------------------------------- download_feed


def test_download_stores_file_hash_and_validators(tmp_path, server):
    server.last_modified = "Wed, 01 Jan 2026 00:00:00 GMT"
    dest = tmp_path / "out.zip"
    fetched = download_feed(FEED_URL, dest)
    assert fetched.path == dest
    assert dest.read_bytes() == server.body
    assert fetched.size_bytes == len(server.body)
    assert len(fetched.sha256) == 64
    assert fetched.etag == '"v1"'
    assert fetched.last_modified == "Wed, 01 Jan 2026 00:00:00 GMT"
    assert not fetched.not_modified


def test_first_request_is_unconditional(tmp_path, server):
    download_feed(FEED_URL, tmp_path / "out.zip")
    request = server.requests[0]
    assert request.get_header("If-none-match") is None
    assert request.get_header("If-modified-since") is None
    assert request.get_header("User-agent")


def test_conditional_request_sends_etag_and_last_modified(tmp_path, server):
    download_feed(
        FEED_URL,
        tmp_path / "out.zip",
        etag='"old"',
        last_modified="Wed, 01 Jan 2026 00:00:00 GMT",
    )
    request = server.requests[0]
    assert request.get_header("If-none-match") == '"old"'
    assert request.get_header("If-modified-since") == "Wed, 01 Jan 2026 00:00:00 GMT"


def test_304_means_not_modified_and_writes_nothing(tmp_path, server):
    dest = tmp_path / "out.zip"
    fetched = download_feed(FEED_URL, dest, etag='"v1"')
    assert fetched.not_modified
    assert fetched.path is None
    assert not dest.exists()


def test_size_cap_is_enforced(tmp_path, server, settings):
    settings.TRANSIT_GTFS_MAX_BYTES = 100
    assert len(server.body) > 100
    with pytest.raises(DownloadError, match="larger than"):
        download_feed(FEED_URL, tmp_path / "out.zip")


def test_body_exactly_at_cap_is_accepted(tmp_path, server, settings):
    settings.TRANSIT_GTFS_MAX_BYTES = len(server.body)
    assert download_feed(FEED_URL, tmp_path / "out.zip").size_bytes == len(server.body)


def test_http_error_raises_download_error_with_status(tmp_path, server):
    server.error = urllib.error.HTTPError(FEED_URL, 503, "Unavailable", {}, None)
    with pytest.raises(DownloadError) as excinfo:
        download_feed(FEED_URL, tmp_path / "out.zip")
    assert excinfo.value.http_status == 503


def test_network_error_raises_download_error(tmp_path, server):
    server.error = urllib.error.URLError("connection refused")
    with pytest.raises(DownloadError, match="network error"):
        download_feed(FEED_URL, tmp_path / "out.zip")


def test_timeout_raises_download_error(tmp_path, server):
    server.error = TimeoutError("timed out")
    with pytest.raises(DownloadError):
        download_feed(FEED_URL, tmp_path / "out.zip")


def test_empty_response_is_an_error(tmp_path, server):
    server.body = b""
    with pytest.raises(DownloadError, match="empty"):
        download_feed(FEED_URL, tmp_path / "out.zip")


def test_local_feed_hash_is_stable_and_content_dependent(tmp_path):
    a = copy_feed(tmp_path / "a")
    b = copy_feed(tmp_path / "b")
    assert local_feed(a).sha256 == local_feed(b).sha256
    (b / "routes.txt").write_text("changed", encoding="utf-8")
    assert local_feed(a).sha256 != local_feed(b).sha256


def test_local_feed_missing_path_raises(tmp_path):
    with pytest.raises(DownloadError):
        local_feed(Path(tmp_path / "nope"))


# ------------------------------------------------------------- through the pipeline


@pytest.mark.django_db
@pytest.mark.usefixtures("gtfs_city")
class TestPipelineDownload:
    def test_import_from_url_stores_validators(self, server):
        server.last_modified = "Wed, 01 Jan 2026 00:00:00 GMT"
        result = import_feed(*feed_obj())
        assert result.outcome == Outcome.IMPORTED, result.message
        version = FeedVersion.objects.get(pk=result.feed_version_id)
        assert version.source_url == FEED_URL
        assert version.etag == '"v1"'
        assert version.last_modified == "Wed, 01 Jan 2026 00:00:00 GMT"
        assert version.size_bytes == len(server.body)
        assert len(version.sha256) == 64

    def test_304_does_nothing_but_move_checked_at(self, server):
        first = import_feed(*feed_obj())
        version = FeedVersion.objects.get(pk=first.feed_version_id)
        before = version.checked_at
        second = import_feed(*feed_obj())
        assert second.outcome == Outcome.UNCHANGED
        assert "304" in second.message
        assert server.requests[1].get_header("If-none-match") == '"v1"'
        assert FeedVersion.objects.count() == 1
        version.refresh_from_db()
        assert version.status == FeedVersion.Status.ACTIVE
        assert version.checked_at > before
        assert Stop.objects.count() == 6

    def test_same_content_without_etag_support_is_unchanged_by_sha256(self, server):
        server.etag = ""
        import_feed(*feed_obj())
        again = import_feed(*feed_obj())
        assert again.outcome == Outcome.UNCHANGED
        assert "sha256" in again.message
        assert FeedVersion.objects.count() == 1

    def test_force_skips_conditional_get(self, server):
        import_feed(*feed_obj())
        forced = import_feed(*feed_obj(), force=True)
        assert forced.outcome == Outcome.IMPORTED
        assert server.requests[1].get_header("If-none-match") is None

    def test_oversized_download_fails_and_is_recorded(self, server, settings):
        settings.TRANSIT_GTFS_MAX_BYTES = 100
        result = import_feed(*feed_obj())
        assert result.outcome == Outcome.FAILED
        version = FeedVersion.objects.get(pk=result.feed_version_id)
        assert version.status == FeedVersion.Status.FAILED
        assert "download failed" in version.error
        assert Stop.objects.count() == 0

    def test_failed_download_keeps_active_version(self, server):
        import_feed(*feed_obj())
        server.error = urllib.error.HTTPError(FEED_URL, 500, "Boom", {}, None)
        result = import_feed(*feed_obj())
        assert result.outcome == Outcome.FAILED
        active = FeedVersion.objects.get(status=FeedVersion.Status.ACTIVE)
        assert Stop.objects.filter(feed_version=active).count() == 6

    def test_uncompressed_size_limit_rejects_zip_bomb(self, server, settings):
        # The cap is checked against the sizes declared in the zip directory. That is a real
        # limit, not just advisory: ZipExtFile stops reading at the declared file_size and
        # verifies the CRC, so an archive that lies about its size cannot unpack more than
        # it declared (it fails with BadZipFile instead).
        settings.TRANSIT_GTFS_MAX_UNCOMPRESSED_BYTES = 100
        result = import_feed(*feed_obj())
        assert result.outcome == Outcome.FAILED
        assert "exceeds the limit" in result.message
        assert Stop.objects.count() == 0
