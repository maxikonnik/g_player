# Gravity and orientation graphs — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add gravity (`GRAV`), camera-orientation (`CORI`), and image-orientation (`IORI`) graphs below the accel/gyro graphs, and refactor the frontend to a data-driven list of graphs.

**Architecture:** The GPMF decoder is generalised to N components per sample (3 for vectors, 4 for quaternions); `/api/accel` returns all five streams. The frontend renders a `GRAPHS` list through the existing `drawGraph`.

**Tech Stack:** Python stdlib backend, vanilla JS/Canvas frontend.

## Global Constraints

- Python 3.10+ (`from __future__ import annotations`, `X | None`); no new deps; pure decode unit-tested.
- Vanilla JS/HTML/CSS only; no framework/CDN. Frontend verified by manual acceptance.
- All graphs share the view window, playhead, pan bar, zoom, and arrow keys; each has its own data, Y-fit, unit, and legend.

---

## File structure

- Modify `gopro_accel/accel.py` — `Series.comps` (N components); `parse_stream` generalised.
- Modify `gopro_accel/server.py` — return GRAV/CORI/IORI arrays.
- Modify `gopro_accel/static/index.html` — three more canvases, legends, grav toggle, labels.
- Modify `gopro_accel/static/style.css` — styles for the new rows.
- Modify `gopro_accel/static/app.js` — data-driven `GRAPHS`; draw/legend/toggle/interaction loops.
- Modify `tests/test_accel.py` — quaternion `parse_stream` test; update the gyro test to `comps`.

---

## Task 1: Decode GRAV/CORI/IORI (N components)

**Files:**
- Modify: `gopro_accel/accel.py`
- Modify: `gopro_accel/server.py`
- Test: `tests/test_accel.py`

**Interfaces:**
- Produces: `Series` with `comps: list[list[float]]`; `parse_stream(blob, times, key, video_duration=None) -> Series`. `parse_accel` unchanged (`AccelSeries`). `/api/accel` gains `gvt/gvx/gvy/gvz/gvmag`, `cot/cow/cox/coy/coz`, `iot/iow/iox/ioy/ioz`.

- [ ] **Step 1: Update the gyro test to `comps` and add a quaternion test**

In `tests/test_accel.py`: add `import math` near the top if absent. Replace the body of `test_parse_stream_decodes_gyro` so it reads `comps`:

```python
def test_parse_stream_decodes_gyro():
    blob = _devc_with_stream(b"GYRO", 100, [(100, 0, 0), (0, 200, 0)])
    s = parse_stream(blob, packet_times=[(10.0, 1.0)], key="GYRO")
    assert s.t == [10.25, 10.75]
    assert s.comps[0] == [1.0, 0.0]
    assert s.comps[1] == [0.0, 2.0]
    assert s.mag == [1.0, 2.0]
    assert s.warnings == []
```

Add a new 4-component test:

```python
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
```

- [ ] **Step 2: Run, expect failure**

Run: `python -m pytest tests/test_accel.py -v`
Expected: FAIL — `test_parse_stream_decodes_gyro` (no `comps` attr yet) and the new quaternion test error.

- [ ] **Step 3: Generalise `accel.py` to N components**

Replace the entire body of `gopro_accel/accel.py` (keep the module docstring at the top) with:

