# Gyroscope graph — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a second graph below the accelerometer scrubber showing the gyroscope (`GYRO`, rad/s), sharing the timeline/zoom/playhead, with its own Y-scale, legend, and `|ω|`/`X·Y·Z` toggle.

**Architecture:** The GPMF decoder is generalised to a `parse_stream(blob, times, key, ...)` producing a generic `Series`; `/api/accel` returns both `ACCL` and `GYRO`. The frontend `draw()` is refactored into a reusable `drawGraph(canvas, ctx, tArr, series, unit)` invoked for both graphs against one shared view window.

**Tech Stack:** Python stdlib backend, vanilla JS/Canvas frontend.

## Global Constraints

- Python 3.10+ (`from __future__ import annotations`, `X | None`); no new dependencies; pure decode logic unit-tested without media.
- Vanilla JS/HTML/CSS only; no framework/CDN. Frontend verified by manual acceptance (no JS harness).
- The gyro graph shares the view window, playhead, pan bar, zoom, drag-select, and arrow keys with the accelerometer graph.

---

## File structure

- Modify `gopro_accel/accel.py` — generic `Series` + `parse_stream`; `parse_accel` becomes a thin wrapper.
- Modify `gopro_accel/server.py` — `/api/accel` returns gyro arrays.
- Modify `gopro_accel/static/index.html` — second canvas, legend, gyro toggle.
- Modify `gopro_accel/static/style.css` — styles for the gyro row.
- Modify `gopro_accel/static/app.js` — `drawGraph` refactor, gyro config/legend/toggle, dual-canvas interactions.
- Modify `tests/test_accel.py` — unit test for `parse_stream` on a `GYRO` stream.

---

## Task 1: Decode GYRO in the backend

**Files:**
- Modify: `gopro_accel/accel.py`
- Modify: `gopro_accel/server.py`
- Test: `tests/test_accel.py`

**Interfaces:**
- Produces: `Series` (`t,x,y,z,mag,warnings`), `parse_stream(blob, packet_times, key, video_duration=None) -> Series`. `parse_accel` unchanged in signature/return (`AccelSeries`). `/api/accel` JSON gains `gt,gx,gy,gz,gmag`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_accel.py` (the file already defines `_klv`; add a stream-generic DEVC builder and a `parse_stream` gyro test):

```python
from gopro_accel.accel import parse_stream


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
    assert s.x == [1.0, 0.0]
    assert s.y == [0.0, 2.0]
    assert s.mag == [1.0, 2.0]
    assert s.warnings == []


def test_parse_stream_absent_key_is_empty_without_warning():
    blob = _devc_with_stream(b"ACCL", 1, [(1, 0, 0)])  # ACCL present, GYRO absent
    s = parse_stream(blob, packet_times=[(0.0, 1.0)], key="GYRO")
    assert s.t == [] and s.mag == []
    assert s.warnings == []
```

- [ ] **Step 2: Run it, expect failure**

Run: `python -m pytest tests/test_accel.py::test_parse_stream_decodes_gyro -v`
Expected: FAIL — `cannot import name 'parse_stream'`.

- [ ] **Step 3: Rewrite `accel.py` around a generic stream decoder**

Replace the entire body of `gopro_accel/accel.py` (keep the module docstring) with:

```python
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
```

- [ ] **Step 4: Return gyro from `/api/accel`**

In `gopro_accel/server.py`, change the import `from gopro_accel.accel import parse_accel` to `from gopro_accel.accel import parse_stream`, and replace the body of `_accel` (from `index = find_gpmf_stream_index(safe)` through the final `return self._json({...})`) with:

```python
            index = find_gpmf_stream_index(safe)
            if index is None:
                return self._json({"error": "no GPMF stream"}, 422)
            blob = extract_gpmf_blob(safe)
            times = gpmd_packet_times(safe, index)
            dur = probe_duration(safe)
            accel = parse_stream(blob, times, "ACCL", dur)
            gyro = parse_stream(blob, times, "GYRO", dur)
            if not accel.t:
                return self._json({"error": "no ACCL samples"}, 422)
            return self._json({
                "t": accel.t, "ax": accel.x, "ay": accel.y, "az": accel.z, "amag": accel.mag,
                "gt": gyro.t, "gx": gyro.x, "gy": gyro.y, "gz": gyro.z, "gmag": gyro.mag,
                "warnings": accel.warnings + gyro.warnings, "fps": probe_fps(safe),
            })
