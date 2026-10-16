# Design: redraw on resize

## Module contract (tests import these names)

### `collie.resident` (new)

- `SETTLE_S = 0.15`: quiet time after the last `SIGWINCH` before a redraw.
- `REDRAW_CLEAR = "\x1b[H\x1b[2J"`: home and clear the visible screen for a resize redraw. It never
  scrolls (that would push another copy of the same excerpt into scrollback) and never clears
  scrollback (`\x1b[3J`).
- `resident_enabled() -> bool`: true when `sys.stdin.isatty()` and `sys.stdout.isatty()` and
  `COLLIE_RESIDENT` is not `off`.
- `stay_resident(draw: Callable[[], int]) -> int`: called after the first draw. Puts stdin in
  cbreak mode (no echo, no line buffering), installs handlers, and loops on `select` over stdin
  with a short timeout:
  - `SIGWINCH` records the time of the latest resize. Once `SETTLE_S` has passed since it, write
    `REDRAW_CLEAR`, flush, and call `draw()`. A burst of resizes gives one redraw.
  - Any byte on stdin: consume it and return 0.
  - `SIGTERM`, `SIGHUP`, `SIGINT`: return 0.
  - Always restores the saved terminal attributes and the previous signal handlers before
    returning, including on an exception.

### `collie.panes` (additions)

- `RENDER_MARK = "-m collie render"`.
- `renderer_pids(process_info: dict) -> list[int]`: the `pid` of every foreground entry whose
  `cmdline` contains `RENDER_MARK` and whose `pid` is an int.
- `is_collie_renderer(pid: int) -> bool`: runs `ps -o command= -p <pid>`; true only when it exits 0
  and its output contains `RENDER_MARK`. Any failure is false.
- `stop_renderers(process_info: dict) -> int`: sends `SIGTERM` to each pid from `renderer_pids` that
  passes `is_collie_renderer`; ignores `ProcessLookupError`; returns how many it signalled.

### `collie.cli` (changes)

- `cmd_render_show` and `cmd_render_diff` each build a `draw()` closure that writes the headers and
  runs bat (or git piped into delta), exactly as today. They write `redraw_prefix(rows)` once, call
  `draw()`, then, if `resident_enabled()`, return `stay_resident(draw)`; otherwise return the first
  draw's status.
- `deliver`, existing pane: read `process_info` once.
  - Idle shell: run.
  - `is_own_render` false (the user's program): exit 4 at once, as today.
  - `is_own_render` true: `stop_renderers(info)`, then `await_idle(..., is_own_render)` as today;
    still not idle after `BUSY_GRACE_MS`: exit 4.
- `cmd_close`: the same three cases; the third stops the renderer, waits for the shell, then closes.
  Still not idle: exit 4, pane left open.

## Decisions

1. **`SIGWINCH` in the pane over herdr's event stream.** The terminal already tells the process in
   the pane when its size changes, with no daemon to start or clean up, and no extra typed command
   per redraw. herdr's `layout.updated` (fact 8) is unverified and would need a background process.
2. **Stop the renderer by pid, not by keys.** collie's rule is never to type into a busy pane. A
   pid confirmed with `ps` (fact 6) targets only collie's own process. herdr's `cmdline` alone could
   be stale by the time the signal is sent; `ps` reads the live process.
3. **Any key exits.** The user may want the shell in the code pane. One key gives it back, with no
   key to learn.
4. **Resident only on a terminal.** Tests and any piped use keep the run once behavior, so a
   captured `render` can never hang. `COLLIE_RESIDENT=off` is the manual escape hatch.
5. **Clear, not scroll, on a resize redraw.** Scrolling would add a full copy of the excerpt to
   scrollback on every resize; earlier excerpts from earlier calls stay in scrollback either way.
