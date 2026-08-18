"""Decode GoPro ACCL from a GPMF blob onto the video's time base.

Each top-level DEVC record is one metadata packet; inside it, one STRM
holds the accelerometer stream (ACCL) and its SCAL divisor. Samples are
spread evenly across the packet's real duration so the resulting time
axis matches video.currentTime.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from gopro_accel.gpmf import decode_numbers, iter_klv


@dataclass
class Series:
    t: list[float] = field(default_factory=list)
    x: list[float] = field(default_factory=list)
    y: list[float] = field(default_factory=list)
    z: list[float] = field(default_factory=list)
    mag: list[float] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class AccelSeries:
    t: list[float] = field(default_factory=list)
    ax: list[float] = field(default_factory=list)
    ay: list[float] = field(default_factory=list)
    az: list[float] = field(default_factory=list)
    amag: list[float] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _packet_stream(devc_payload: bytes, key: str) -> tuple[list[tuple[float, float, float]], bool]:
    """Return (scaled xyz samples, missing_scal) for one DEVC payload and stream key."""
    for strm in iter_klv(devc_payload):
        if strm.key != "STRM":
            continue
        scal = None
        target = None
        for child in iter_klv(strm.payload):
            if child.key == "SCAL":
                scal = decode_numbers(child)[0][0]
            elif child.key == key:
                target = child
        if target is not None:
            divisor = float(scal) if scal else 1.0
            samples = [(x / divisor, y / divisor, z / divisor)
                       for x, y, z in decode_numbers(target)]
            return samples, scal is None
    return [], False


def parse_stream(
    blob: bytes,
    packet_times: list[tuple[float, float]],
    key: str,
    video_duration: float | None = None,
) -> Series:
    packets: list[list[tuple[float, float, float]]] = []
    missing_scal = False
    for devc in iter_klv(blob):
        if devc.key != "DEVC":
            continue
        samples, no_scal = _packet_stream(devc.payload, key)
        missing_scal = missing_scal or no_scal
        packets.append(samples)

    series = Series()
    aligned = len(packets) == len(packet_times) and len(packet_times) > 0

    if aligned:
        for samples, (pts, dur) in zip(packets, packet_times):
            n = len(samples)
            if n == 0:
                continue
            for j, (x, y, z) in enumerate(samples):
                series.t.append(pts + (j + 0.5) / n * dur)
                series.x.append(x)
                series.y.append(y)
                series.z.append(z)
    else:
        series.warnings.append(f"GPMF packet count mismatch ({key}); uniform timing")
        flat = [s for pk in packets for s in pk]
        n = len(flat)
        if video_duration:
            total = video_duration
        elif packet_times:
            total = packet_times[-1][0] + packet_times[-1][1]
        else:
            total = float(n)
        for i, (x, y, z) in enumerate(flat):
            series.t.append((i + 0.5) / n * total if n else 0.0)
            series.x.append(x)
            series.y.append(y)
            series.z.append(z)

    series.mag = [math.sqrt(x * x + y * y + z * z)
                  for x, y, z in zip(series.x, series.y, series.z)]
    if missing_scal:
        series.warnings.append(f"missing SCAL ({key}); raw units")
    return series


def parse_accel(
    blob: bytes,
    packet_times: list[tuple[float, float]],
    video_duration: float | None = None,
) -> AccelSeries:
    s = parse_stream(blob, packet_times, "ACCL", video_duration)
    return AccelSeries(t=s.t, ax=s.x, ay=s.y, az=s.z, amag=s.mag, warnings=s.warnings)