```python
from __future__ import annotations

import math
from dataclasses import dataclass, field

from gopro_accel.gpmf import decode_numbers, iter_klv


@dataclass
class Series:
    t: list[float] = field(default_factory=list)
    comps: list[list[float]] = field(default_factory=list)
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


def _packet_stream(devc_payload: bytes, key: str) -> tuple[list[tuple[float, ...]], bool]:
    """Return (scaled samples, missing_scal) for one DEVC payload and stream key."""
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
            samples = [tuple(v / divisor for v in row) for row in decode_numbers(target)]
            return samples, scal is None
    return [], False


def parse_stream(
    blob: bytes,
    packet_times: list[tuple[float, float]],
    key: str,
    video_duration: float | None = None,
) -> Series:
    packets: list[list[tuple[float, ...]]] = []
    missing_scal = False
    for devc in iter_klv(blob):
        if devc.key != "DEVC":
            continue
        samples, no_scal = _packet_stream(devc.payload, key)
        missing_scal = missing_scal or no_scal
        packets.append(samples)

    n_comp = 0
    for pk in packets:
        if pk:
            n_comp = len(pk[0])
            break

    series = Series(comps=[[] for _ in range(n_comp)])
    aligned = len(packets) == len(packet_times) and len(packet_times) > 0

    if aligned:
        for samples, (pts, dur) in zip(packets, packet_times):
            n = len(samples)
            if n == 0:
                continue
            for j, row in enumerate(samples):
                series.t.append(pts + (j + 0.5) / n * dur)
                for c, v in enumerate(row):
                    series.comps[c].append(v)
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
        for i, row in enumerate(flat):
            series.t.append((i + 0.5) / n * total if n else 0.0)
            for c, v in enumerate(row):
                series.comps[c].append(v)

    series.mag = [math.sqrt(sum(v * v for v in row)) for row in zip(*series.comps)]
    if missing_scal:
        series.warnings.append(f"missing SCAL ({key}); raw units")
    return series


def parse_accel(
    blob: bytes,
    packet_times: list[tuple[float, float]],
    video_duration: float | None = None,
) -> AccelSeries:
    s = parse_stream(blob, packet_times, "ACCL", video_duration)

    def comp(i: int) -> list[float]:
        return s.comps[i] if i < len(s.comps) else []

    return AccelSeries(t=s.t, ax=comp(0), ay=comp(1), az=comp(2), amag=s.mag, warnings=s.warnings)
```

- [ ] **Step 4: Return the new streams from `/api/accel`**

In `gopro_accel/server.py`, replace the `_accel` method body from `index = find_gpmf_stream_index(safe)` through the final `return self._json({...})` with:

```python
            index = find_gpmf_stream_index(safe)
            if index is None:
                return self._json({"error": "no GPMF stream"}, 422)
            blob = extract_gpmf_blob(safe)
            times = gpmd_packet_times(safe, index)
            dur = probe_duration(safe)
            accel = parse_stream(blob, times, "ACCL", dur)
            if not accel.t:
                return self._json({"error": "no ACCL samples"}, 422)
            gyro = parse_stream(blob, times, "GYRO", dur)
            grav = parse_stream(blob, times, "GRAV", dur)
            cori = parse_stream(blob, times, "CORI", dur)
            iori = parse_stream(blob, times, "IORI", dur)

            def comp(s, i):
                return s.comps[i] if i < len(s.comps) else []

            return self._json({
                "t": accel.t, "ax": comp(accel, 0), "ay": comp(accel, 1), "az": comp(accel, 2), "amag": accel.mag,
                "gt": gyro.t, "gx": comp(gyro, 0), "gy": comp(gyro, 1), "gz": comp(gyro, 2), "gmag": gyro.mag,
                "gvt": grav.t, "gvx": comp(grav, 0), "gvy": comp(grav, 1), "gvz": comp(grav, 2), "gvmag": grav.mag,
                "cot": cori.t, "cow": comp(cori, 0), "cox": comp(cori, 1), "coy": comp(cori, 2), "coz": comp(cori, 3),
                "iot": iori.t, "iow": comp(iori, 0), "iox": comp(iori, 1), "ioy": comp(iori, 2), "ioz": comp(iori, 3),
                "warnings": accel.warnings + gyro.warnings + grav.warnings + cori.warnings + iori.warnings,
                "fps": probe_fps(safe),
            })
```

(The `parse_stream` import already exists in `server.py`.)

- [ ] **Step 5: Run tests, expect pass**

Run: `python -m pytest -q`
Expected: PASS (all — the updated gyro test, the new quaternion test, and the unchanged `parse_accel` regression tests).

- [ ] **Step 6: Commit**

```bash
git add gopro_accel/accel.py gopro_accel/server.py tests/test_accel.py
git commit -m "feat: decode GRAV/CORI/IORI (N-component streams); return them from /api/accel"
```

---

## Task 2: Markup and styles for the three new graphs

**Files:**
- Modify: `gopro_accel/static/index.html`
- Modify: `gopro_accel/static/style.css`

