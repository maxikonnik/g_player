# GoPro accelerometer player

A local web tool that opens a GoPro `.MP4`, extracts the accelerometer
readings from its GPMF metadata, and plots them on a clickable, zoomable
timeline under a video player. Clicking the curve seeks the video; a
playhead tracks playback. Built for inspecting skydive footage — the exit
spike and the opening shock are visible on the curve and one click away in
the video.

Zero third-party dependencies: pure Python standard library plus a
vanilla-JavaScript frontend. It only needs **ffmpeg / ffprobe** on your
`PATH` to read metadata and to transcode HEVC clips for playback.

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH` (e.g. `winget install Gyan.FFmpeg`, or
  your platform's package manager)

## Run

```bash
python -m gopro_accel --root "/path/to/folder/with/mp4s"
```

The browser opens at `http://127.0.0.1:8770/`. Pick a file from the list —
the video and its accelerometer graph load together. Point `--root` at a
folder that actually contains `.MP4` files, or use the **Обзор / Browse**
button to navigate the filesystem.

Options:

- `--root DIR` — a directory to browse (repeatable). Defaults to `./Samples`.
- `--port N` — HTTP port (default `8770`).
- `--no-open` — do not open the browser automatically.

### Windows quick launch

Instead of the command line you can use the bundled scripts (they `cd`
into the project for you and forward a folder argument):

```bat
run.bat "D:\GoPro\Jump1"
```

- Double-click `run.bat` to start with the default root, then pick files
  with the **Обзор** button.
- Or drag a folder of `.MP4` files onto `run.bat`.
- PowerShell users: `.\run.ps1 -Root "D:\GoPro\Jump1" -Port 8090`.

Both need `python` and `ffmpeg`/`ffprobe` on `PATH`.

## Features

- Accelerometer decoded from GPMF (`ACCL`), aligned to the video's own
  time base using per-packet ffprobe timing.
- Stacked telemetry graphs on a shared timeline: accelerometer `|a|`,
  gyroscope, gravity, and camera orientation (quaternion) — each with a
  `|magnitude|` / `X·Y·Z` toggle and a colour legend.
- On-frame telemetry overlays (toggleable): the current scene class from
  `SCEN` and face boxes with smile / blink from `FACE`, drawn over the
  video in 10 px Calibri in a contrasting colour.
- Millisecond timecode and a frame counter (`MM:SS.mmm · frame F / total`).
- Horizontal zoom: `+` / `−` buttons, drag-select a region, double-click to
  reset, a pan scrollbar, and playback auto-follow.
- Arrow keys `←` / `→` step the playhead — 1% of the visible window, or to
  the neighbouring sample once zoomed into individual readings.
- A numeric `m/s²` Y-axis scale.
- HEVC clips a browser cannot decode are transcoded to an H.264 proxy on
  demand.

## Tests

```bash
python -m pytest
```

Unit tests are pure (synthetic GPMF bytes, no media). Tests that need real
media are marked `integration`.

## How it works

- `gopro_accel/gpmf.py` — dependency-free GPMF (KLV) parser.
- `gopro_accel/ffprobe.py` — ffprobe/ffmpeg wrappers: stream discovery,
  per-packet timing, duration, frame rate, and the GPMF blob extractor.
- `gopro_accel/accel.py` — decodes `ACCL` onto the video time base.
- `gopro_accel/fsbrowse.py` — server-side filesystem browser with a
  path-safety guard.
- `gopro_accel/proxy.py` — lazy H.264 proxy for HEVC playback.
- `gopro_accel/server.py` — stdlib `http.server`: routing, Range video
  streaming, JSON endpoints.
- `gopro_accel/static/` — the vanilla-JS canvas player.
