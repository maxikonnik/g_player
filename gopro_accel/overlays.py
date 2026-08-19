"""Decode GoPro SCEN (scene classifier) and FACE (boxes + smile/blink)
onto the video time base for on-frame overlays.

Each STRM holds many leaves; every leaf is one time sample. A SCEN leaf is
6 records of `4-char code + float32` (the overlay shows the arg-max). A
FACE leaf holds `repeat` faces of 14 bytes each — `version, confidence,
id, x, y, w, h, smile, blink` — with per-field SCAL that normalises
x/y/w/h to 0..1 of the frame.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from gopro_accel.gpmf import decode_numbers, iter_klv

# id stays a signed short; x/y/w/h are unsigned shorts (0..65535, scaled
# by SCAL) — a signed 'h' would overflow for boxes past mid-frame.
_FACE_FMT = ">BBhHHHHBB"


@dataclass
class SceneSeries:
    t: list[float] = field(default_factory=list)
    code: list[str] = field(default_factory=list)
    prob: list[float] = field(default_factory=list)


@dataclass
class FaceSeries:
    t: list[float] = field(default_factory=list)
    faces: list[list[dict]] = field(default_factory=list)


def _strm_children(devc_payload: bytes, key: str):
    for strm in iter_klv(devc_payload):
        if strm.key != "STRM":
            continue
        children = list(iter_klv(strm.payload))
        if any(c.key == key for c in children):
            return children
    return None


def _timed(blob, packet_times, per_packet, video_duration):
    packets = [per_packet(d.payload) for d in iter_klv(blob) if d.key == "DEVC"]
    t: list[float] = []
    vals: list = []
    aligned = len(packets) == len(packet_times) and len(packet_times) > 0
    if aligned:
        for samples, (pts, dur) in zip(packets, packet_times):
            n = len(samples)
            for j, v in enumerate(samples):
                t.append(pts + (j + 0.5) / n * dur)
                vals.append(v)
    else:
        flat = [v for pk in packets for v in pk]
        n = len(flat)
        if video_duration:
            total = video_duration
        elif packet_times:
            total = packet_times[-1][0] + packet_times[-1][1]
        else:
            total = float(n)
        for i, v in enumerate(flat):
            t.append((i + 0.5) / n * total if n else 0.0)
            vals.append(v)
    return t, vals


def _scene_leaf(scen) -> tuple[str, float]:
    best_code, best_prob = "", -1.0
    p = scen.payload
    for i in range(scen.repeat):
        rec = p[i * 8:(i + 1) * 8]
        if len(rec) < 8:
            break
        prob = struct.unpack(">f", rec[4:8])[0]
        if prob > best_prob:
            best_prob = prob
            best_code = rec[:4].decode("latin-1").strip("\x00")
    return best_code, best_prob


def parse_scene(blob, packet_times, video_duration=None) -> SceneSeries:
    def per_packet(devc_payload):
        children = _strm_children(devc_payload, "SCEN")
        if not children:
            return []
        return [_scene_leaf(c) for c in children if c.key == "SCEN"]

    t, vals = _timed(blob, packet_times, per_packet, video_duration)
    s = SceneSeries()
    for ti, (code, prob) in zip(t, vals):
        s.t.append(ti)
        s.code.append(code)
        s.prob.append(prob)
    return s


def _flatten_scal(scal) -> list[float]:
    vals = [v for tup in decode_numbers(scal) for v in tup]
    while len(vals) < 9:
        vals.append(1)
    return [float(v) if v else 1.0 for v in vals]


def _face_leaf(face, scal) -> list[dict]:
    out = []
    p = face.payload
    for i in range(face.repeat):
        rec = p[i * 14:(i + 1) * 14]
        if len(rec) < 14:
            break
        _ver, conf, _id, x, y, w, h, smile, blink = struct.unpack(_FACE_FMT, rec)
        out.append({
            "conf": conf,
            "x": x / scal[3], "y": y / scal[4],
            "w": w / scal[5], "h": h / scal[6],
            "smile": smile, "blink": blink,
        })
    return out


def parse_faces(blob, packet_times, video_duration=None) -> FaceSeries:
    def per_packet(devc_payload):
        children = _strm_children(devc_payload, "FACE")
        if not children:
            return []
        scal_klv = next((c for c in children if c.key == "SCAL"), None)
        scal = _flatten_scal(scal_klv) if scal_klv else [1.0] * 9
        return [_face_leaf(c, scal) for c in children if c.key == "FACE"]

    t, vals = _timed(blob, packet_times, per_packet, video_duration)
    fs = FaceSeries()
    for ti, faces in zip(t, vals):
        fs.t.append(ti)
        fs.faces.append(faces)
    return fs
