# VisionCop

VisionCop finds occurrences of a reference person in an image or video and reports the timestamps where the person appears.

## What it does

- Takes a **reference image** containing the person to find.
- Scans a **video** or a single **image** for faces.
- Compares every detected face with the reference face.
- Emits JSON and/or CSV results containing frame numbers, timestamps, match distance, and confidence.
- Optionally writes annotated media with bounding boxes for detected matches.

## Install

Python 3.10+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs the web UI, OpenCV, and NumPy. The face-recognition backend is optional at install time because it pulls in `dlib`, which often requires native C++ build tools on Windows. Install it when you are ready to run scans:

```bash
pip install -r requirements-face-recognition.txt
```

On Windows PowerShell, use the Windows activation script instead of `source`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activation script, allow scripts for the current user and try again:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
```

On Windows Command Prompt, use:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

Install the optional face-recognition backend only after the web UI dependencies are working:

```powershell
pip install -r requirements-face-recognition.txt
```

> `face-recognition` depends on `dlib`, which may require CMake and native build tools on some systems. If `dlib` fails on Windows with a Visual C++ error, install **Visual Studio Build Tools** with the **Desktop development with C++** workload, or use Conda/Miniconda and install a prebuilt `dlib` package before installing `face-recognition`.

## Usage

### Scan a video

```bash
python -m visioncop \
  --reference path/to/person.jpg \
  --input path/to/video.mp4 \
  --output-json occurrences.json \
  --output-csv occurrences.csv
```

### Scan every second frame and write annotated output

```bash
python -m visioncop \
  --reference path/to/person.jpg \
  --input path/to/video.mp4 \
  --sample-rate 1 \
  --annotated-output annotated.mp4
```

### Scan an image

```bash
python -m visioncop --reference person.jpg --input crowd.jpg --output-json result.json
```

## Output format

JSON output contains a summary and every match found:

```json
{
  "reference": "person.jpg",
  "input": "video.mp4",
  "media_type": "video",
  "tolerance": 0.6,
  "matches": [
    {
      "frame": 150,
      "timestamp_seconds": 5.0,
      "timestamp": "00:00:05.000",
      "distance": 0.42,
      "confidence": 0.3,
      "box": {"top": 80, "right": 220, "bottom": 210, "left": 90}
    }
  ],
  "occurrences": [
    {"start_seconds": 5.0, "end_seconds": 5.0, "start": "00:00:05.000", "end": "00:00:05.000"}
  ]
}
```

`occurrences` merges nearby matching frames into timestamp ranges. Use `--merge-gap-seconds` to control that behavior.

## Notes on accuracy and responsible use

Face recognition can produce false positives and false negatives, especially with poor lighting, occlusion, low-resolution video, large pose changes, or demographic imbalance in training data. Treat the output as investigative assistance, not definitive identification. Ensure you have the legal right and consent required to process biometric data in your jurisdiction.

## Friendly web interface

Start the local browser UI with:

```bash
python -m visioncop.web.app
# or, after installing the package:
visioncop-web
```

Then open <http://127.0.0.1:7860>. The UI supports both uploads and **server-side file paths**.

For very large videos, such as 10GB surveillance files, prefer file paths instead of browser uploads:

1. Put the video somewhere the VisionCop server can read, for example `/data/camera/case.mp4`.
2. Put the reference face image somewhere readable, for example `/data/refs/person.jpg`.
3. Paste those paths into the web form and start the scan.

This avoids copying huge files through the browser and lets OpenCV stream frames from disk. VisionCop processes video frame-by-frame and samples at the configured `--sample-rate`, so it does not load the whole video into memory. Lowering the sample rate, for example to `0.5` or `1`, is recommended for very large files when approximate occurrence times are acceptable.

## Large-video performance tips

- Use **server-side paths** for multi-gigabyte videos.
- Start with `--sample-rate 1` for one scan per second, then increase if you need finer timestamps.
- Leave annotated output off for the first pass; writing a second 10GB-style video can be slow and storage-heavy.
- Keep JSON/CSV result output enabled because those files are small and contain the occurrence timestamps.

### Fix: `ModuleNotFoundError: No module named 'flask'`

If the web UI fails with `ModuleNotFoundError: No module named 'flask'`, your virtual environment is active but the project dependencies have not been installed into it yet.

From the activated virtual environment, run:

```powershell
pip install -r requirements.txt
```

Then start the web UI again:

```powershell
python -m visioncop.web.app
```

If you only want to install the missing web dependency, run:

```powershell
pip install Flask
```

### Fix: `dlib` fails to build on Windows

If `pip install -r requirements-face-recognition.txt` fails while building `dlib` and says you must use Visual Studio to build a Python extension, the web UI dependencies can still be installed with:

```powershell
pip install -r requirements.txt
python -m visioncop.web.app
```

To enable actual face scanning on Windows, install one of these first:

1. **Visual Studio Build Tools** with the **Desktop development with C++** workload, then rerun:

   ```powershell
   pip install -r requirements-face-recognition.txt
   ```

2. Or use Conda/Miniconda for the face backend, which can provide prebuilt native packages:

   ```powershell
   conda install -c conda-forge dlib
   pip install face-recognition
   ```

The error is from `dlib`, not from Flask or the web UI.
