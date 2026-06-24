"""Flask web frontend for running VisionCop scans."""

from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from flask import Flask, Response, jsonify, render_template, request, send_file
    from werkzeug.utils import secure_filename
except ImportError as exc:  # pragma: no cover - depends on optional web dependency installation
    Flask = Response = None  # type: ignore[assignment]
    jsonify = render_template = request = send_file = None  # type: ignore[assignment]
    secure_filename = None  # type: ignore[assignment]
    FLASK_IMPORT_ERROR: ImportError | None = exc
else:
    FLASK_IMPORT_ERROR = None

from visioncop.core import scan_media

DEFAULT_WORK_DIR = Path(os.environ.get("VISIONCOP_WORK_DIR", "./visioncop_runs")).resolve()


@dataclass
class Job:
    """Mutable scan job state for the lightweight local web server."""

    id: str
    status: str = "queued"
    progress: float = 0.0
    message: str = "Waiting to start"
    result_path: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    cancelled: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **changes: Any) -> None:
        with self.lock:
            for key, value in changes.items():
                setattr(self, key, value)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "id": self.id,
                "status": self.status,
                "progress": self.progress,
                "message": self.message,
                "result_path": self.result_path,
                "error": self.error,
                "result": self.result,
                "cancelled": self.cancelled,
            }


JOBS: dict[str, Job] = {}


def _save_uploads(field_name: str, destination: Path) -> list[Path]:
    outputs: list[Path] = []
    for upload in request.files.getlist(field_name):
        if upload is None or not upload.filename:
            continue
        safe_name = secure_filename(upload.filename) or f"{field_name}.bin"
        output = destination / safe_name
        upload.save(output)
        outputs.append(output)
    return outputs


def _split_paths(value: str) -> list[str]:
    return [part.strip() for chunk in value.splitlines() for part in chunk.split(";") if part.strip()]


def _resolve_inputs(field_name: str, upload_name: str, destination: Path) -> list[Path]:
    paths: list[Path] = []
    for path_text in _split_paths(request.form.get(field_name, "")):
        path = Path(path_text).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"File path does not exist: {path}")
        paths.append(path)

    paths.extend(_save_uploads(upload_name, destination))
    if not paths:
        raise ValueError(f"Provide one or more file paths or uploads for {field_name}.")
    return paths


def _attach_snapshot_urls(payload: dict[str, Any], job_id: str) -> dict[str, Any]:
    for match in payload.get("matches", []):
        snapshot_path = match.get("snapshot_path")
        if not snapshot_path:
            continue
        match["snapshot_url"] = f"/jobs/{job_id}/snapshots/{Path(snapshot_path).name}"
    return payload

def _run_job(
    job: Job,
    reference_paths: list[Path],
    input_paths: list[Path],
    tolerance: float,
    sample_rate: float,
    merge_gap_seconds: float,
    annotated_output: Path | None,
    output_json: Path,
    snapshot_dir: Path,
    mode: str,
) -> None:
    def on_progress(frame: int, total_frames: int | None, timestamp: float | None) -> None:
        if total_frames:
            progress = min(99.0, round(((frame + 1) / total_frames) * 100, 2))
            message = f"Scanned frame {frame:,} of {total_frames:,}"
        else:
            progress = job.progress
            when = f" at {timestamp:.1f}s" if timestamp is not None else ""
            message = f"Scanned frame {frame:,}{when}"
        job.update(status="running", progress=progress, message=message)

    try:
        job.update(status="running", progress=0.0, message="Starting scan")
        runs: list[dict[str, Any]] = []
        total_matches = 0
        total_runs = len(reference_paths) * len(input_paths)
        run_number = 0
        for reference_path in reference_paths:
            for input_path in input_paths:
                run_number += 1
                if job.cancelled:
                    raise RuntimeError("Scan cancelled")
                job.update(message=f"Scanning {run_number}/{total_runs}: {reference_path.name} in {input_path.name}")
                result = scan_media(
                    reference_path,
                    input_path,
                    tolerance=tolerance,
                    sample_rate=sample_rate,
                    merge_gap_seconds=merge_gap_seconds,
                    annotated_output=annotated_output if total_runs == 1 else None,
                    mode=mode,
                    snapshot_dir=snapshot_dir / f"run_{run_number}",
                    progress_callback=on_progress,
                    cancellation_callback=lambda: job.cancelled,
                )
                run_payload = _attach_snapshot_urls(result.to_dict(), job.id)
                run_payload["reference_name"] = reference_path.name
                run_payload["input_name"] = input_path.name
                runs.append(run_payload)
                total_matches += len(result.matches)

        payload = {"mode": mode, "runs": runs, "matches": [match for run in runs for match in run.get("matches", [])], "occurrences": [item for run in runs for item in run.get("occurrences", [])]}
        output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        job.update(
            status="complete",
            progress=100.0,
            message=f"Complete: {total_matches} matching frame(s) found across {total_runs} scan(s)",
            result_path=str(output_json),
            result=payload,
        )
    except Exception as exc:  # pragma: no cover - surfaced to browser for local app use
        if job.cancelled:
            job.update(status="cancelled", error=None, message="Scan cancelled by user")
        else:
            job.update(status="failed", error=str(exc), message="Scan failed")


