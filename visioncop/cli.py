"""Command line interface for VisionCop."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .core import Match, scan_media


def _write_csv(path: Path, matches: list[Match]) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["frame", "timestamp_seconds", "timestamp", "distance", "confidence", "top", "right", "bottom", "left"],
        )
        writer.writeheader()
        for match in matches:
            writer.writerow(
                {
                    "frame": match.frame,
                    "timestamp_seconds": match.timestamp_seconds,
                    "timestamp": match.timestamp,
                    "distance": match.distance,
                    "confidence": match.confidence,
                    "top": match.box.top,
                    "right": match.box.right,
                    "bottom": match.box.bottom,
                    "left": match.box.left,
                }
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find a reference person's face in an image or video.")
    parser.add_argument("--reference", required=True, help="Image containing exactly one face to search for.")
    parser.add_argument("--input", required=True, help="Image or video to scan.")
    parser.add_argument("--tolerance", type=float, default=0.6, help="Face distance threshold; lower is stricter. Default: 0.6")
    parser.add_argument("--sample-rate", type=float, default=2.0, help="Video frames to scan per second. Default: 2")
    parser.add_argument("--merge-gap-seconds", type=float, default=1.5, help="Gap for merging video matches into occurrences.")
    parser.add_argument("--output-json", help="Path to write JSON results. Prints to stdout if omitted.")
    parser.add_argument("--output-csv", help="Path to write per-match CSV results.")
    parser.add_argument("--annotated-output", help="Optional path for annotated image/video output.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    result = scan_media(
        args.reference,
        args.input,
        tolerance=args.tolerance,
        sample_rate=args.sample_rate,
        merge_gap_seconds=args.merge_gap_seconds,
        annotated_output=args.annotated_output,
    )
    payload = result.to_dict()

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        print(json.dumps(payload, indent=2))

    if args.output_csv:
        _write_csv(Path(args.output_csv), result.matches)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
