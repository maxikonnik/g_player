const video = document.getElementById("video");
const canvas = document.getElementById("scrub");
const ctx = canvas.getContext("2d");
const tlabel = document.getElementById("tlabel");
const warnings = document.getElementById("warnings");
const videomsg = document.getElementById("videomsg");

let data = null;      // {t, ax, ay, az, amag, warnings, fps}
let mode = "mag";
let curPath = null;
let viewStart = 0, viewEnd = 1;   // visible time window (seconds)
let userZoomed = false;
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

function fmtMs(s) {
  s = Math.max(0, s || 0);
  const m = Math.floor(s / 60), r = Math.floor(s % 60), ms = Math.floor((s % 1) * 1000);
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
}

function duration() {
  if (video.duration && isFinite(video.duration)) return video.duration;
  return data && data.t.length ? data.t[data.t.length - 1] : 1;
}

function minSpan() {
  if (!data || data.t.length < 2) return 0.02;
  const si = (data.t[data.t.length - 1] - data.t[0]) / (data.t.length - 1);
  return Math.max(si * 8, 0.02);
}
function resetView() { viewStart = 0; viewEnd = duration(); userZoomed = false; }
function clampView(s, e) {
  const D = duration();
  const span = Math.max(minSpan(), Math.min(e - s, D));
  if (s < 0) s = 0;
  if (s + span > D) s = D - span;
  if (s < 0) s = 0;
  return [s, Math.min(D, s + span)];
}
function lowerBound(arr, x) {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] < x) lo = m + 1; else hi = m; }
  return lo;
}
function niceTicks(lo, hi, target = 4) {
  if (!isFinite(lo) || !isFinite(hi) || hi <= lo) return [];
  const raw = (hi - lo) / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const ticks = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
    ticks.push(+v.toFixed(6));
  }
  return ticks;
}
const panbar = document.getElementById("panbar");
const panthumb = document.getElementById("panthumb");
function updatePanbar() {
  const D = duration();
  panthumb.style.left = (viewStart / D * 100) + "%";
  panthumb.style.width = Math.max(2, (viewEnd - viewStart) / D * 100) + "%";
}

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

function followPlayhead() {
  if (video.paused || panning || !data || !data.t.length) return;
  const t = video.currentTime;
  if (t < viewStart || t > viewEnd) {
    const span = viewEnd - viewStart;
    [viewStart, viewEnd] = clampView(t - span * 0.1, t - span * 0.1 + span);
  }
}
function loop() {
  followPlayhead();
  const D = duration();
  let label = `${fmtMs(video.currentTime)} / ${fmtMs(D)}`;
  const fps = data && data.fps;
  if (fps && fps > 0) {
    const total = Math.round(D * fps);
    const frame = Math.min(Math.max(0, Math.floor((video.currentTime || 0) * fps)), Math.max(0, total - 1));
    label += ` · кадр ${frame} / ${total}`;
  }
  tlabel.textContent = label;
  draw();
  requestAnimationFrame(loop);
}

const DRAG_PX = 4;
let selecting = false, dragging = false, downX = 0, downTime = 0, selStartTime = 0, selCurTime = 0;
function eventTime(e) {
  const r = e.currentTarget.getBoundingClientRect();
  const frac = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  return viewStart + frac * (viewEnd - viewStart);
}
canvas.addEventListener("mousedown", (e) => {
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
  if (!data || !data.t.length) return;
  selecting = true; dragging = false; downX = e.clientX;
  downTime = eventTime(e); selStartTime = downTime; selCurTime = downTime;
});
gcanvas.addEventListener("dblclick", () => { resetView(); });

function zoomBy(factor) {
  if (!data || !data.t.length) return;
  const oldSpan = viewEnd - viewStart;
  const c = (video.currentTime >= viewStart && video.currentTime <= viewEnd)
    ? video.currentTime : (viewStart + viewEnd) / 2;
  const frac = (c - viewStart) / oldSpan;
  const newSpan = oldSpan * factor;
  [viewStart, viewEnd] = clampView(c - frac * newSpan, c - frac * newSpan + newSpan);
  userZoomed = true;
}
document.getElementById("zoomin").addEventListener("click", () => zoomBy(1 / 1.5));
document.getElementById("zoomout").addEventListener("click", () => zoomBy(1.5));
document.getElementById("zoomreset").addEventListener("click", () => resetView());

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

function stepPlayhead(dir) {
  if (!data || !data.t.length) return;
  const w = canvas.clientWidth * 2;
  const i0 = Math.max(0, lowerBound(data.t, viewStart) - 1);
  const i1 = Math.min(data.t.length - 1, lowerBound(data.t, viewEnd));
  const visible = i1 - i0 + 1;
  const dots = visible > 0 && w / visible > 8;
  let t = video.currentTime || 0;
  if (dots) {
    let idx = lowerBound(data.t, t);
    if (idx >= data.t.length) idx = data.t.length - 1;
    if (idx > 0 && (t - data.t[idx - 1]) < (data.t[idx] - t)) idx -= 1;  // nearest sample
    idx = Math.max(0, Math.min(data.t.length - 1, idx + dir));
    t = data.t[idx];
  } else {
    t += dir * 0.01 * (viewEnd - viewStart);
  }
  t = Math.max(0, Math.min(duration(), t));
  video.currentTime = t;
  if (t < viewStart || t > viewEnd) {
    const span = viewEnd - viewStart;
    [viewStart, viewEnd] = clampView(t - span / 2, t + span / 2);
  }
}

