"""Tools the model can call. Each wraps an existing backend service (no HTTP, no raw SQL
from the model) and is read-only: no tool has side effects.

Arguments come from the model and are untrusted: they are type-checked and length-capped
here. The city is fixed by the request, never chosen by the model. Results returned to the
model are compact JSON; cards for the client are built here from the same service results
(never from model text) and collected in ``ToolContext.cards``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from cities.registry import VEHICLE_TYPES, City
from journeys import services as journeys
from journeys.otp import OtpUnavailable
from timetable import services as timetable
from timetable.lines import Feeds, Line, get_line, get_stop, list_lines
from timetable.stops import StopGroup, city_groups, search_stops

from .departures import MAX_DEPARTURES, upcoming_departures
from .providers.base import ToolCall, ToolSpec

logger = logging.getLogger(__name__)

MAX_CARDS = 3
MAX_STOP_RESULTS = 5
MAX_LINE_RESULTS = 80
MAX_ITINERARIES_FOR_MODEL = 3
MAX_ARG_LENGTH = 200
_CARD_DEPARTURE_FIELDS = (
    "line",
    "stop_id",
    "direction",
    "headsign",
    "time",
    "next_day",
    "date",
    "trip_id",
)


class ToolError(Exception):
    """A tool cannot answer; ``code`` is passed to the model as ``{"error": code}``."""

    def __init__(self, code: str, **extra: Any):
        super().__init__(code)
        self.code = code
        self.extra = extra


@dataclass
class ToolContext:
    city: City
    now: datetime  # in the city time zone
    feeds: Feeds = field(init=False)
    cards: list[tuple[str, dict]] = field(default_factory=list)  # (dedupe key, card)
    stop_choices: list[dict] | None = None  # last ambiguous stop search (for a stops card)
    _groups_by_stop: dict[str, StopGroup] | None = None

    def __post_init__(self) -> None:
        self.feeds = Feeds(self.city)

    def add_card(self, key: str, card: dict) -> None:
        if all(existing != key for existing, _ in self.cards):
            self.cards.append((key, card))

    def final_cards(self) -> list[dict]:
        cards = [card for _, card in self.cards]
        if not cards and self.stop_choices:
            cards = [{"type": "stops", "stops": self.stop_choices}]
        return cards[:MAX_CARDS]

    def group_of(self, stop_id: str) -> StopGroup | None:
        """The name group (all platforms) a platform id belongs to."""
        if self._groups_by_stop is None:
            self._groups_by_stop = {
                platform.stop_id: group
                for group in city_groups(self.city, self.feeds)
                for platform in group.platforms
            }
        return self._groups_by_stop.get(stop_id)


# ------------------------------------------------------------------------ arguments


def _text(args: dict, name: str, required: bool = True) -> str | None:
    value = args.get(name)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ToolError("missing_argument", argument=name)
        return None
    if not isinstance(value, str | int | float):
        raise ToolError("invalid_argument", argument=name)
    return str(value).strip()[:MAX_ARG_LENGTH]


def _int(args: dict, name: str, choices: tuple[int, ...] | None = None) -> int | None:
    value = args.get(name)
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ToolError("invalid_argument", argument=name) from None
    if choices is not None and number not in choices:
        raise ToolError("invalid_argument", argument=name)
    return number


def _bool(args: dict, name: str) -> bool:
    value = args.get(name)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _date(args: dict, name: str, ctx: ToolContext) -> date:
    value = _text(args, name, required=False)
    if value is None:
        return ctx.now.date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError("invalid_argument", argument=name) from None


def _hhmm(iso: str) -> tuple[str, str]:
    moment = datetime.fromisoformat(iso)
    return moment.date().isoformat(), moment.strftime("%H:%M")


# --------------------------------------------------------------------------- lookups


def _line_brief(line: Line) -> dict:
    return {
        "line_id": line.id,
        "name": line.short_name,
        "vehicle_type": line.vehicle_type,
        "long_name": line.long_name,
    }


def _resolve_line(ctx: ToolContext, value: str) -> Line:
    """A line by id or by its public name (``52``, ``N1``)."""
    line = get_line(ctx.city, ctx.feeds, value) if ":" in value else None
    if line is not None:
        return line
    wanted = value.casefold()
    matches = [
        line for line in list_lines(ctx.city, ctx.feeds) if line.short_name.casefold() == wanted
    ]
    if not matches:
        raise ToolError("unknown_line")
    if len(matches) > 1:
        raise ToolError("ambiguous_line", candidates=[_line_brief(m) for m in matches[:10]])
    return matches[0]


def _stop_group(ctx: ToolContext, stop_id: str) -> StopGroup:
    group = ctx.group_of(stop_id)
    if group is None:
        raise ToolError("unknown_stop")
    return group


# ----------------------------------------------------------------------------- tools


def search_stops_tool(ctx: ToolContext, args: dict) -> dict:
    query = _text(args, "query")
    if len(query) < 2:
        raise ToolError("query_too_short")
    results = search_stops(ctx.city, ctx.feeds, query)[:MAX_STOP_RESULTS]
    if len(results) > 1:
        ctx.stop_choices = results
    return {
        "stops": [
            {"stop_id": r["stop_id"], "name": r["name"], "vehicle_types": r["vehicle_types"]}
            for r in results
        ]
    }


def plan_journey_tool(ctx: ToolContext, args: dict) -> dict:
    places = []
    for name in ("from_stop_id", "to_stop_id"):
        stop = journeys.resolve_stop(ctx.feeds, _text(args, name))
        if stop is None:
            raise ToolError("unknown_stop", argument=name)
        places.append(journeys.Place(name=stop.name or None, lat=stop.point.y, lon=stop.point.x))
    origin, destination = places
    if (round(origin.lat, 6), round(origin.lon, 6)) == (
        round(destination.lat, 6),
        round(destination.lon, 6),
    ):
        raise ToolError("same_start_and_destination")
    when = ctx.now
    time_text = _text(args, "time", required=False)
    if time_text:
        try:
            when = datetime.fromisoformat(time_text)
        except ValueError:
            raise ToolError("invalid_argument", argument="time") from None
        when = (
            when.replace(tzinfo=ctx.city.zoneinfo)
            if when.tzinfo is None
            else when.astimezone(ctx.city.zoneinfo)
        )
    time_mode = "arrive" if _text(args, "time_mode", required=False) == "arrive" else "depart"
    preferences = journeys.Preferences(
        fewer_transfers=_bool(args, "fewer_transfers"),
        less_walking=_bool(args, "less_walking"),
        wheelchair=_bool(args, "wheelchair"),
    )
    try:
        data = journeys.search(
            ctx.city, ctx.feeds, origin, destination, when, time_mode, preferences
        )
    except OtpUnavailable:
        raise ToolError("journey_planner_unavailable") from None

    itineraries = data["itineraries"]
    if itineraries:
        first = itineraries[0]
        ctx.add_card(
            f"journey:{first['start']}:{first['end']}:{first['legs'][0]['from']['name']}",
            {
                "type": "journey",
                "from": data["from"],
                "to": data["to"],
                "itinerary": first,
                "comparison": data["comparison"],
            },
        )
    summary = []
    for itinerary in itineraries[:MAX_ITINERARIES_FOR_MODEL]:
        day, start = _hhmm(itinerary["start"])
        legs = []
        for leg in itinerary["legs"]:
            item = {
                "mode": leg["mode"],
                "from": leg["from"]["name"],
                "to": leg["to"]["name"],
                "departure": _hhmm(leg["start"])[1],
                "arrival": _hhmm(leg["end"])[1],
                "duration_min": round(leg["duration"] / 60),
            }
            if leg["line"] is not None:
                item["line"] = leg["line"]["short_name"]
                item["headsign"] = leg["headsign"]
                item["stops_between"] = len(leg["intermediate_stops"])
            else:
                item["distance_m"] = leg["distance"]
            legs.append(item)
        summary.append(
            {
                "date": day,
                "departure": start,
                "arrival": _hhmm(itinerary["end"])[1],
                "duration_min": round(itinerary["duration"] / 60),
                "transfers": itinerary["transfers"],
                "walk_distance_m": itinerary["walk_distance"],
                "legs": legs,
            }
        )
    comparison = {
        mode: (None if value is None else {"duration_min": round(value["duration"] / 60)})
        for mode, value in data["comparison"].items()
    }
    return {
        "from": data["from"]["name"],
        "to": data["to"]["name"],
        "itineraries": summary,
        "walk_or_bike_instead": comparison,
    }


def list_lines_tool(ctx: ToolContext, args: dict) -> dict:
    vehicle_type = _text(args, "vehicle_type", required=False)
    if vehicle_type is not None and vehicle_type not in VEHICLE_TYPES:
        raise ToolError("invalid_argument", argument="vehicle_type")
    query = (_text(args, "query", required=False) or "").casefold()
    lines = list_lines(ctx.city, ctx.feeds, vehicle_type)
    if query:
        lines = [
            line
            for line in lines
            if query in line.short_name.casefold() or query in line.long_name.casefold()
        ]
    return {
        "count": len(lines),
        "lines": [_line_brief(line) for line in lines[:MAX_LINE_RESULTS]],
        "truncated": len(lines) > MAX_LINE_RESULTS,
    }


def line_route_tool(ctx: ToolContext, args: dict) -> dict:
    line = _resolve_line(ctx, _text(args, "line"))
    direction = _int(args, "direction", (0, 1))
    day = _date(args, "date", ctx)
    try:
        context = timetable.direction_context(line, direction, day)
    except timetable.DirectionNotFound:
        raise ToolError("direction_not_found") from None
    route = timetable.build_route(ctx.city, ctx.feeds, context)
    return {
        "line": _line_brief(line),
        "direction": route["direction"],
        "date": route["date"].isoformat(),
        "directions": route["directions"],
        "stops": [
            {
                "stop_id": stop["stop_id"],
                "name": stop["name"],
                "only_some_trips": stop["variant_only"],
                "transfers": [t["short_name"] for t in stop["transfers"]],
            }
            for stop in route["stops"]
        ],
    }


def _times(column: dict) -> list[str]:
    return [
        departure["time"] + (" (+1 day)" if departure["next_day"] else "")
        for hour in column["hours"]
        for departure in hour["departures"]
    ]


def stop_timetable_tool(ctx: ToolContext, args: dict) -> dict:
    line = _resolve_line(ctx, _text(args, "line"))
    group = _stop_group(ctx, _text(args, "stop_id"))
    direction = _int(args, "direction", (0, 1))
    day = _date(args, "date", ctx)
    directions = (
        [direction]
        if direction is not None
        else [item["direction"] for item in timetable.line_directions(line)]
    )
    stops = [
        stop
        for platform in group.platforms
        if (stop := get_stop(ctx.feeds, line, platform.stop_id)) is not None
    ]
    timetables = []
    for current in directions:
        stop = next((s for s in stops if timetable.stop_served(line, current, s)), None)
        if stop is None:
            continue
        try:
            context = timetable.direction_context(line, current, day)
        except timetable.DirectionNotFound:
            continue
        data = timetable.build_timetable(ctx.city, ctx.feeds, context, stop, day)
        column = next(c for c in data["columns"] if c["day_type"] == data["day_type"])
        timetables.append(
            {
                "direction": current,
                "headsign": data["headsign"],
                "stop_id": data["stop"]["stop_id"],
                "date": column["date"].isoformat(),
                "day_type": data["day_type"],
                "departures": _times(column),
            }
        )
    if not timetables:
        raise ToolError("line_does_not_stop_here")
    return {"line": _line_brief(line), "stop": group.name, "timetables": timetables}


def next_departures_tool(ctx: ToolContext, args: dict) -> dict:
    group = _stop_group(ctx, _text(args, "stop_id"))
    line_value = _text(args, "line", required=False)
    route_pks = {_resolve_line(ctx, line_value).pk} if line_value else None
    limit = min(max(_int(args, "limit") or MAX_DEPARTURES, 1), MAX_DEPARTURES)
    departures = upcoming_departures(
        ctx.city,
        ctx.feeds,
        [platform.pk for platform in group.platforms],
        ctx.now,
        limit,
        route_pks,
    )
    if departures:
        ctx.add_card(
            f"departures:{group.stop_id}:{line_value or ''}",
            {
                "type": "departures",
                "stop": {"stop_id": group.stop_id, "name": group.name},
                "departures": [
                    {key: item[key] for key in _CARD_DEPARTURE_FIELDS} for item in departures
                ],
            },
        )
    return {
        "stop": group.name,
        "now": ctx.now.strftime("%Y-%m-%d %H:%M"),
        "departures": [
            {
                "line": item["line"]["short_name"],
                "vehicle_type": item["line"]["vehicle_type"],
                "headsign": item["headsign"],
                "time": item["time"],
                "service_date": item["date"],
                "after_midnight": item["next_day"],
            }
            for item in departures
        ],
    }


# -------------------------------------------------------------------------- registry


_STRING = {"type": "string"}


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    handler: Callable[[ToolContext, dict], dict]


TOOLS: dict[str, Tool] = {
    tool.spec.name: tool
    for tool in (
        Tool(
            ToolSpec(
                "search_stops",
                "Find stops of the current city by name (case and Polish diacritics do not "
                "matter). Returns up to 5 stops with stop_id. Use it before any other tool "
                "that needs a stop_id. If nothing is found, try a shorter or official form "
                "of the name (e.g. 'Rondo Mogilskie' for 'Mogilskie').",
                {
                    "type": "object",
                    "properties": {
                        "query": {**_STRING, "description": "Stop name or its fragment."}
                    },
                    "required": ["query"],
                },
            ),
            search_stops_tool,
        ),
        Tool(
            ToolSpec(
                "plan_journey",
                "Plan a public transport journey between two stops (scheduled data). "
                "Returns up to 3 itineraries with local times.",
                {
                    "type": "object",
                    "properties": {
                        "from_stop_id": {**_STRING, "description": "stop_id of the start."},
                        "to_stop_id": {**_STRING, "description": "stop_id of the destination."},
                        "time": {
                            **_STRING,
                            "description": "Local date and time YYYY-MM-DDTHH:MM. Default: now.",
                        },
                        "time_mode": {
                            **_STRING,
                            "enum": ["depart", "arrive"],
                            "description": "Whether time is the departure (default) or "
                            "the latest arrival.",
                        },
                        "fewer_transfers": {"type": "boolean"},
                        "less_walking": {"type": "boolean"},
                        "wheelchair": {"type": "boolean"},
                    },
                    "required": ["from_stop_id", "to_stop_id"],
                },
            ),
            plan_journey_tool,
        ),
        Tool(
            ToolSpec(
                "next_departures",
                "Next scheduled departures (timetable, not live) from a stop, all lines or "
                "one line, from now on. Up to 10, ascending.",
                {
                    "type": "object",
                    "properties": {
                        "stop_id": {**_STRING, "description": "stop_id from search_stops."},
                        "line": {
                            **_STRING,
                            "description": "Optional line name (e.g. '52') or line_id.",
                        },
                        "limit": {"type": "integer", "description": "1-10, default 10."},
                    },
                    "required": ["stop_id"],
                },
            ),
            next_departures_tool,
        ),
        Tool(
            ToolSpec(
                "list_lines",
                "Lines of the current city, optionally filtered by vehicle type or by a "
                "fragment of the line name or route description.",
                {
                    "type": "object",
                    "properties": {
                        "vehicle_type": {**_STRING, "enum": list(VEHICLE_TYPES)},
                        "query": _STRING,
                    },
                },
            ),
            list_lines_tool,
        ),
        Tool(
            ToolSpec(
                "get_line_route",
                "Stops of a line in one direction, in order, with transfers to other lines, "
                "and the list of the line's directions.",
                {
                    "type": "object",
                    "properties": {
                        "line": {**_STRING, "description": "Line name (e.g. '52') or line_id."},
                        "direction": {
                            "type": "integer",
                            "description": "0 or 1. Default: the first direction.",
                        },
                        "date": {**_STRING, "description": "YYYY-MM-DD, default today."},
                    },
                    "required": ["line"],
                },
            ),
            line_route_tool,
        ),
        Tool(
            ToolSpec(
                "get_stop_timetable",
                "Full-day scheduled timetable of one line at one stop on a date (all "
                "directions unless one is given). Times marked '(+1 day)' are after "
                "midnight.",
                {
                    "type": "object",
                    "properties": {
                        "line": {**_STRING, "description": "Line name (e.g. '52') or line_id."},
                        "stop_id": {**_STRING, "description": "stop_id from search_stops."},
                        "direction": {"type": "integer", "description": "0 or 1. Default: all."},
                        "date": {**_STRING, "description": "YYYY-MM-DD, default today."},
                    },
                    "required": ["line", "stop_id"],
                },
            ),
            stop_timetable_tool,
        ),
    )
}


def tool_specs() -> list[ToolSpec]:
    return [tool.spec for tool in TOOLS.values()]


def run_tool(ctx: ToolContext, call: ToolCall) -> dict:
    """Run one tool call. Never raises: failures become ``{"error": code}`` so the model can
    tell the user that the data is unavailable."""
    tool = TOOLS.get(call.name)
    if tool is None:
        return {"error": "unknown_tool"}
    try:
        return {"result": tool.handler(ctx, call.arguments or {})}
    except ToolError as exc:
        return {"error": exc.code, **exc.extra}
    except Exception:
        logger.exception("Assistant tool %s failed", call.name)
        return {"error": "data_unavailable"}