def _web_dependency_error() -> str:
    return (
        "The VisionCop web UI requires Flask. Install dependencies with "
        "`pip install -r requirements.txt`, or install Flask directly with `pip install Flask`."
    )


def create_app(work_dir: Path | str = DEFAULT_WORK_DIR) -> Any:
    """Create the VisionCop web application."""
    if FLASK_IMPORT_ERROR is not None or Flask is None:
        raise RuntimeError(_web_dependency_error()) from FLASK_IMPORT_ERROR

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = None
    run_root = Path(work_dir).resolve()
    run_root.mkdir(parents=True, exist_ok=True)


    @app.after_request
    def add_cache_headers(response: Response) -> Response:
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.post("/jobs")
    def create_job() -> tuple[Response, int]:
        job_id = uuid.uuid4().hex
        job_dir = run_root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        try:
            reference_paths = _resolve_inputs("reference_path", "reference_upload", job_dir)
            input_paths = _resolve_inputs("input_path", "input_upload", job_dir)
            tolerance = float(request.form.get("tolerance", 0.6))
            sample_rate = float(request.form.get("sample_rate", 2.0))
            merge_gap_seconds = float(request.form.get("merge_gap_seconds", 1.5))
            annotated = request.form.get("annotated_output") == "on"
            mode = request.form.get("mode", "face")
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

        annotated_output = job_dir / "annotated.mp4" if annotated else None
        output_json = job_dir / "occurrences.json"
        snapshot_dir = job_dir / "snapshots"
        job = Job(id=job_id)
        JOBS[job_id] = job
        thread = threading.Thread(
            target=_run_job,
            args=(job, reference_paths, input_paths, tolerance, sample_rate, merge_gap_seconds, annotated_output, output_json, snapshot_dir, mode),
            daemon=True,
        )
        thread.start()
        return jsonify({"job_id": job_id}), 202

    @app.get("/jobs/<job_id>")
    def get_job(job_id: str) -> tuple[Response, int]:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "Unknown job"}), 404
        return jsonify(job.snapshot()), 200

    @app.post("/jobs/<job_id>/cancel")
    def cancel_job(job_id: str) -> tuple[Response, int]:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "Unknown job"}), 404
        if job.status in {"complete", "failed", "cancelled"}:
            return jsonify(job.snapshot()), 200
        job.update(cancelled=True, status="cancelling", message="Cancelling scan...")
        return jsonify(job.snapshot()), 202

    @app.get("/jobs/<job_id>/snapshots/<filename>")
    def get_snapshot(job_id: str, filename: str) -> Response | tuple[Response, int]:
        snapshot_root = run_root / job_id / "snapshots"
        matches = list(snapshot_root.rglob(filename))
        if not matches:
            return jsonify({"error": "Snapshot not found"}), 404
        return send_file(matches[0])

    @app.get("/jobs/<job_id>/download")
    def download_result(job_id: str) -> Response | tuple[Response, int]:
        job = JOBS.get(job_id)
        if job is None or not job.result_path:
            return jsonify({"error": "Result is not ready"}), 404
        return send_file(job.result_path, as_attachment=True, download_name="occurrences.json")

    return app


def main() -> int:
    """Run the local VisionCop web server."""
    if FLASK_IMPORT_ERROR is not None:
        print(_web_dependency_error(), file=sys.stderr)
        return 1

    host = os.environ.get("VISIONCOP_HOST", "127.0.0.1")
    port = int(os.environ.get("VISIONCOP_PORT", "7860"))
    create_app().run(host=host, port=port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