window.addEventListener("keydown", (e) => {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  const tag = (document.activeElement && document.activeElement.tagName) || "";
  if (tag === "SELECT" || tag === "INPUT" || tag === "TEXTAREA") return;
  e.preventDefault();
  stepPlayhead(e.key === "ArrowRight" ? 1 : -1);
});

async function openFile(path) {
  curPath = path;
  videomsg.textContent = "";
  video.src = `/api/video?path=${encodeURIComponent(path)}`;
  warnings.textContent = "";
  try {
    const res = await fetch(`/api/accel?path=${encodeURIComponent(path)}`);
    const body = await res.json();
    if (body.error) { warnings.textContent = body.error; data = null; return; }
    data = body;
    resetView();
    warnings.textContent = (body.warnings || []).join(" · ");
  } catch (err) {
    warnings.textContent = String(err);
  }
}

video.addEventListener("error", async () => {
  if (!curPath || video.src.includes("proxy")) return;
  videomsg.textContent = "готовлю совместимую копию…";
  const res = await fetch(`/api/proxy?path=${encodeURIComponent(curPath)}`, { method: "POST" });
  const body = await res.json();
  if (body.error) { videomsg.textContent = body.error; return; }
  videomsg.textContent = "";
  video.src = `/api/video?path=${encodeURIComponent(body.path)}&proxy=1`;
});

video.addEventListener("loadedmetadata", () => { if (!userZoomed) resetView(); });

// --- file picker ---
const modal = document.getElementById("modal");
const fslist = document.getElementById("fslist");
const crumb = document.getElementById("crumb");
let browseCwd = null;

function makeRow(icon, label, onclick) {
  const d = document.createElement("div");
  d.className = "row";
  d.textContent = `${icon}  ${label}`;
  d.addEventListener("click", onclick);
  return d;
}

async function browse(path) {
  const res = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
  const body = await res.json();
  if (body.error) { crumb.textContent = body.error; return; }
  browseCwd = body.cwd;
  crumb.textContent = body.cwd;
  fslist.innerHTML = "";
  fslist.appendChild(makeRow("⬆", "..", () => browse(body.parent)));
  for (const e of body.entries) {
    if (e.is_dir) fslist.appendChild(makeRow("📁", e.name, () => browse(e.path)));
    else fslist.appendChild(makeRow("🎬", e.name, () => {
      modal.classList.add("hidden");
      addFileOption(e.path, e.name);
      openFile(e.path);
    }));
  }
}

function addFileOption(path, name) {
  const sel = document.getElementById("filesel");
  const opt = document.createElement("option");
  opt.value = path; opt.textContent = name; opt.selected = true;
  sel.insertBefore(opt, sel.firstChild);
}

async function populateList(root) {
  const res = await fetch(`/api/browse?path=${encodeURIComponent(root)}`);
  const body = await res.json();
  const sel = document.getElementById("filesel");
  sel.innerHTML = "";
  for (const e of (body.entries || []).filter((x) => !x.is_dir)) {
    const opt = document.createElement("option");
    opt.value = e.path; opt.textContent = e.name;
    sel.appendChild(opt);
  }
  if (sel.value) openFile(sel.value);
}

document.getElementById("filesel").addEventListener("change", (e) => openFile(e.target.value));
document.getElementById("browse").addEventListener("click", () => {
  modal.classList.remove("hidden"); browse(browseCwd || rootDir);
});
document.getElementById("closem").addEventListener("click", () => modal.classList.add("hidden"));
document.getElementById("usefolder").addEventListener("click", () => {
  modal.classList.add("hidden");
  if (browseCwd) { rootDir = browseCwd; populateList(rootDir); }
});

let panning = false, panDownX = 0, panStartView = 0;
panthumb.addEventListener("mousedown", (e) => {
  panning = true; panDownX = e.clientX; panStartView = viewStart; userZoomed = true;
  e.stopPropagation();
});
window.addEventListener("mousemove", (e) => {
  if (!panning) return;
  if (!(e.buttons & 1)) { panning = false; return; }
  const D = duration(), span = viewEnd - viewStart;
  const dxFrac = (e.clientX - panDownX) / panbar.getBoundingClientRect().width;
  const s = panStartView + dxFrac * D;
  [viewStart, viewEnd] = clampView(s, s + span);
});
window.addEventListener("mouseup", () => { panning = false; });

let rootDir = "";
(async function init() {
  const res = await fetch("/api/roots");
  const body = await res.json();
  rootDir = body.roots[0];
  await populateList(rootDir);
  requestAnimationFrame(loop);
})();
