"""Core face occurrence detection logic."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any, Iterable

from .utils import format_timestamp, merge_timestamps

IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm", ".wmv"}


@dataclass(frozen=True)
class Box:
    """Face bounding box in CSS order used by face_recognition."""

    top: int
    right: int
    bottom: int
    left: int


@dataclass(frozen=True)
class Match:
    """A matched face in a frame or image."""

    frame: int | None
    timestamp_seconds: float | None
    timestamp: str | None
    distance: float
    confidence: float
    box: Box


@dataclass(frozen=True)
class Occurrence:
    """A merged timestamp range where the person appears."""

    start_seconds: float
    end_seconds: float
    start: str
    end: str


@dataclass(frozen=True)
class ScanResult:
    """Complete scan result."""

    reference: str
    input: str
    media_type: str
    tolerance: float
    matches: list[Match]
    occurrences: list[Occurrence]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def _load_dependencies() -> tuple[Any, Any, Any]:
    try:
        import cv2  # type: ignore[import-not-found]
        import face_recognition  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "VisionCop requires face-recognition, opencv-python, and numpy. "
            "Install them with `pip install -r requirements.txt`."
        ) from exc
    return cv2, face_recognition, np


def detect_media_type(path: Path) -> str:
    """Detect whether the path is an image or video based on extension."""
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    raise ValueError(f"Unsupported input type for {path}. Use an image or video file.")


def _reference_encoding(reference_path: Path, face_recognition: Any) -> Any:
    image = face_recognition.load_image_file(str(reference_path))
    encodings = face_recognition.face_encodings(image)
    if not encodings:
        raise ValueError(f"No face found in reference image: {reference_path}")
    if len(encodings) > 1:
        raise ValueError(
            f"Reference image must contain exactly one face; found {len(encodings)} in {reference_path}"
        )
    return encodings[0]


def _confidence_from_distance(distance: float, tolerance: float) -> float:
    # Lower distance means a better match. Normalize into a simple user-facing score.
    if tolerance <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (distance / tolerance)))


def _matches_in_rgb_frame(
    rgb_frame: Any,
    reference_encoding: Any,
    face_recognition: Any,
    tolerance: float,
    frame_number: int | None,
    timestamp_seconds: float | None,
) -> list[Match]:
    locations = face_recognition.face_locations(rgb_frame)
    encodings = face_recognition.face_encodings(rgb_frame, locations)
    distances = face_recognition.face_distance(encodings, reference_encoding) if encodings else []

    matches: list[Match] = []
    for location, distance in zip(locations, distances):
        distance_value = float(distance)
        if distance_value > tolerance:
            continue
        box = Box(top=location[0], right=location[1], bottom=location[2], left=location[3])
        matches.append(
            Match(
                frame=frame_number,
                timestamp_seconds=timestamp_seconds,
                timestamp=format_timestamp(timestamp_seconds),
                distance=round(distance_value, 6),
                confidence=round(_confidence_from_distance(distance_value, tolerance), 6),
                box=box,
            )
        )
    return matches


def _draw_matches(cv2: Any, frame: Any, matches: Iterable[Match]) -> None:
    for match in matches:
        box = match.box
        label = f"match {match.confidence:.2f}"
        cv2.rectangle(frame, (box.left, box.top), (box.right, box.bottom), (0, 255, 0), 2)
        cv2.putText(frame, label, (box.left, max(0, box.top - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)


def scan_media(
    reference_path: str | Path,
    input_path: str | Path,
    *,
    tolerance: float = 0.6,
    sample_rate: float = 2.0,
    merge_gap_seconds: float = 1.5,
    annotated_output: str | Path | None = None,
    progress_callback: Callable[[int, int | None, float | None], None] | None = None,
) -> ScanResult:
    """Scan an image or video for occurrences of the person in reference_path."""
    cv2, face_recognition, _np = _load_dependencies()
    reference = Path(reference_path)
    source = Path(input_path)
    media_type = detect_media_type(source)
    reference_encoding = _reference_encoding(reference, face_recognition)

    if media_type == "image":
        image = face_recognition.load_image_file(str(source))
        matches = _matches_in_rgb_frame(image, reference_encoding, face_recognition, tolerance, None, None)
        if annotated_output:
            bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            _draw_matches(cv2, bgr, matches)
            cv2.imwrite(str(annotated_output), bgr)
        if progress_callback is not None:
            progress_callback(1, 1, None)
        return ScanResult(str(reference), str(source), media_type, tolerance, matches, [])

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError(f"Unable to open video: {source}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 0
    if fps <= 0:
        raise ValueError(f"Unable to determine FPS for video: {source}")

    frame_interval = max(1, int(round(fps / sample_rate))) if sample_rate > 0 else 1
    writer = None
    if annotated_output:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(annotated_output), fourcc, fps, (width, height))

    total_frames_value = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    total_frames = total_frames_value if total_frames_value > 0 else None

    matches: list[Match] = []
    frame_number = -1
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_number += 1
            frame_matches: list[Match] = []
            should_scan = frame_number % frame_interval == 0
            if should_scan:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp_seconds = frame_number / fps
                frame_matches = _matches_in_rgb_frame(
                    rgb_frame,
                    reference_encoding,
                    face_recognition,
                    tolerance,
                    frame_number,
                    timestamp_seconds,
                )
                matches.extend(frame_matches)
                if progress_callback is not None:
                    progress_callback(frame_number, total_frames, timestamp_seconds)
            if writer is not None:
                _draw_matches(cv2, frame, frame_matches)
                writer.write(frame)
    finally:
        capture.release()
        if writer is not None:
            writer.release()

    timestamps = [match.timestamp_seconds for match in matches if match.timestamp_seconds is not None]
    occurrences = [
        Occurrence(start, end, format_timestamp(start) or "", format_timestamp(end) or "")
        for start, end in merge_timestamps(timestamps, merge_gap_seconds)
    ]
    return ScanResult(str(reference), str(source), media_type, tolerance, matches, occurrences)
