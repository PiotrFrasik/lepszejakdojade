"""Route variants: distinct stop patterns of the trips of one line and direction."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from django.db import connection

from transit_data.models import StopTime

MAIN = "main"
SHORT_TURN = "short_turn"
DEPOT = "depot"
OTHER = "other"

Pattern = tuple[int, ...]  # stop primary keys in stop_sequence order


@dataclass
class Variant:
    id: str
    kind: str
    pattern: Pattern
    trip_ids: list[int] = field(default_factory=list)
    headsigns: Counter = field(default_factory=Counter)

    @property
    def trip_count(self) -> int:
        return len(self.trip_ids)

    @property
    def headsign(self) -> str:
        return self.headsigns.most_common(1)[0][0] if self.headsigns else ""


def trip_patterns(trip_ids: Iterable[int]) -> dict[int, Pattern]:
    """Stop pattern of every given trip, aggregated in the database (one row per trip)."""
    trip_ids = list(trip_ids)
    if not trip_ids:
        return {}
    table = StopTime._meta.db_table
    sql = (
        f"SELECT trip_id, array_agg(stop_id ORDER BY stop_sequence) "  # noqa: S608
        f"FROM {table} WHERE trip_id = ANY(%s) GROUP BY trip_id"
    )
    with connection.cursor() as cursor:
        cursor.execute(sql, [trip_ids])
        return {trip_id: tuple(stops) for trip_id, stops in cursor.fetchall()}


def _contains_contiguous(main: Pattern, part: Pattern) -> bool:
    if not part or len(part) > len(main):
        return False
    size = len(part)
    return any(main[i : i + size] == part for i in range(len(main) - size + 1))


def classify(pattern: Pattern, main: Pattern) -> str:
    """Kind of a non-main pattern relative to the main pattern."""
    if pattern == main:
        return MAIN
    if _contains_contiguous(main, pattern):
        return SHORT_TURN
    in_main = set(main)
    start = 0
    while start < len(pattern) and pattern[start] not in in_main:
        start += 1
    end = len(pattern)
    while end > start and pattern[end - 1] not in in_main:
        end -= 1
    middle = pattern[start:end]
    if (start > 0 or end < len(pattern)) and _contains_contiguous(main, middle):
        return DEPOT
    return OTHER


def build_variants(patterns: Mapping[int, Pattern], headsigns: Mapping[int, str]) -> list[Variant]:
    """Group trips by stop pattern. Main (most trips) first, then by trip count."""
    by_pattern: dict[Pattern, Variant] = {}
    for trip_id, pattern in patterns.items():
        if not pattern:
            continue
        variant = by_pattern.setdefault(pattern, Variant(id="", kind=OTHER, pattern=pattern))
        variant.trip_ids.append(trip_id)
        if headsigns.get(trip_id):
            variant.headsigns[headsigns[trip_id]] += 1
    ordered = sorted(by_pattern.values(), key=lambda v: (-v.trip_count, -len(v.pattern), v.pattern))
    for index, variant in enumerate(ordered, start=1):
        variant.id = f"v{index}"
        variant.kind = MAIN if index == 1 else classify(variant.pattern, ordered[0].pattern)
    return ordered


def extend_variants(
    variants: list[Variant], patterns: Mapping[int, Pattern], headsigns: Mapping[int, str]
) -> dict[int, Variant]:
    """Map trips to variants, adding variants for patterns not in ``variants``.

    Existing variants keep their ids; new ones continue the numbering. Returns trip id ->
    variant for every trip in ``patterns``.
    """
    by_pattern = {variant.pattern: variant for variant in variants}
    main = variants[0].pattern if variants else None
    extra = build_variants({t: p for t, p in patterns.items() if p not in by_pattern}, headsigns)
    for variant in extra:
        variant.id = f"v{len(variants) + 1}"
        if main is None:
            # No reference pattern: the first new variant becomes the main one.
            main = variant.pattern
        variant.kind = classify(variant.pattern, main)
        variants.append(variant)
        by_pattern[variant.pattern] = variant
    return {trip_id: by_pattern[p] for trip_id, p in patterns.items() if p in by_pattern}


def merge_stops(variants: list[Variant]) -> list[tuple[int, bool]]:
    """Diagram stops: the main pattern plus stops served only by other variants, inserted
    at their position in sequence. Returns ``(stop_pk, variant_only)`` pairs."""
    if not variants:
        return []
    merged: list[tuple[int, bool]] = [(stop, False) for stop in variants[0].pattern]
    for variant in variants[1:]:
        anchor: int | None = None  # index in merged of the last known stop of this variant
        pending: list[int] = []  # leading stops before the first known stop
        for stop in variant.pattern:
            positions = [i for i, (s, _only) in enumerate(merged) if s == stop]
            if positions:
                later = [i for i in positions if anchor is None or i > anchor]
                index = later[0] if later else positions[0]
                if pending:
                    merged[index:index] = [(s, True) for s in pending]
                    index += len(pending)
                    pending = []
                anchor = index
            elif anchor is None:
                pending.append(stop)
            else:
                anchor += 1
                merged.insert(anchor, (stop, True))
        if pending:
            merged.extend((s, True) for s in pending)
    return merged
