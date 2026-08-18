import math
import struct

from gopro_accel.accel import parse_accel
from gopro_accel.accel import parse_stream


def _klv(key: bytes, type_char: bytes, sample_size: int, repeat: int, payload: bytes) -> bytes:
    header = key + type_char + bytes([sample_size]) + struct.pack(">H", repeat)
    pad = (-len(payload)) % 4
    return header + payload + b"\x00" * pad


def _devc_with_accl(scal: int | None, samples: list[tuple[int, int, int]]) -> bytes:
    children = b""
    if scal is not None:
        children += _klv(b"SCAL", b"s", 2, 1, struct.pack(">h", scal))
    payload = b"".join(struct.pack(">hhh", *s) for s in samples)
    children += _klv(b"ACCL", b"s", 6, len(samples), payload)
    strm = _klv(b"STRM", b"\x00", 1, len(children), children)
    return _klv(b"DEVC", b"\x00", 1, len(strm), strm)


def test_parse_accel_scales_and_times_per_packet():
    blob = _devc_with_accl(100, [(100, 0, 0), (0, 200, 0)])
    series = parse_accel(blob, packet_times=[(10.0, 1.0)])
    # two samples spread across the packet: centre of each half
    assert series.t == [10.25, 10.75]
    assert series.ax == [1.0, 0.0]
    assert series.ay == [0.0, 2.0]
    assert series.amag == [1.0, 2.0]
    assert series.warnings == []


def test_parse_accel_missing_scal_warns_and_keeps_raw():
    blob = _devc_with_accl(None, [(3, 4, 0)])
    series = parse_accel(blob, packet_times=[(0.0, 1.0)])
    assert series.amag == [5.0]  # raw 3-4-5, no scaling
    assert any("SCAL" in w for w in series.warnings)


def test_parse_accel_packet_mismatch_falls_back_to_uniform():
    # two DEVC packets, but only one packet_time -> uniform fallback over duration
    blob = _devc_with_accl(1, [(1, 0, 0)]) + _devc_with_accl(1, [(0, 1, 0)])
    series = parse_accel(blob, packet_times=[(0.0, 1.0)], video_duration=4.0)
    assert series.t == [1.0, 3.0]  # centres of two halves of [0, 4]
    assert any("mismatch" in w for w in series.warnings)


def _devc_with_stream(key: bytes, scal: int | None, samples: list[tuple[int, int, int]]) -> bytes:
    children = b""
    if scal is not None:
        children += _klv(b"SCAL", b"s", 2, 1, struct.pack(">h", scal))
    payload = b"".join(struct.pack(">hhh", *s) for s in samples)
    children += _klv(key, b"s", 6, len(samples), payload)
    strm = _klv(b"STRM", b"\x00", 1, len(children), children)
    return _klv(b"DEVC", b"\x00", 1, len(strm), strm)


def test_parse_stream_decodes_gyro():
    blob = _devc_with_stream(b"GYRO", 100, [(100, 0, 0), (0, 200, 0)])
    s = parse_stream(blob, packet_times=[(10.0, 1.0)], key="GYRO")
    assert s.t == [10.25, 10.75]
    assert s.comps[0] == [1.0, 0.0]
    assert s.comps[1] == [0.0, 2.0]
    assert s.mag == [1.0, 2.0]
    assert s.warnings == []


def test_parse_stream_decodes_quaternion():
    children = _klv(b"SCAL", b"s", 2, 1, struct.pack(">h", 100))
    samples = [(100, 0, 0, 0), (0, 100, 0, 100)]
    payload = b"".join(struct.pack(">hhhh", *s) for s in samples)
    children += _klv(b"CORI", b"s", 8, len(samples), payload)
    strm = _klv(b"STRM", b"\x00", 1, len(children), children)
    blob = _klv(b"DEVC", b"\x00", 1, len(strm), strm)
    s = parse_stream(blob, packet_times=[(0.0, 1.0)], key="CORI")
    assert len(s.comps) == 4
    assert s.comps[0] == [1.0, 0.0]
    assert s.comps[3] == [0.0, 1.0]
    assert s.mag[0] == 1.0
    assert abs(s.mag[1] - math.sqrt(2)) < 1e-9


def test_parse_stream_absent_key_is_empty_without_warning():
    blob = _devc_with_stream(b"ACCL", 1, [(1, 0, 0)])  # ACCL present, GYRO absent
    s = parse_stream(blob, packet_times=[(0.0, 1.0)], key="GYRO")
    assert s.t == [] and s.mag == []
    assert s.warnings == []
