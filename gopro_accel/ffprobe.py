"""Thin wrappers over ffprobe/ffmpeg. Pure helpers are separated from
subprocess calls so the logic is testable without media files."""
from __future__ import annotations

import json
import shutil
import subprocess


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _run_json(args: list[str]) -> dict:
    out = subprocess.run(args, check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def ffprobe_streams(path: str) -> list[dict]:
    data = _run_json(["ffprobe", "-v", "error", "-show_streams",
                      "-print_format", "json", path])
    return data.get("streams", [])


def _select_gpmf_index(streams: list[dict]) -> int | None:
    for s in streams:
        if s.get("codec_tag_string") == "gpmd":
            return int(s["index"])
        handler = s.get("tags", {}).get("handler_name", "")
        if "GoPro MET" in handler:
            return int(s["index"])
    return None


def find_gpmf_stream_index(path: str) -> int | None:
    return _select_gpmf_index(ffprobe_streams(path))


def _parse_packet_times(data: dict) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for pkt in data.get("packets", []):
        pts = pkt.get("pts_time")
        dur = pkt.get("duration_time")
        if pts is not None and dur is not None:
            pairs.append((float(pts), float(dur)))
    return pairs


def gpmd_packet_times(path: str, stream_index: int) -> list[tuple[float, float]]:
    data = _run_json([
        "ffprobe", "-v", "error", "-select_streams", str(stream_index),
        "-show_packets", "-show_entries", "packet=pts_time,duration_time",
        "-print_format", "json", path,
    ])
    return _parse_packet_times(data)


def probe_duration(path: str) -> float | None:
    data = _run_json([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-print_format", "json", path,
    ])
    raw = data.get("format", {}).get("duration")
    return float(raw) if raw is not None else None


def _parse_fps(text: str | None) -> float | None:
    if not text:
        return None
    try:
        if "/" in text:
            num_s, den_s = text.split("/", 1)
            num, den = float(num_s), float(den_s)
            if den == 0:
                return None
            return num / den
        return float(text) or None
    except ValueError:
        return None


def probe_fps(path: str) -> float | None:
    data = _run_json([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-print_format", "json", path,
    ])
    streams = data.get("streams", [])
    if not streams:
        return None
    return _parse_fps(streams[0].get("r_frame_rate"))


def extract_gpmf_blob(path: str) -> bytes:
    index = find_gpmf_stream_index(path)
    if index is None:
        return b""
    out = subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-map", f"0:{index}",
         "-codec", "copy", "-f", "data", "-"],
        check=True, capture_output=True,
    )
    return out.stdout
