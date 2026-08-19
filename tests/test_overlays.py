import struct

from gopro_accel.overlays import parse_scene, parse_faces


def _klv(key, type_char, sample_size, repeat, payload):
    header = key + type_char + bytes([sample_size]) + struct.pack(">H", repeat)
    pad = (-len(payload)) % 4
    return header + payload + b"\x00" * pad


def _scen_leaf(pairs):
    payload = b"".join(cc + struct.pack(">f", p) for cc, p in pairs)
    return _klv(b"SCEN", b"?", 8, len(pairs), payload)


def _face_leaf(faces):
    # x/y/w/h are unsigned shorts (0..65535 scaled by SCAL) — 'h' would
    # overflow for boxes past mid-frame (e.g. x=32768), so pack those
    # fields as 'H'.
    payload = b"".join(struct.pack(">BBhHHHHBB", 4, conf, i, x, y, w, h, sm, bl)
                        for i, (conf, x, y, w, h, sm, bl) in enumerate(faces))
    return _klv(b"FACE", b"?", 14, len(faces), payload)


def _devc(children):
    strm = _klv(b"STRM", b"\x00", 1, len(children), children)
    return _klv(b"DEVC", b"\x00", 1, len(strm), strm)


def test_parse_scene_picks_argmax_per_leaf():
    leaf = _scen_leaf([(b"SNOW", 0.1), (b"INDO", 0.6), (b"URBA", 0.3)])
    blob = _devc(_klv(b"TYPE", b"c", 2, 1, b"Ff") + leaf)
    s = parse_scene(blob, packet_times=[(0.0, 1.0)])
    assert s.code == ["INDO"]
    assert abs(s.prob[0] - 0.6) < 1e-6
    assert s.t == [0.5]


def test_parse_faces_decodes_scaled_boxes():
    scal = _klv(b"SCAL", b"S", 2, 9,
                struct.pack(">9H", 1, 1, 1, 65535, 65535, 65535, 65535, 1, 1))
    # one leaf with one face: box (0.5, 0.25) size (0.1, 0.2), smile 51, blink 0
    leaf = _face_leaf([(96, round(0.5 * 65535), round(0.25 * 65535),
                        round(0.1 * 65535), round(0.2 * 65535), 51, 0)])
    blob = _devc(_klv(b"TYPE", b"c", 2, 1, b"BBSSSSSBB") + scal + leaf)
    fs = parse_faces(blob, packet_times=[(0.0, 1.0)])
    assert fs.t == [0.5]
    f = fs.faces[0][0]
    assert abs(f["x"] - 0.5) < 1e-3 and abs(f["y"] - 0.25) < 1e-3
    assert abs(f["w"] - 0.1) < 1e-3 and abs(f["h"] - 0.2) < 1e-3
    assert f["smile"] == 51 and f["blink"] == 0 and f["conf"] == 96