**Interfaces:**
- Produces DOM ids `#scrub3`/`#scrub4`/`#scrub5`, `#legend3`/`#legend4`/`#legend5`, and `.rbtn` grav-toggle buttons.

- [ ] **Step 1: Add the three graph blocks to `index.html`**

Immediately AFTER the gyroscope `.controls` row (the `<div class="controls">` block containing `Гироскоп` and the `#gmode` `.gbtn` buttons) and BEFORE the `<div id="modal" ...>` block, insert:

```html
  <canvas id="scrub3" height="240"></canvas>
  <div id="legend3"></div>
  <div class="controls">
    <span class="glabel">Гравитация</span>
    <span class="spacer"></span>
    <div id="rmode">
      <button data-m="mag" class="rbtn">|g|</button>
      <button data-m="xyz" class="rbtn on">X / Y / Z</button>
    </div>
  </div>

  <canvas id="scrub4" height="240"></canvas>
  <div id="legend4"></div>
  <div class="controls"><span class="glabel">Ориентация камеры (кватернион)</span></div>

  <canvas id="scrub5" height="240"></canvas>
  <div id="legend5"></div>
  <div class="controls"><span class="glabel">Ориентация изображения (кватернион)</span></div>
```

- [ ] **Step 2: Add styles to `style.css`**

Append to `gopro_accel/static/style.css`:

```css
#scrub3, #scrub4, #scrub5 { width: 100%; height: 120px; margin-top: 12px; background: #f4f4f2;
  border: 1px solid #ddd; border-radius: 8px; cursor: pointer; display: block; }
#legend3, #legend4, #legend5 { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 6px; font-size: 12px; color: #555; }
.rbtn { padding: 6px 14px; border: 1px solid #bbb; background: #fff; cursor: pointer; }
.rbtn.on { background: #eee; }
```

- [ ] **Step 3: Manual check**

Run `python -m gopro_accel --root "<folder with mp4s>"`, open a clip: three more empty canvases appear below the gyro graph, with `Гравитация` (|g| / X·Y·Z toggle), `Ориентация камеры`, and `Ориентация изображения` rows. No behaviour yet.

- [ ] **Step 4: Commit**

```bash
git add gopro_accel/static/index.html gopro_accel/static/style.css
git commit -m "feat: markup and styles for gravity and orientation graphs"
```

---

## Task 3: Data-driven graph list (render all five)

**Files:**
- Modify: `gopro_accel/static/app.js`

**Interfaces:**
- Consumes the Task 1 arrays and the Task 2 DOM.

- [ ] **Step 1: Replace the SERIES/GYRO config block with a `GRAPHS` list**

Replace this exact block (the `const SERIES = {...}` through `const gctx = gcanvas.getContext("2d");`):

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

with:

```javascript
const COL = { x: "#378ADD", y: "#1D9E75", z: "#D85A30", w: "#7F77DD", mag: "#26215c" };
function vecModes(magKey, magLabel, xk, yk, zk) {
  return {
    mag: [{ key: magKey, color: COL.mag, label: magLabel, width: 2.4 }],
    xyz: [
      { key: xk, color: COL.x, label: "X", width: 1.4 },
      { key: yk, color: COL.y, label: "Y", width: 1.4 },
      { key: zk, color: COL.z, label: "Z", width: 1.4 },
    ],
  };
}
function quat(wk, xk, yk, zk) {
  return [
    { key: wk, color: COL.w, label: "W", width: 1.4 },
    { key: xk, color: COL.x, label: "X", width: 1.4 },
    { key: yk, color: COL.y, label: "Y", width: 1.4 },
    { key: zk, color: COL.z, label: "Z", width: 1.4 },
  ];
}
const GRAPHS = [
  { canvasId: "scrub",  legendId: "legend",  toggleSel: ".mbtn", tKey: "t",   unit: "m/s²",  modes: vecModes("amag", "|a|", "ax", "ay", "az"),    mode: "mag" },
  { canvasId: "scrub2", legendId: "legend2", toggleSel: ".gbtn", tKey: "gt",  unit: "rad/s", modes: vecModes("gmag", "|ω|", "gx", "gy", "gz"),    mode: "mag" },
  { canvasId: "scrub3", legendId: "legend3", toggleSel: ".rbtn", tKey: "gvt", unit: "g",     modes: vecModes("gvmag", "|g|", "gvx", "gvy", "gvz"), mode: "xyz" },
  { canvasId: "scrub4", legendId: "legend4", tKey: "cot", unit: "", fixed: quat("cow", "cox", "coy", "coz") },
  { canvasId: "scrub5", legendId: "legend5", tKey: "iot", unit: "", fixed: quat("iow", "iox", "ioy", "ioz") },
];
for (const g of GRAPHS) {
  g.cnv = document.getElementById(g.canvasId);
  g.cx = g.cnv.getContext("2d");
  g.legendEl = document.getElementById(g.legendId);
}
function graphSeries(g) { return g.fixed || g.modes[g.mode]; }
```