```

- [ ] **Step 5: Run the tests, expect pass**

Run: `python -m pytest tests/test_accel.py -v`
Expected: PASS — the two new `parse_stream` tests plus the existing `parse_accel` regression tests.

- [ ] **Step 6: Commit**

```bash
git add gopro_accel/accel.py gopro_accel/server.py tests/test_accel.py
git commit -m "feat: decode GYRO via a generic parse_stream; return it from /api/accel"
```

---

## Task 2: Gyro graph markup and styles

**Files:**
- Modify: `gopro_accel/static/index.html`
- Modify: `gopro_accel/static/style.css`

**Interfaces:**
- Produces DOM ids `#scrub2`, `#legend2`, and `.gbtn` toggle buttons (`data-m="mag"/"xyz"`).

- [ ] **Step 1: Add the gyro canvas, legend, and toggle to `index.html`**

Immediately AFTER the accelerometer `<div id="warnings"></div>` line and BEFORE the `<div id="modal" ...>` block, insert:

```html
  <canvas id="scrub2" height="240"></canvas>

  <div id="legend2"></div>

  <div class="controls">
    <span class="glabel">Гироскоп</span>
    <span class="spacer"></span>
    <div id="gmode">
      <button data-m="mag" class="gbtn on">|ω|</button>
      <button data-m="xyz" class="gbtn">X / Y / Z</button>
    </div>
  </div>
```

- [ ] **Step 2: Add styles to `style.css`**

Append to `gopro_accel/static/style.css`:

```css
#scrub2 { width: 100%; height: 120px; margin-top: 12px; background: #f4f4f2;
  border: 1px solid #ddd; border-radius: 8px; cursor: pointer; display: block; }
#legend2 { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 6px; font-size: 12px; color: #555; }
.glabel { font-size: 13px; color: #555; }
.gbtn { padding: 6px 14px; border: 1px solid #bbb; background: #fff; cursor: pointer; }
.gbtn.on { background: #eee; }
```

- [ ] **Step 3: Manual check**

Run `python -m gopro_accel --root "<folder with mp4s>"`, open a clip: a second empty canvas, a `Гироскоп` controls row with `|ω|` / `X / Y / Z`, and an empty legend appear below the accelerometer graph. No behaviour yet.

- [ ] **Step 4: Commit**

```bash
git add gopro_accel/static/index.html gopro_accel/static/style.css
git commit -m "feat: markup and styles for the gyroscope graph"
```

---

## Task 3: Render the gyro graph and share interactions

**Files:**
- Modify: `gopro_accel/static/app.js`

**Interfaces:**
- Consumes `gt/gx/gy/gz/gmag` from `/api/accel` (Task 1) and the DOM from Task 2.

- [ ] **Step 1: Add the gyro canvas refs, config, and mode state**

In `gopro_accel/static/app.js`, replace the `SERIES` const block (the `const SERIES = {...};`) with the accel config renamed plus the gyro config and mode/refs:

```javascript
const SERIES = {
  mag: [{ key: "amag", color: "#26215c", label: "|a|", width: 2.4 }],
  xyz: [
    { key: "ax", color: "#378ADD", label: "X", width: 1.4 },
    { key: "ay", color: "#1D9E75", label: "Y", width: 1.4 },
    { key: "az", color: "#D85A30", label: "Z", width: 1.4 },
  ],
};
const GYRO_SERIES = {
  mag: [{ key: "gmag", color: "#26215c", label: "|ω|", width: 2.4 }],
  xyz: [
    { key: "gx", color: "#378ADD", label: "X", width: 1.4 },
    { key: "gy", color: "#1D9E75", label: "Y", width: 1.4 },
    { key: "gz", color: "#D85A30", label: "Z", width: 1.4 },
  ],
};
let gmode = "mag";
const gcanvas = document.getElementById("scrub2");
const gctx = gcanvas.getContext("2d");
```

- [ ] **Step 2: Refactor `draw()` into a reusable `drawGraph`**

Replace the entire existing `function draw() { ... }` with the parameterised `drawGraph` plus a thin `draw()`:

