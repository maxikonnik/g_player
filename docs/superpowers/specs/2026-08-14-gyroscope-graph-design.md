# Gyroscope graph — design

Date: 2026-08-14
Status: approved for planning (autonomous tool-update flow)

## Purpose

Add a second graph below the accelerometer scrubber showing the
gyroscope (`GYRO`) readings, so the operator can inspect rotation rate
alongside acceleration on the same timeline.

## Scope

- Backend: decode `GYRO` from GPMF (analogous to `ACCL`) and return it
  from `/api/accel`.
- Frontend: a second canvas graph beneath the accelerometer one, sharing
  the timeline / zoom / playhead, with its own Y-scale (rad/s), gridlines,
  legend, and `|ω|` / `X·Y·Z` mode toggle.

## Data model

GoPro stores `GYRO` in its own `STRM` container inside the same `DEVC`
packets as `ACCL`, with its own `SCAL` divisor, sampled at ~200 Hz in
rad/s. Its per-packet timing is the same packet timing already used for
`ACCL`, but its sample count per packet may differ, so it carries its own
time axis.

### Backend

`accel.py` generalises the per-stream decode:

- `parse_stream(blob, packet_times, key, video_duration) -> Series` where
  `key` is `"ACCL"` or `"GYRO"` and `Series` has `t, x, y, z, mag,
  warnings`. It reuses the existing DEVC/STRM walk and SCAL handling,
  selecting the `STRM` that contains `key`.
- `parse_accel(...)` stays as a thin wrapper (`key="ACCL"`) so existing
  callers and tests are unchanged.

`server.py` `_accel` calls `parse_stream` for both streams and returns:

```
{ t, ax, ay, az, amag,
  gt, gx, gy, gz, gmag,
  warnings, fps }
```

`gt/gx/gy/gz/gmag` are the gyro time axis and axes. When a clip has no
`GYRO` stream those arrays are empty and the gyro graph simply shows
nothing.

## Frontend

### Shared vs per-graph

- **Shared**: the view window (`viewStart`/`viewEnd`), the playhead
  (`video.currentTime`), the pan bar, click-seek, drag-zoom, double-click
  reset, and arrow-key stepping. A click or drag on *either* canvas
  controls the single shared timeline.
- **Per-graph**: the data arrays, the mode (`|a|`/XYZ for accel, `|ω|`/XYZ
  for gyro), the auto-fitted Y range with its `m/s²` or `rad/s` gridline
  labels, the legend, and the mode toggle.

### Refactor

The current `draw()` becomes a reusable `drawGraph(cnv, cx, tArr, series,
unit)` that renders one canvas for the current view window (min/max
envelope or per-sample dots, Y-fit gridlines with `unit`, playhead, drag
selection). A top-level `draw()` calls it for the accelerometer canvas
(`data.t`, accel series, `m/s²`) and the gyro canvas (`data.gt`, gyro
series, `rad/s`). `updatePanbar()` is called once (shared).

Series config is data-driven, one entry list per mode:

```
ACCEL_SERIES.mag = [{key:"amag", color:"#26215c", label:"|a|", width:2.4}]
ACCEL_SERIES.xyz = [ax #378ADD X, ay #1D9E75 Y, az #D85A30 Z]
GYRO_SERIES.mag  = [{key:"gmag", color:"#26215c", label:"|ω|", width:2.4}]
GYRO_SERIES.xyz  = [gx #378ADD X, gy #1D9E75 Y, gz #D85A30 Z]
```

### Layout

Beneath the accelerometer canvas + pan bar + accel controls, add a second
canvas, its legend, and a small gyro controls row with the `|ω|` /
`X·Y·Z` toggle. Both canvases are the same width and height.

## Edge cases

- No `GYRO` in the clip → `gt` empty → the gyro canvas renders blank (no
  crash); its legend still shows the current gyro mode's colours.
- Gyro and accel sample counts differ → each graph uses its own time axis
  and index window (`lowerBound` over its own `tArr`).
- The shared playhead line is drawn on both graphs at the same time.

## Testing

- Unit: `parse_stream` on synthetic GPMF bytes containing a `GYRO` STRM —
  SCAL division, `|ω|` magnitude, per-packet timing — plus a check
  that `parse_accel` still behaves (regression).
- Manual acceptance on a real clip: the gyro graph appears below, shows
  rad/s gridlines and a legend; zooming/panning/seeking on either graph
  moves both; the playhead tracks on both; `|ω|` ↔ X·Y·Z toggles the
  gyro trace independently of the accel toggle.

## Dependencies

None new. Vanilla JS/Canvas frontend, stdlib backend.
