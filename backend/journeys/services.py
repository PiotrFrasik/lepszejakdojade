"""Journey search: resolve places, query OpenTripPlanner, map its answer to the API contract.

OTP ids are ``{feedId}:{gtfsId}`` and the OTP graph uses our static feed ids as ``feedId``
(transit_data/otp_inputs.py), so OTP route, stop and trip ids are our public ids as they are.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.gis.db.models import Extent
from django.core.cache import cache

from cities.registry import City, get_otp_url
from timetable.lines import Feeds, Line, line_colours, lines_by_id
from transit_data.models import Stop, vehicle_type_for_route_type
from transit_data.otp_inputs import BBox

from . import otp, polyline
from .otp import OtpUnavailable

logger = logging.getLogger(__name__)

MAX_ITINERARIES = 5
_BBOX_CACHE_SECONDS = 3600

# App vehicle type -> OTP transit modes (OTP's mapping of GTFS route types).
OTP_TRANSIT_MODES = {
    "tram": ("TRAM", "CABLE_CAR"),
    "bus": ("BUS", "TROLLEYBUS", "COACH"),
    "metro": ("SUBWAY",),
    "rail": ("RAIL", "MONORAIL"),
}
_VEHICLE_TYPE_BY_OTP_MODE = {
    mode: vehicle_type for vehicle_type, modes in OTP_TRANSIT_MODES.items() for mode in modes
}

_LEG_FIELDS = """
    mode
    transitLeg
    duration
    distance
    start { scheduledTime estimated { time } }
    end { scheduledTime estimated { time } }
    from { name lat lon stop { gtfsId } }
    to { name lat lon stop { gtfsId } }
    route { gtfsId shortName longName type color textColor }
    trip { gtfsId tripHeadsign }
    headsign
    intermediatePlaces { name stop { gtfsId } }
    legGeometry { points }
"""

PLAN_QUERY = (
    """
query JourneySearch(
  $origin: PlanLabeledLocationInput!
  $destination: PlanLabeledLocationInput!
  $dateTime: PlanDateTimeInput
  $modes: PlanModesInput
  $preferences: PlanPreferencesInput
  $first: Int
) {
  planConnection(
    origin: $origin
    destination: $destination
    dateTime: $dateTime
    modes: $modes
    preferences: $preferences
    first: $first
  ) {
    edges {
      node {
        start
        end
        duration
        legs {"""
    + _LEG_FIELDS
    + """}
      }
    }
  }
}
"""
)


@dataclass(frozen=True)
class Place:
    name: str | None
    lat: float
    lon: float

    def as_dict(self) -> dict:
        return {"name": self.name, "lat": self.lat, "lon": self.lon}


@dataclass(frozen=True)
class Preferences:
    fewer_transfers: bool = False
    less_walking: bool = False
    wheelchair: bool = False


# ------------------------------------------------------------------------- places


def resolve_stop(feeds: Feeds, stop_id: str) -> Stop | None:
    """A stop with coordinates of the city's active feeds, by public id."""
    resolved = feeds.resolve(stop_id)
    if resolved is None:
        return None
    return Stop.objects.filter(
        feed_version_id=resolved[0], gtfs_id=resolved[2], point__isnull=False
    ).first()


def city_bbox(city: City, feeds: Feeds) -> BBox | None:
    """The area served by the city's OTP graph: ``otp.bbox`` from city config, otherwise the
    extent of the active feeds' stops plus ``OTP_BBOX_BUFFER_KM`` (as in the graph build).
    None when the city has no stops yet."""
    if city.otp is not None and city.otp.bbox is not None:
        return BBox(*city.otp.bbox)
    version_ids = sorted(feeds.version_ids)
    if not version_ids:
        return None
    key = f"journeys:bbox:{city.id}:{','.join(map(str, version_ids))}"
    cached = cache.get(key)
    if cached is None:
        extent = Stop.objects.filter(
            feed_version_id__in=version_ids, point__isnull=False
        ).aggregate(extent=Extent("point"))["extent"]
        cached = list(extent) if extent else []
        cache.set(key, cached, _BBOX_CACHE_SECONDS)
    if not cached:
        return None
    return BBox(*cached).buffered(settings.OTP_BBOX_BUFFER_KM)


def in_bbox(bbox: BBox, lat: float, lon: float) -> bool:
    return bbox.min_lat <= lat <= bbox.max_lat and bbox.min_lon <= lon <= bbox.max_lon


# ---------------------------------------------------------------------- OTP query


def _location(place: Place) -> dict:
    return {"location": {"coordinate": {"latitude": place.lat, "longitude": place.lon}}}