- [ ] **Step 2: Replace `draw()` with a loop over `GRAPHS`**

Replace this exact block:

```javascript
function draw() {
  drawGraph(canvas, ctx, data && data.t, SERIES[mode], "m/s²");
  drawGraph(gcanvas, gctx, data && data.gt, GYRO_SERIES[gmode], "rad/s");
  updatePanbar();
}
```

with:

```javascript
function draw() {
  for (const g of GRAPHS) {
    drawGraph(g.cnv, g.cx, data && data[g.tKey], graphSeries(g), g.unit);
  }
  updatePanbar();
}
```

- [ ] **Step 3: Bind interactions to every graph canvas**

Replace this exact block (the accel `canvas` mousedown, the two `window` selection handlers, the accel `dblclick`, and the `gcanvas` mousedown/dblclick — from `canvas.addEventListener("mousedown"` through `gcanvas.addEventListener("dblclick", () => { resetView(); });`):

```javascript
canvas.addEventListener("mousedown", (e) => {
  activeCanvas = e.currentTarget;
  if (!data || !data.t.length) return;
  selecting = true; dragging = false; downX = e.clientX;
  downTime = eventTime(e); selStartTime = downTime; selCurTime = downTime;
});
window.addEventListener("mousemove", (e) => {
  if (!selecting) return;
  if (!(e.buttons & 1)) { selecting = false; dragging = false; return; }
  if (!dragging && Math.abs(e.clientX - downX) > DRAG_PX) dragging = true;
  if (dragging) selCurTime = eventTime(e);
});
window.addEventListener("mouseup", () => {
  if (!selecting) return;
  selecting = false;
  if (dragging) {
    [viewStart, viewEnd] = clampView(Math.min(selStartTime, selCurTime), Math.max(selStartTime, selCurTime));
    userZoomed = true;
  } else {
    video.currentTime = downTime;
  }
  dragging = false;
});
canvas.addEventListener("dblclick", () => { resetView(); });

gcanvas.addEventListener("mousedown", (e) => {
  activeCanvas = e.currentTarget;
  if (!data || !data.t.length) return;
  selecting = true; dragging = false; downX = e.clientX;
  downTime = eventTime(e); selStartTime = downTime; selCurTime = downTime;
});
gcanvas.addEventListener("dblclick", () => { resetView(); });
```

with:

```javascript
window.addEventListener("mousemove", (e) => {
  if (!selecting) return;
  if (!(e.buttons & 1)) { selecting = false; dragging = false; return; }
  if (!dragging && Math.abs(e.clientX - downX) > DRAG_PX) dragging = true;
  if (dragging) selCurTime = eventTime(e);
});
window.addEventListener("mouseup", () => {
  if (!selecting) return;
  selecting = false;
  if (dragging) {
    [viewStart, viewEnd] = clampView(Math.min(selStartTime, selCurTime), Math.max(selStartTime, selCurTime));
    userZoomed = true;
  } else {
    video.currentTime = downTime;
  }
  dragging = false;
});
for (const g of GRAPHS) {
  g.cnv.addEventListener("mousedown", (e) => {
    activeCanvas = e.currentTarget;
    if (!data || !data.t.length) return;
    selecting = true; dragging = false; downX = e.clientX;
    downTime = eventTime(e); selStartTime = downTime; selCurTime = downTime;
  });
  g.cnv.addEventListener("dblclick", () => { resetView(); });
}
```

- [ ] **Step 4: Replace the legend + toggle handlers with loops**

