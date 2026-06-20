"""Utility helpers for VisionCop."""

from __future__ import annotations


def format_timestamp(seconds: float | None) -> str | None:
    """Format seconds as HH:MM:SS.mmm."""
    if seconds is None:
        return None

    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def merge_timestamps(timestamps: list[float], gap_seconds: float) -> list[tuple[float, float]]:
    """Merge sorted timestamps into ranges separated by no more than gap_seconds."""
    if not timestamps:
        return []

    sorted_times = sorted(timestamps)
    ranges: list[tuple[float, float]] = []
    start = previous = sorted_times[0]

    for timestamp in sorted_times[1:]:
        if timestamp - previous <= gap_seconds:
            previous = timestamp
            continue
        ranges.append((start, previous))
        start = previous = timestamp

    ranges.append((start, previous))
    return ranges