def _date_time(when: datetime, time_mode: str) -> dict:
    key = "latestArrival" if time_mode == "arrive" else "earliestDeparture"
    return {key: when.isoformat(timespec="seconds")}


def transit_variables(
    city: City,
    origin: Place,
    destination: Place,
    when: datetime,
    time_mode: str,
    preferences: Preferences,
) -> dict:
    otp_preferences: dict = {}
    if preferences.wheelchair:
        otp_preferences["accessibility"] = {"wheelchair": {"enabled": True}}
    if preferences.less_walking:
        otp_preferences["street"] = {
            "walk": {"reluctance": settings.JOURNEY_LESS_WALKING_RELUCTANCE}
        }
    if preferences.fewer_transfers:
        otp_preferences["transit"] = {"transfer": {"cost": settings.JOURNEY_FEWER_TRANSFERS_COST}}
    transit_modes = [
        {"mode": mode}
        for vehicle_type in city.vehicle_types
        for mode in OTP_TRANSIT_MODES[vehicle_type]
    ]
    variables = {
        "origin": _location(origin),
        "destination": _location(destination),
        "dateTime": _date_time(when, time_mode),
        "modes": {"transitOnly": True, "transit": {"transit": transit_modes}},
        "first": MAX_ITINERARIES,
    }
    if otp_preferences:
        variables["preferences"] = otp_preferences
    return variables


def direct_variables(
    origin: Place, destination: Place, when: datetime, time_mode: str, street_mode: str
) -> dict:
    """A street-only search (``WALK`` or ``BICYCLE``) between the same points."""
    return {
        "origin": _location(origin),
        "destination": _location(destination),
        "dateTime": _date_time(when, time_mode),
        "modes": {"directOnly": True, "direct": [street_mode]},
        "first": 1,
    }


# ------------------------------------------------------------------------ mapping


def _time(leg_time: dict) -> str:
    estimated = leg_time.get("estimated") or {}
    return estimated.get("time") or leg_time["scheduledTime"]


def _iso(value: str, zone: ZoneInfo) -> str:
    return datetime.fromisoformat(value).astimezone(zone).isoformat(timespec="seconds")


def _stop_id(place: dict) -> str | None:
    return (place.get("stop") or {}).get("gtfsId")


def _leg_place(place: dict, label: Place | None) -> dict:
    """A leg end. Street points (no stop) at the journey's ends carry the request label."""
    stop_id = _stop_id(place)
    name = place.get("name") if stop_id or label is None else label.name
    return {"name": name, "stop_id": stop_id, "lat": place["lat"], "lon": place["lon"]}


def _geometry(leg: dict, start: dict, end: dict) -> dict:
    coordinates: list[list[float]] = []
    points = (leg.get("legGeometry") or {}).get("points")
    if points:
        try:
            coordinates = polyline.decode(points)
        except ValueError:
            logger.warning("OTP returned an invalid leg polyline")
    if len(coordinates) < 2:
        coordinates = [[start["lon"], start["lat"]], [end["lon"], end["lat"]]]
    return {"type": "LineString", "coordinates": coordinates}


def _fallback_line(city: City, route: dict) -> dict | None:
    """Line summary from OTP's route when the route is not in our database (e.g. OTP
    built from a newer feed than the active import)."""
    feed_id, _, gtfs_id = (route.get("gtfsId") or "").partition(":")
    route_type = route.get("type")
    if not gtfs_id or route_type is None:
        return None
    vehicle_type = str(vehicle_type_for_route_type(route_type))
    if vehicle_type not in city.vehicle_types:
        return None
    short_name = route.get("shortName") or route.get("longName") or gtfs_id
    group = city.line_group_for(vehicle_type, feed_id, short_name)
    colour, text_colour = line_colours(route.get("color"), route.get("textColor"), group)
    return {
        "id": route["gtfsId"],
        "short_name": short_name,
        "vehicle_type": vehicle_type,
        "group": group.id,
        "colour": colour,
        "text_colour": text_colour,
    }


def _map_leg(
    city: City,
    leg: dict,
    lines: dict[str, Line],
    origin: Place | None,
    destination: Place | None,
) -> dict | None:
    """One leg in the contract format, or None for a mode the API does not support."""
    zone = city.zoneinfo
    start_place, end_place = leg["from"], leg["to"]
    base = {
        "start": _iso(_time(leg["start"]), zone),
        "end": _iso(_time(leg["end"]), zone),
        "duration": round(leg.get("duration") or 0),
        "distance": round(leg.get("distance") or 0),
        "from": _leg_place(start_place, origin),
        "to": _leg_place(end_place, destination),
        "geometry": _geometry(leg, start_place, end_place),
    }
    if leg["mode"] == "WALK":
        return {
            "mode": "walk",
            **base,
            "line": None,
            "headsign": None,
            "trip_id": None,
            "intermediate_stops": [],
        }
    route = leg.get("route")
    if not leg.get("transitLeg") or not route:
        return None
    line = lines.get(route.get("gtfsId"))
    summary = line.summary() if line is not None else _fallback_line(city, route)
    if summary is None:
        return None
    trip = leg.get("trip") or {}
    return {
        "mode": summary["vehicle_type"],
        **base,
        "line": summary,
        "headsign": leg.get("headsign") or trip.get("tripHeadsign") or None,
        "trip_id": trip.get("gtfsId"),
        "intermediate_stops": [
            {"name": place.get("name"), "stop_id": _stop_id(place)}
            for place in leg.get("intermediatePlaces") or []
        ],
    }


