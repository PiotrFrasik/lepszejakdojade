"""Stop overview: lines serving a stop group with their directions (docs/api.md, "Stop
overview (#9)").

All trips of the active feed versions count, whatever their service days. One aggregate
query counts, per line, direction and platform of the group, the trips that depart there
(calls with a later stop and boarding allowed), split by headsign. The per-route directions
are cached per set of active feed versions and group; feed versions are immutable, so a new
import changes the cache key.
"""

from __future__ import annotations

from collections import defaultdict

from django.core.cache import cache
from django.db import connection

from cities.registry import VEHICLE_TYPES, City
from transit_data.models import PickupDropOff, Stop, StopTime, Trip

from .lines import Feeds, lines_by_pk
from .stops import StopGroup, group_vehicle_types

_OVERVIEW_CACHE_SECONDS = 24 * 3600

# Per (route, direction, platform, headsign) and per (route, direction, platform): number of
# distinct trips departing there. The headsign falls back to the trip headsign and then to
# the name of the trip's last stop (evaluated only when both are blank).
_DEPARTURES_SQL = f"""
WITH calls AS (
    SELECT t.route_id,
           COALESCE(t.direction_id, 0) AS direction,
           st.stop_id,
           st.trip_id,
           COALESCE(
               NULLIF(st.stop_headsign, ''),
               NULLIF(t.headsign, ''),
               (SELECT s.name FROM {StopTime._meta.db_table} l
                JOIN {Stop._meta.db_table} s ON s.id = l.stop_id
                WHERE l.trip_id = st.trip_id
                ORDER BY l.stop_sequence DESC LIMIT 1),
               ''
           ) AS headsign
    FROM {StopTime._meta.db_table} st
    JOIN {Trip._meta.db_table} t ON t.id = st.trip_id
    WHERE st.stop_id = ANY(%s)
      AND st.pickup_type <> %s
      AND EXISTS (
          SELECT 1 FROM {StopTime._meta.db_table} n
          WHERE n.trip_id = st.trip_id AND n.stop_sequence > st.stop_sequence
      )
)
SELECT route_id, direction, stop_id, headsign, GROUPING(headsign) AS total,
       COUNT(DISTINCT trip_id) AS trips
FROM calls
GROUP BY GROUPING SETS ((route_id, direction, stop_id, headsign), (route_id, direction, stop_id))
"""  # noqa: S608 - table names come from model metadata, values are parameters


def _departure_counts(
    stop_pks: list[int],
) -> tuple[dict[tuple[int, int], dict[int, int]], dict[tuple[int, int, int], dict[str, int]]]:
    """``(trips per (route, direction) and platform, trips per (route, direction, platform)
    and headsign)``."""
    platforms: dict[tuple[int, int], dict[int, int]] = defaultdict(dict)
    headsigns: dict[tuple[int, int, int], dict[str, int]] = defaultdict(dict)
    with connection.cursor() as cursor:
        cursor.execute(_DEPARTURES_SQL, [stop_pks, PickupDropOff.NONE])
        for route_pk, direction, stop_pk, headsign, total, trips in cursor.fetchall():
            if total:
                platforms[(route_pk, direction)][stop_pk] = trips
            else:
                headsigns[(route_pk, direction, stop_pk)][headsign] = trips
    return platforms, headsigns


def _route_directions(group: StopGroup) -> dict[int, list[dict]]:
    """Directions in which each route departs from the group, sorted by direction."""
    stop_id_by_pk = {platform.pk: platform.stop_id for platform in group.platforms}
    platforms, headsigns = _departure_counts(list(stop_id_by_pk))
    directions: dict[int, list[dict]] = defaultdict(list)
    for (route_pk, direction), counts in sorted(platforms.items()):
        # Most trips, ties: lowest platform id.
        stop_pk = min(counts, key=lambda pk: (-counts[pk], stop_id_by_pk[pk]))
        by_headsign = headsigns[(route_pk, direction, stop_pk)]
        # Most trips, ties: alphabetical.
        headsign = min(by_headsign, key=lambda text: (-by_headsign[text], text))
        directions[route_pk].append(
            {"direction": direction, "headsign": headsign, "platform_id": stop_id_by_pk[stop_pk]}
        )
    return dict(directions)


def _cached_route_directions(city: City, feeds: Feeds, group: StopGroup) -> dict[int, list[dict]]:
    versions = ",".join(str(v) for v in sorted(feeds.version_ids))
    key = f"timetable:stop_overview:{city.id}:{versions}:{group.stop_id}"
    directions = cache.get(key)
    if directions is None:
        directions = _route_directions(group)
        cache.set(key, directions, _OVERVIEW_CACHE_SECONDS)
    return directions


def build_overview(city: City, feeds: Feeds, group: StopGroup, requested_stop_id: str) -> dict:
    """Response of GET /cities/{city}/stops/{stop_id}/ for one stop group. Only the route
    directions are cached; lines (vehicle types, groups, colours) follow the current city
    config."""
    directions = _cached_route_directions(city, feeds, group)
    lines = lines_by_pk(city, feeds, directions)
    ordered = sorted(
        lines.values(), key=lambda line: (VEHICLE_TYPES.index(line.vehicle_type), line.sort_key)
    )
    return {
        "stop": {
            "id": requested_stop_id,
            "name": group.name,
            "lat": group.lat,
            "lon": group.lon,
            "vehicle_types": group_vehicle_types(city, feeds, [group])[0],
            "stop_ids": [platform.stop_id for platform in group.platforms],
        },
        "lines": [{"line": line.summary(), "directions": directions[line.pk]} for line in ordered],
    }
