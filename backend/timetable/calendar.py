"""Service calendar of one feed version: active services per date and day types."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from transit_data.models import Calendar, CalendarDate

WEEKDAY = "weekday"
SATURDAY = "saturday"
SUNDAY = "sunday"
DAY_TYPES = (WEEKDAY, SATURDAY, SUNDAY)

_WEEKDAY_FIELDS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# calendar_dates.txt rows are loaded in windows of this many days around the asked date.
_EXCEPTION_WINDOW_BEFORE = 7
_EXCEPTION_WINDOW_AFTER = 28


class ServiceCalendar:
    """Active service ids per date for one feed version (calendar + calendar_dates).

    calendar.txt rows are loaded once; calendar_dates.txt rows are loaded in date windows
    on demand. Meant to live for one request.
    """

    def __init__(self, feed_version_id: int):
        self.feed_version_id = feed_version_id
        self._weekly: list[tuple[str, tuple[bool, ...], date, date]] | None = None
        self._exceptions: dict[date, list[tuple[str, int]]] = {}
        self._loaded: list[tuple[date, date]] = []
        self._services: dict[date, frozenset[str]] = {}

    def _load_weekly(self) -> list[tuple[str, tuple[bool, ...], date, date]]:
        if self._weekly is None:
            rows = Calendar.objects.filter(feed_version_id=self.feed_version_id).values_list(
                "service_id", *_WEEKDAY_FIELDS, "start_date", "end_date"
            )
            self._weekly = [(row[0], tuple(row[1:8]), row[8], row[9]) for row in rows]
        return self._weekly

    def _ensure_exceptions(self, day: date) -> None:
        if any(start <= day <= end for start, end in self._loaded):
            return
        start = _shift(day, -_EXCEPTION_WINDOW_BEFORE)
        end = _shift(day, _EXCEPTION_WINDOW_AFTER)
        rows = CalendarDate.objects.filter(
            feed_version_id=self.feed_version_id, date__range=(start, end)
        ).values_list("date", "service_id", "exception_type")
        for row_date, service_id, exception_type in rows:
            if not any(s <= row_date <= e for s, e in self._loaded):
                self._exceptions.setdefault(row_date, []).append((service_id, exception_type))
        self._loaded.append((start, end))

    def services_on(self, day: date) -> frozenset[str]:
        """Service ids that run on ``day``."""
        if day in self._services:
            return self._services[day]
        weekday = day.weekday()
        active = {
            service_id
            for service_id, days, start, end in self._load_weekly()
            if start <= day <= end and days[weekday]
        }
        self._ensure_exceptions(day)
        for service_id, exception_type in self._exceptions.get(day, ()):
            if exception_type == CalendarDate.ExceptionType.ADDED:
                active.add(service_id)
            else:
                active.discard(service_id)
        result = frozenset(active)
        self._services[day] = result
        return result

    def day_type(self, day: date) -> str:
        """``weekday``, ``saturday`` or ``sunday`` (Sundays and public holidays).

        A weekday or Saturday whose set of active services equals the set of the nearest
        Sunday counts as ``sunday``. If the nearest Sunday has no service (outside the
        feed), the other neighbouring Sunday is used. Days without service keep their
        weekday-based type.
        """
        weekday = day.weekday()
        if weekday == 6:
            return SUNDAY
        own_type = SATURDAY if weekday == 5 else WEEKDAY
        services = self.services_on(day)
        if not services:
            return own_type
        previous_sunday = _shift(day, -(weekday + 1))
        next_sunday = _shift(day, 6 - weekday)
        candidates = (
            (previous_sunday, next_sunday)
            if weekday + 1 < 6 - weekday
            else (next_sunday, previous_sunday)
        )
        for sunday in candidates:
            if sunday is None:
                continue
            sunday_services = self.services_on(sunday)
            if sunday_services:
                return SUNDAY if sunday_services == services else own_type
        return own_type


def _shift(day: date, days: int) -> date | None:
    """``day + days``, or None when it would leave the supported date range."""
    try:
        return day + timedelta(days=days)
    except OverflowError:
        return None


def service_day_origin(day: date, tz: ZoneInfo) -> datetime:
    """The instant GTFS times of service day ``day`` count from ("noon minus 12 h")."""
    noon = datetime.combine(day, time(12), tzinfo=tz)
    return noon.astimezone(UTC) - timedelta(hours=12)


def gtfs_timestamp(day: date, seconds: int | None, tz: ZoneInfo) -> str | None:
    """ISO 8601 local timestamp with offset of a GTFS time on service day ``day``."""
    if seconds is None:
        return None
    return (service_day_origin(day, tz) + timedelta(seconds=seconds)).astimezone(tz).isoformat()


def clock_time(seconds: int) -> tuple[str, bool]:
    """``HH:MM`` clock time of a GTFS time and whether it is after midnight of the service
    day (``24:15`` -> ``("00:15", True)``)."""
    minutes = seconds // 60
    hours, minute = divmod(minutes, 60)
    return f"{hours % 24:02d}:{minute:02d}", hours >= 24