```javascript
function drawGraph(cnv, cx, tArr, seriesDef, unit) {
  const w = cnv.width = cnv.clientWidth * 2;
  const h = cnv.height;
  cx.clearRect(0, 0, w, h);
  if (!data || !tArr || !tArr.length) return;
  if (!(viewEnd > viewStart)) resetView();
  const span = viewEnd - viewStart;
  const series = seriesDef.map((s) => [data[s.key], s.color, s.width]);
  let i0 = lowerBound(tArr, viewStart) - 1; if (i0 < 0) i0 = 0;
  let i1 = lowerBound(tArr, viewEnd); if (i1 > tArr.length - 1) i1 = tArr.length - 1;
  const visible = i1 - i0 + 1;
  let minv = Infinity, maxv = -Infinity;
  for (const [arr] of series) for (let i = i0; i <= i1; i++) { const v = arr[i]; if (v < minv) minv = v; if (v > maxv) maxv = v; }
  const mid = (minv + maxv) / 2, half = Math.max((maxv - minv) / 2, 0.5);
  const lo = mid - half * 1.15, hi = mid + half * 1.15;
  const pad = 8;
  const X = (t) => (t - viewStart) / span * w;
  const Y = (v) => h - pad - ((v - lo) / (hi - lo)) * (h - 2 * pad);
  cx.font = "22px system-ui, sans-serif";
  for (const tv of niceTicks(lo, hi, 4)) {
    const gy = Y(tv);
    cx.strokeStyle = "rgba(120,120,120,0.25)"; cx.lineWidth = 1;
    cx.beginPath(); cx.moveTo(0, gy); cx.lineTo(w, gy); cx.stroke();
    cx.fillStyle = "rgba(90,90,90,0.9)"; cx.textBaseline = "bottom";
    cx.fillText(tv.toFixed(1), 6, gy - 2);
  }
  cx.fillStyle = "rgba(90,90,90,0.9)"; cx.textBaseline = "top";
  cx.fillText(unit, 6, 4);
  const asDots = visible > 0 && w / visible > 8;
  for (const [arr, color, lw] of series) {
    cx.strokeStyle = color; cx.fillStyle = color; cx.lineWidth = lw;
    if (asDots) {
      cx.beginPath();
      for (let i = i0; i <= i1; i++) { const x = X(tArr[i]), y = Y(arr[i]); i === i0 ? cx.moveTo(x, y) : cx.lineTo(x, y); }
      cx.stroke();
      for (let i = i0; i <= i1; i++) { cx.beginPath(); cx.arc(X(tArr[i]), Y(arr[i]), 2.5, 0, 6.2832); cx.fill(); }
    } else {
      cx.beginPath();
      let px = -1, lo2 = Infinity, hi2 = -Infinity, started = false;
      for (let i = i0; i <= i1; i++) {
        const x = Math.floor(X(tArr[i]));
        if (x !== px && px >= 0) {
          if (!started) { cx.moveTo(px, Y(hi2)); started = true; } else { cx.lineTo(px, Y(hi2)); }
          cx.lineTo(px, Y(lo2));
          lo2 = Infinity; hi2 = -Infinity;
        }
        lo2 = Math.min(lo2, arr[i]); hi2 = Math.max(hi2, arr[i]); px = x;
      }
      if (px >= 0) {
        if (!started) cx.moveTo(px, Y(hi2)); else cx.lineTo(px, Y(hi2));
        cx.lineTo(px, Y(lo2));
      }
      cx.stroke();
    }
  }
  const t = video.currentTime || 0;
  if (t >= viewStart && t <= viewEnd) {
    const px = X(t);
    cx.strokeStyle = "#E24B4A"; cx.lineWidth = 2;
    cx.beginPath(); cx.moveTo(px, 0); cx.lineTo(px, h); cx.stroke();
  }
  if (selecting && dragging) {
    const a = X(Math.min(selStartTime, selCurTime)), b = X(Math.max(selStartTime, selCurTime));
    cx.fillStyle = "rgba(55,138,221,0.18)";
    cx.fillRect(a, 0, b - a, h);
  }
}

function draw() {
  drawGraph(canvas, ctx, data && data.t, SERIES[mode], "m/s²");
  drawGraph(gcanvas, gctx, data && data.gt, GYRO_SERIES[gmode], "rad/s");
  updatePanbar();
}
```

- [ ] **Step 3: Make `eventTime` use the event's own canvas and bind both canvases**

Replace `eventTime` so it reads the canvas the event fired on:

```javascript
function eventTime(e) {
  const r = e.currentTarget.getBoundingClientRect();
  const frac = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  return viewStart + frac * (viewEnd - viewStart);
}
```

Then, immediately AFTER the existing `canvas.addEventListener("dblclick", () => { resetView(); });` line, add the same two handlers for the gyro canvas:

```javascript
gcanvas.addEventListener("mousedown", (e) => {
  if (!data || !data.t.length) return;
  selecting = true; dragging = false; downX = e.clientX;
  downTime = eventTime(e); selStartTime = downTime; selCurTime = downTime;
});
gcanvas.addEventListener("dblclick", () => { resetView(); });
```

(The existing `window` `mousemove`/`mouseup` selection handlers are shared and need no change; the accelerometer `canvas` `mousedown` handler already sets `selecting`.)

- [ ] **Step 4: Render both legends and wire the gyro toggle**

Replace the `renderLegend` function and its initial call with a version that fills both legends, and add the `.gbtn` handler.

Replace:

```javascript
const legendEl = document.getElementById("legend");
function renderLegend() {
  legendEl.innerHTML = "";
  for (const s of SERIES[mode]) {
    const item = document.createElement("span");
    item.className = "legit";
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = s.color;
    item.appendChild(sw);
    item.appendChild(document.createTextNode(s.label));
    legendEl.appendChild(item);
  }
}
renderLegend();
```

with:

```javascript
const legendEl = document.getElementById("legend");
const legend2El = document.getElementById("legend2");
function renderLegendInto(el, seriesDef) {
  el.innerHTML = "";
  for (const s of seriesDef) {
    const item = document.createElement("span");
    item.className = "legit";
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = s.color;
    item.appendChild(sw);
    item.appendChild(document.createTextNode(s.label));
    el.appendChild(item);
  }
}
function renderLegend() {
  renderLegendInto(legendEl, SERIES[mode]);
  renderLegendInto(legend2El, GYRO_SERIES[gmode]);
}
renderLegend();

document.querySelectorAll(".gbtn").forEach((b) => {
  b.addEventListener("click", () => {
    gmode = b.dataset.m;
    document.querySelectorAll(".gbtn").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    renderLegend();
    draw();
  });
});
```

- [ ] **Step 5: Verify it parses**

Run `node --check gopro_accel/static/app.js` if node exists; otherwise re-read the whole file confirming brace/paren balance, exactly one `drawGraph`, one `draw`, one `renderLegend`, and that the old single-canvas `draw()` body is gone (grep for `SERIES[mode].map` returns only inside `draw`/none stray). Report the method.

- [ ] **Step 6: Manual acceptance**

Run `python -m gopro_accel --root "<folder with mp4s>"`, open a clip. Confirm:
- The gyro graph renders below with `rad/s` gridlines and a `|ω|` legend.
- Zooming (`+`/`−`, drag-select, double-click), panning, and clicking on EITHER graph moves both; the playhead tracks on both.
- Arrow keys still step the playhead; both graphs update.
- The gyro `|ω|` ↔ `X / Y / Z` toggle changes only the gyro trace/legend; the accel toggle changes only the accel trace/legend.
- A clip without a gyro stream shows an empty gyro canvas and no crash.

- [ ] **Step 7: Commit**

```bash
git add gopro_accel/static/app.js
git commit -m "feat: render the gyroscope graph sharing the timeline; gyro toggle and legend"
```

---

## Self-review

**Spec coverage:** GYRO decode → Task 1 (`parse_stream`, `_packet_stream`); both streams in `/api/accel` → Task 1 Step 4; second canvas/legend/toggle → Task 2; shared timeline/zoom/playhead with per-graph Y-fit/unit → Task 3 (`drawGraph` uses shared `viewStart/viewEnd`, own `tArr`/`unit`); interactions on either canvas → Task 3 Step 3 (`e.currentTarget`, both canvases bound); independent gyro toggle → Task 3 Step 4; no-gyro clip renders blank → `drawGraph` guard `!tArr.length`; `parse_accel` regression → Task 1 wrapper + existing tests.

**Placeholder scan:** none — full code for every step.

**Type/name consistency:** `Series`/`parse_stream` defined in Task 1 and consumed by `server.py` (Task 1 Step 4) and the test (Step 1); `AccelSeries`/`parse_accel` preserved for regression. Frontend: `GYRO_SERIES`/`gmode`/`gcanvas`/`gctx` defined in Task 3 Step 1 and used by `draw`/`renderLegend`/`.gbtn` handler; `drawGraph(cnv, cx, tArr, seriesDef, unit)` signature matches both call sites; `renderLegendInto(el, seriesDef)` used for both legends; DOM ids `#scrub2`/`#legend2`/`.gbtn` created in Task 2 and referenced in Task 3.
