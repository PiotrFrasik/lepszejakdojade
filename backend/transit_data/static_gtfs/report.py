"""Import report: what was read, stored, skipped and corrected, per GTFS file.

Stored as JSON on ``FeedVersion.report`` and printed by the ``import_gtfs`` command.
Shape of ``ImportReport.as_dict()``::

    {
      "files": {
        "stop_times.txt": {
          "rows": 1234,            # data rows read
          "imported": 1230,        # rows written to the database
          "skipped": 4,            # rows dropped
          "skip_reasons": {"unknown stop_id": 4},
          "corrections": {"invalid pickup_type, used 0": 2},  # stored with a default
          "examples": [{"row": 17, "reason": "unknown stop_id", "value": "X1"}]
        }
      },
      "counts": {"stops": 120, "stop_times": 1230, ...},   # rows in the database
      "ignored_files": ["blocks.txt"],
      "warnings": ["service ends on 2026-12-12 (in 10 days)"],
      "timings_s": {"download": 1.2, "load": 3.4, "total": 4.8},
      "comparison": {                                       # empty without active / with force
        "active_feed_version_id": 7, "min_share": 0.5,
        "trips": {"new": 15000, "active": 15321},
        "stop_times": {"new": 430000, "active": 439544}
      }
    }
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

# Examples of skipped rows kept per file (the counts are always complete).
MAX_EXAMPLES_PER_FILE = 20
MAX_VALUE_LENGTH = 80
MAX_WARNINGS = 50


@dataclass
class FileStats:
    rows: int = 0
    imported: int = 0
    skipped: int = 0
    skip_reasons: Counter = field(default_factory=Counter)
    corrections: Counter = field(default_factory=Counter)
    examples: list = field(default_factory=list)

    def skip(self, row: int, reason: str, value: str | None = None) -> None:
        self.skipped += 1
        self.skip_reasons[reason] += 1
        if len(self.examples) < MAX_EXAMPLES_PER_FILE:
            example = {"row": row, "reason": reason}
            if value is not None:
                example["value"] = value[:MAX_VALUE_LENGTH]
            self.examples.append(example)

    def correct(self, reason: str) -> None:
        self.corrections[reason] += 1

    @property
    def skipped_ratio(self) -> float:
        return self.skipped / self.rows if self.rows else 0.0

    def as_dict(self) -> dict:
        return {
            "rows": self.rows,
            "imported": self.imported,
            "skipped": self.skipped,
            "skip_reasons": dict(self.skip_reasons.most_common()),
            "corrections": dict(self.corrections.most_common()),
            "examples": self.examples,
        }


@dataclass
class ImportReport:
    files: dict[str, FileStats] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    ignored_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timings_s: dict[str, float] = field(default_factory=dict)
    # Size check against the active version (pipeline._check_against_active); empty when
    # there was no active version or the import was forced.
    comparison: dict = field(default_factory=dict)

    def file(self, name: str) -> FileStats:
        if name not in self.files:
            self.files[name] = FileStats()
        return self.files[name]

    def warn(self, message: str) -> None:
        if len(self.warnings) < MAX_WARNINGS:
            self.warnings.append(message)

    def as_dict(self) -> dict:
        return {
            "files": {name: stats.as_dict() for name, stats in self.files.items()},
            "counts": dict(self.counts),
            "ignored_files": list(self.ignored_files),
            "warnings": list(self.warnings),
            "timings_s": {key: round(value, 2) for key, value in self.timings_s.items()},
            "comparison": dict(self.comparison),
        }


def format_report(report: dict, indent: str = "  ") -> list[str]:
    """Human-readable lines for a report dict (as stored on FeedVersion.report)."""
    lines = []
    counts = report.get("counts") or {}
    if counts:
        lines.append(indent + "rows: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    for name, stats in (report.get("files") or {}).items():
        if not stats.get("skipped") and not stats.get("corrections"):
            continue
        lines.append(
            f"{indent}{name}: read {stats['rows']}, imported {stats['imported']},"
            f" skipped {stats['skipped']}"
        )
        for reason, count in (stats.get("skip_reasons") or {}).items():
            lines.append(f"{indent}{indent}skipped {count}: {reason}")
        for reason, count in (stats.get("corrections") or {}).items():
            lines.append(f"{indent}{indent}corrected {count}: {reason}")
    if report.get("ignored_files"):
        lines.append(indent + "ignored files: " + ", ".join(report["ignored_files"]))
    for warning in report.get("warnings") or []:
        lines.append(f"{indent}warning: {warning}")
    comparison = report.get("comparison") or {}
    if comparison:
        parts = [
            f"{table} {comparison[table]['new']} (active {comparison[table]['active']})"
            for table in ("trips", "stop_times")
            if table in comparison
        ]
        lines.append(
            f"{indent}compared with active version {comparison.get('active_feed_version_id')}: "
            + ", ".join(parts)
        )
    timings = report.get("timings_s") or {}
    if timings:
        lines.append(indent + "timings: " + ", ".join(f"{k}={v}s" for k, v in timings.items()))
    return lines
