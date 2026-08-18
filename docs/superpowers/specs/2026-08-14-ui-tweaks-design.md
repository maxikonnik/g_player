# UI tweaks — design

Date: 2026-08-14
Status: approved for planning (autonomous tool-update flow)

## Purpose

Four small player refinements:

1. Remove the image-orientation (`IORI`) quaternion graph.
2. Keep the video fixed on screen; only the graphs area scrolls.
3. Populate the file dropdown with all `.MP4` files from the opened
   file's directory (not just the one picked via Обзор).
4. Add a "copy path" button for the current file's full path.

## Scope

- Backend: stop returning `IORI` from `/api/accel`.
- Frontend: `index.html`, `style.css`, `app.js`.

## 1. Remove IORI

- `server.py`: drop the `IORI` `parse_stream` call and the
  `iot/iow/iox/ioy/ioz` response keys (and its warnings).
- `index.html`: remove the `#scrub5`/`#legend5` canvas and its label row.
- `app.js`: remove the `IORI` entry (canvas `scrub5`) from the `GRAPHS`
  list. `CORI` (camera orientation) stays.

## 2. Fixed video, scrollable graphs

Restructure into an app-shell: the file bar and the video are a fixed
header; everything below (the shared pan bar, zoom/time controls, and all
graph canvases with their legends and toggles) lives in one scroll
container that takes the remaining height.

- `index.html`: wrap the region from the first `<canvas id="scrub">`
  through the last graph's controls row in `<div id="graphs"> … </div>`.
  The `.bar`, `#stage`, and `#modal` stay outside it.
- `style.css`: make `body` a full-height flex column; `.bar` and `#stage`
  keep their natural height; `#graphs` flex-grows and scrolls
  (`overflow-y: auto; min-height: 0`). The page itself does not scroll, so
  the video stays put while the graphs scroll.

## 3. Dropdown lists the directory

When a file is opened through the Обзор browser, fill the dropdown with
every `.MP4` in that file's folder and select the opened one, so the
dropdown reflects the whole directory rather than a single entry.

- `app.js`: `populateList(root, selectPath)` gains an optional
  `selectPath`; when given, it selects and opens that file after filling
  the list. The Обзор file-click sets the active root to the browsed
  folder and calls `populateList(folder, filePath)`. The now-unused
  `addFileOption` helper is removed.

## 4. Copy-path button

- `index.html`: a `#copypath` button in the file bar.
- `app.js`: on click, copy `curPath` to the clipboard via
  `navigator.clipboard.writeText` (localhost is a secure context) and
  briefly show "Скопировано" on the button. No-op when no file is open.

## Edge cases

- No file open → copy button does nothing.
- Clipboard write rejected (rare) → swallow the error; the button still
  shows its transient label.
- A folder with no `.MP4` files → empty dropdown (unchanged behaviour).
- The scroll container coexists with the fixed-position `#modal`
  (browse dialog), which is outside the flex flow.

## Testing

No JS test harness (manual acceptance):

- Manual: only four graphs remain (accel, gyro, gravity, camera
  orientation); scrolling moves the graphs while the video stays fixed;
  opening a file via Обзор fills the dropdown with the folder's files and
  the dropdown switches between them; the copy button copies the current
  path and shows "Скопировано". Backend: `/api/accel` no longer contains
  `iot/iow/...` keys.

## Dependencies

None new.