Replace this exact block (the `.mbtn` handler, the `legendEl`/`legend2El` + `renderLegendInto` + `renderLegend` + `renderLegend();` call, and the `.gbtn` handler — from `document.querySelectorAll(".mbtn").forEach` through the `.gbtn` handler's closing `});`):

```javascript
document.querySelectorAll(".mbtn").forEach((b) => {
  b.addEventListener("click", () => {
    mode = b.dataset.m;
    document.querySelectorAll(".mbtn").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    renderLegend();
    draw();
  });
});

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

with:

```javascript
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
  for (const g of GRAPHS) renderLegendInto(g.legendEl, graphSeries(g));
}
renderLegend();

for (const g of GRAPHS) {
  if (!g.toggleSel) continue;
  document.querySelectorAll(g.toggleSel).forEach((b) => {
    b.addEventListener("click", () => {
      g.mode = b.dataset.m;
      document.querySelectorAll(g.toggleSel).forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      renderLegend();
      draw();
    });
  });
}
```

Note: the top-level `let mode = "mag";` and the `const canvas`/`const ctx` (accel) declarations stay — `canvas`/`ctx` are still used by `stepPlayhead`, `eventTime`, and `duration`. The removed `SERIES`/`GYRO_SERIES`/`gmode`/`gcanvas`/`gctx` names must have no remaining references after these edits.

- [ ] **Step 5: Verify it parses**

Run `node --check gopro_accel/static/app.js` if node exists; otherwise re-read the whole file confirming: brace/paren balance; exactly one `GRAPHS`, one `draw`, one `renderLegend`; and grep confirms NO remaining references to `SERIES`, `GYRO_SERIES`, `gmode`, `gcanvas`, `gctx` (all replaced). Report the method and grep result.

- [ ] **Step 6: Manual acceptance**

Run `python -m gopro_accel --root "<folder with mp4s>"`, open a clip. Confirm:
- Five graphs stack: accel (m/s²), gyro (rad/s), gravity (g), camera orientation (quaternion W/X/Y/Z), image orientation (quaternion). Each has a legend; grav has a working |g| / X·Y·Z toggle (default X·Y·Z); the quaternion graphs show four W/X/Y/Z traces.
- Zoom (+/−, drag-select, double-click), pan, and click-seek on ANY graph move all five; the playhead tracks on all.
- Arrow keys still step; accel and gyro toggles still work.
- A clip missing a stream shows that graph blank, no console error.

- [ ] **Step 7: Commit**

```bash
git add gopro_accel/static/app.js
git commit -m "feat: data-driven graph list rendering accel, gyro, gravity, and orientation"
```

---

## Self-review

**Spec coverage:** GRAV/CORI/IORI decode with N components → Task 1 (`Series.comps`, `parse_stream`); all five in `/api/accel` → Task 1 Step 4; three canvases/legends/labels + grav toggle → Task 2; data-driven `GRAPHS` rendering, legend, toggle, interaction loops → Task 3; grav default `xyz`, quaternion fixed 4-series `W/X/Y/Z` (purple W) → Task 3 Step 1; shared timeline/zoom/playhead across all → Task 3 (drawGraph shares `viewStart/viewEnd`; interactions bound to every `g.cnv`); blank on absent stream → `drawGraph` `!tArr.length` guard; `parse_accel` regression → Task 1 wrapper + unchanged tests.

**Placeholder scan:** none — full code for every step.

**Type/name consistency:** `Series.comps`/`parse_stream` defined in Task 1, consumed by `server.py` (Step 4) and tests (Step 1); `parse_accel`/`AccelSeries` preserved. Frontend: `GRAPHS`/`graphSeries`/`COL`/`vecModes`/`quat` defined Task 3 Step 1; `draw` (Step 2), interactions (Step 3), `renderLegend`/toggle loop (Step 4) all consume `GRAPHS` and `g.cnv`/`g.cx`/`g.legendEl`/`g.tKey`/`g.unit`/`g.toggleSel`; DOM ids `#scrub3..5`/`#legend3..5`/`.rbtn` created in Task 2. Removed names `SERIES`/`GYRO_SERIES`/`gmode`/`gcanvas`/`gctx` have no remaining references (Step 5 grep).
