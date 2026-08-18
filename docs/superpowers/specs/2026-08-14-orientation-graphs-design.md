# Gravity and orientation graphs — design

Date: 2026-08-14
Status: approved for planning (autonomous tool-update flow)

## Purpose

Add three more GPMF streams to the player: the gravity vector (`GRAV`)
and the two orientation quaternions (`CORI` camera, `IORI` image), each as
its own graph beneath the accelerometer and gyroscope, sharing the same
timeline.

## Scope

- Backend: decode `GRAV` (3-vector), `CORI` and `IORI` (4-component
  quaternions) and return them from `/api/accel`.
- Frontend: three more canvas graphs, and a refactor of the two current
  hard-coded graphs (accel, gyro) into one data-driven list so all five
  render, toggle, and legend through the same loop.

## Backend — generalise to N components

`GRAV` has 3 components; `CORI`/`IORI` have 4. The current `parse_stream`
assumes exactly three (`x, y, z`). Generalise it:

- `Series` carries `comps: list[list[float]]` — one list per component —
  plus `t`, `mag`, `warnings`. Component count is inferred from the data
  (`sample_size // 2` int16 lanes, or the first sample's arity).
- `parse_stream(blob, packet_times, key, video_duration=None) -> Series`
  distributes each packet's samples across its duration (unchanged timing
  logic) and appends each component to its own list. `mag` is the
  Euclidean norm across all components.
- `parse_accel` remains a wrapper mapping `comps[0..2]` to `ax/ay/az` and
  `mag` to `amag`, so its `AccelSeries` return and existing tests are
  unchanged.

`server.py` `_accel` calls `parse_stream` for `ACCL`, `GYRO`, `GRAV`,
`CORI`, `IORI` and returns flat arrays (empty when a stream is absent):

```
t, ax, ay, az, amag,
gt, gx, gy, gz, gmag,
gvt, gvx, gvy, gvz, gvmag,          # GRAV
cot, cow, cox, coy, coz,            # CORI quaternion W,X,Y,Z
iot, iow, iox, ioy, ioz,            # IORI quaternion W,X,Y,Z
warnings, fps
```

A small helper picks component `i` or `[]` when the stream has fewer.

## Frontend — data-driven graph list

Replace the accel/gyro-specific `draw`/legend/toggle code with a `GRAPHS`
list. Each entry describes one graph:

```
{ tKey, canvas, ctx, legendId, unit, label,
  modes: { mag:[...], xyz:[...] }, mode,   // vector graphs (accel, gyro, grav)
  fixed: [...] }                           // fixed-series graphs (cori, iori)
```

- Accel: `t`, `m/s²`, modes `|a|`/`X·Y·Z`, default `mag`.
- Gyro: `gt`, `rad/s`, modes `|ω|`/`X·Y·Z`, default `mag`.
- Grav: `gvt`, `g`, modes `|g|`/`X·Y·Z`, default `xyz` (the tilt is the
  useful view; the magnitude of a unit vector is ~1).
- Cori: `cot`, unit blank, fixed 4 series `W/X/Y/Z` (quaternion, no
  magnitude — a unit quaternion's norm is ~1).
- Iori: `iot`, unit blank, fixed 4 series `W/X/Y/Z`.

`draw()` loops the list calling the existing `drawGraph(cnv, cx, tArr,
seriesDef, unit)` for each, then `updatePanbar()` once. `renderLegend()`
loops filling each graph's legend. Mode toggles (accel/gyro/grav) are
wired by iterating the list; quaternion graphs have no toggle. Click-seek,
drag-zoom, and double-click reset are bound to every graph's canvas
(the shared window and `activeCanvas` logic is unchanged). The shared
timeline still keys `duration`/`minSpan`/`stepPlayhead` off `data.t`
(accel), which every graph shares.

Series colours reuse the existing palette; quaternions use a fourth colour
(purple `#7F77DD`) for the `W` component, then blue/green/coral for X/Y/Z.

## Layout

Below the gyro row, stack: grav canvas + legend + `Гравитация` toggle row;
cori canvas + legend + `Ориентация камеры` label row; iori canvas + legend
+ `Ориентация изображения` label row. All canvases share width and the
existing pan bar / zoom controls.

## Edge cases

- A stream absent in a clip → its arrays are empty → that canvas renders
  blank (the `drawGraph` `!tArr.length` guard), no crash, no warning.
- Quaternion graphs have four series; `drawGraph` already handles any
  series count and its Y-fit is sign-agnostic (quaternion components span
  −1…1).
- Different sample rates per stream (accel/gyro ~200 Hz, grav/cori/iori
  ~60 Hz) are fine: each graph indexes its own `tKey` via `lowerBound`.

## Testing

- Unit: `parse_stream` on a synthetic 4-component (quaternion-shaped)
  stream — component splitting, magnitude across 4 lanes, per-packet
  timing; plus the existing `parse_accel`/`parse_stream` tests still pass
  (the gyro `parse_stream` test is updated to read `comps`).
- Manual acceptance on a real clip: grav/cori/iori graphs appear and
  render; zoom/pan/seek on any graph moves all; grav toggle works; the
  quaternion graphs show four W/X/Y/Z traces with a legend; a clip missing
  a stream shows that graph blank without error.

## Dependencies

None new. Vanilla JS/Canvas frontend, stdlib backend.