def _nodes(data: dict) -> list[dict]:
    connection = data.get("planConnection") or {}
    return [edge["node"] for edge in connection.get("edges") or [] if edge.get("node")]


def map_itineraries(
    city: City,
    feeds: Feeds,
    data: dict,
    origin: Place,
    destination: Place,
    time_mode: str,
) -> list[dict]:
    nodes = _nodes(data)
    route_ids = {
        leg["route"]["gtfsId"]
        for node in nodes
        for leg in node.get("legs") or []
        if leg.get("route") and leg["route"].get("gtfsId")
    }
    lines = lines_by_id(city, feeds, route_ids)
    zone = city.zoneinfo

    itineraries = []
    for node in nodes:
        raw_legs = node.get("legs") or []
        legs = []
        for index, raw in enumerate(raw_legs):
            leg = _map_leg(
                city,
                raw,
                lines,
                origin if index == 0 else None,
                destination if index == len(raw_legs) - 1 else None,
            )
            if leg is None:
                break
            legs.append(leg)
        transit_legs = sum(1 for leg in legs if leg["mode"] != "walk")
        if len(legs) != len(raw_legs) or transit_legs == 0:
            continue  # unsupported mode, or a walk-only result (that is the comparison's job)
        walking = [leg for leg in legs if leg["mode"] == "walk"]
        itineraries.append(
            {
                "start": _iso(node["start"], zone),
                "end": _iso(node["end"], zone),
                "duration": round(node["duration"]),
                "transfers": max(transit_legs - 1, 0),
                "walk_distance": sum(leg["distance"] for leg in walking),
                "walk_duration": sum(leg["duration"] for leg in walking),
                "legs": legs,
            }
        )

    def instant(value: str) -> float:
        return datetime.fromisoformat(value).timestamp()

    if time_mode == "arrive":
        itineraries.sort(key=lambda item: (-instant(item["start"]), instant(item["end"])))
    else:
        itineraries.sort(key=lambda item: (instant(item["end"]), -instant(item["start"])))
    itineraries = itineraries[:MAX_ITINERARIES]
    return [{"id": f"i{n}", **item} for n, item in enumerate(itineraries, start=1)]


def map_direct(data: dict) -> dict | None:
    """``{duration, distance}`` of the first street-only itinerary, or None."""
    nodes = _nodes(data)
    if not nodes:
        return None
    duration = round(nodes[0]["duration"])
    if duration > settings.JOURNEY_COMPARISON_MAX_DURATION:
        return None
    distance = sum(leg.get("distance") or 0 for leg in nodes[0].get("legs") or [])
    return {"duration": duration, "distance": round(distance)}


# ------------------------------------------------------------------------- search


def search(
    city: City,
    feeds: Feeds,
    origin: Place,
    destination: Place,
    when: datetime,
    time_mode: str,
    preferences: Preferences,
) -> dict:
    """Run the transit search and the walk and bike comparisons concurrently.

    Raises OtpUnavailable if any of the OTP requests fails or the answer cannot be read.
    """
    base_url = get_otp_url(city.id)
    if not base_url:
        raise OtpUnavailable("OTP URL not configured")
    requests = [
        transit_variables(city, origin, destination, when, time_mode, preferences),
        direct_variables(origin, destination, when, time_mode, "WALK"),
        direct_variables(origin, destination, when, time_mode, "BICYCLE"),
    ]
    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        futures = [pool.submit(otp.graphql, base_url, PLAN_QUERY, v) for v in requests]
        transit, walk, bike = (future.result() for future in futures)
    try:
        return {
            "from": origin.as_dict(),
            "to": destination.as_dict(),
            "itineraries": map_itineraries(city, feeds, transit, origin, destination, time_mode),
            "comparison": {"walk": map_direct(walk), "bike": map_direct(bike)},
        }
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        logger.warning("Unexpected OTP response for %s: %r", city.id, exc)
        raise OtpUnavailable("unexpected response") from exc
