"""Stop name search for the journey form autocomplete (docs/api.md, "Stops (#59)").

Platforms of the city's active static feed versions are grouped by name (same name within
TRANSFER_RADIUS_M, single linkage) and matched in memory against a normalised name
(case-folded, diacritics removed). A city has a few thousand platforms, so the groups are
built once per set of active feed versions and cached; feed versions are immutable, so a
new import changes the cache key.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import NamedTuple

from django.core.cache import cache

from cities.registry import VEHICLE_TYPES, City
from transit_data.models import LocationType, Stop

from .lines import Feeds, lines_by_pk, make_id
from .services import TRANSFER_RADIUS_M, _routes_at_stops

MAX_RESULTS = 20
MIN_QUERY_LENGTH = 2
_GROUPS_CACHE_SECONDS = 24 * 3600

_EARTH_RADIUS_M = 6_371_000
# Letters that Unicode does not decompose into base letter + combining mark.
_EXTRA_FOLDS = str.maketrans({"ł": "l", "ø": "o", "đ": "d", "æ": "ae", "œ": "oe"})
_SPACES_RE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Case- and diacritics-insensitive form of a name or query (whitespace collapsed)."""
    folded = unicodedata.normalize("NFKD", text.casefold().translate(_EXTRA_FOLDS))
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return _SPACES_RE.sub(" ", stripped).strip()


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


class Platform(NamedTuple):
    pk: int
    stop_id: str
    lat: float
    lon: float


class StopGroup(NamedTuple):
    key: str  # normalised name
    name: str
    lat: float
    lon: float
    stop_id: str  # representative platform: the one closest to the centroid
    platforms: tuple[Platform, ...]


def _cluster(platforms: list[Platform]) -> list[list[Platform]]:
    """Single-linkage clusters of same-name platforms within TRANSFER_RADIUS_M."""
    parent = list(range(len(platforms)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(platforms):
        for j in range(i + 1, len(platforms)):
            b = platforms[j]
            if _distance_m(a.lat, a.lon, b.lat, b.lon) <= TRANSFER_RADIUS_M:
                parent[find(i)] = find(j)
    clusters: dict[int, list[Platform]] = {}
    for i, platform in enumerate(platforms):
        clusters.setdefault(find(i), []).append(platform)
    return list(clusters.values())


def _group(name: str, members: list[Platform]) -> StopGroup:
    members = sorted(members, key=lambda p: p.stop_id)
    lat = sum(p.lat for p in members) / len(members)
    lon = sum(p.lon for p in members) / len(members)
    representative = min(members, key=lambda p: (_distance_m(lat, lon, p.lat, p.lon), p.stop_id))
    return StopGroup(
        key=normalise(name),
        name=name,
        lat=round(lat, 6),
        lon=round(lon, 6),
        stop_id=representative.stop_id,
        platforms=tuple(members),
    )


def build_groups(feeds: Feeds) -> list[StopGroup]:
    """All named platforms of the active versions, grouped by name and distance, sorted
    by normalised name."""
    rows = Stop.objects.filter(
        feed_version_id__in=feeds.version_ids,
        location_type=LocationType.STOP,
        point__isnull=False,
    ).values_list("id", "feed_version_id", "gtfs_id", "name", "point")
    by_name: dict[str, list[Platform]] = {}
    for pk, version_id, gtfs_id, raw_name, point in rows:
        name = raw_name.strip()
        if not name:
            continue
        stop_id = make_id(feeds.feed_by_version[version_id], gtfs_id)
        by_name.setdefault(name, []).append(Platform(pk, stop_id, point.y, point.x))
    groups = [
        _group(name, members)
        for name, platforms in by_name.items()
        for members in _cluster(platforms)
    ]
    groups.sort(key=lambda g: (g.key, g.name, g.stop_id))
    return groups


def city_groups(city: City, feeds: Feeds) -> list[StopGroup]:
    versions = ",".join(str(v) for v in sorted(feeds.version_ids))
    key = f"timetable:stop_groups:{city.id}:{versions}"
    groups = cache.get(key)
    if groups is None:
        groups = build_groups(feeds)
        cache.set(key, groups, _GROUPS_CACHE_SECONDS)
    return groups


def _is_word_prefix(key: str, query: str) -> bool:
    """True when ``query`` starts at the beginning of a word of ``key``."""
    start = key.find(query)
    while start != -1:
        if start == 0 or not key[start - 1].isalnum():
            return True
        start = key.find(query, start + 1)
    return False


def search_stops(city: City, feeds: Feeds, q: str) -> list[dict]:
    """Up to MAX_RESULTS stop groups whose name contains ``q``: word-prefix matches first,
    then other substring matches, each sorted by name."""
    query = normalise(q)
    prefix: list[StopGroup] = []
    other: list[StopGroup] = []
    for group in city_groups(city, feeds):  # sorted by name
        if query in group.key:
            (prefix if _is_word_prefix(group.key, query) else other).append(group)
            if len(prefix) >= MAX_RESULTS:
                break
    groups = (prefix + other)[:MAX_RESULTS]

    stop_pks = {p.pk for group in groups for p in group.platforms}
    routes = _routes_at_stops(stop_pks)
    lines = lines_by_pk(city, feeds, set().union(*routes.values()) if routes else set())
    results = []
    for group in groups:
        types = {
            lines[route_pk].vehicle_type
            for p in group.platforms
            for route_pk in routes.get(p.pk, ())
            if route_pk in lines
        }
        results.append(
            {
                "stop_id": group.stop_id,
                "name": group.name,
                "lat": group.lat,
                "lon": group.lon,
                "vehicle_types": [t for t in VEHICLE_TYPES if t in types],
                "stop_ids": [p.stop_id for p in group.platforms],
            }
        )
    return results
