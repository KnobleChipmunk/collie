# Design: redraw on resize

## Module contract (tests import these names)

### `collie.resident` (new)

- `SETTLE_S = 0.15`: quiet time after the last `SIGWINCH` before a redraw.
- `REDRAW_CLEAR = "\x1b[H\x1b[2J"`: home and clear the visible screen for a resize redraw. It never
  scrolls (that would push another copy of the same excerpt into scrollback) and never clears
  scrollback (`\x1b[3J`).
- `resident_enabled() -> bool`: true when `sys.stdin.isatty()` and `sys.stdout.isatty()` and
  `COLLIE_RESIDENT` is not `off`.
- `resident_terminal()`: a context manager entered BEFORE the first draw (plan review round 1,
  F1: a resize that arrives while bat or delta is still running the first draw must not be lost,
  and `SIGWINCH` is ignored by default until a handler exists). On enter it puts stdin in cbreak mode
  (no echo, no line buffering) and installs handlers for `SIGWINCH` (record the time of the latest
  resize), `SIGTERM`, `SIGHUP`, `SIGINT` (request stop). It yields a state object. On exit, including
  on an exception, it restores the saved terminal attributes and the previous signal handlers.
- `stay_resident(state, draw: Callable[[], int]) -> int`: called after the first draw, inside
  `resident_terminal()`. Returns 0 at once if a stop was requested during the first draw. Otherwise
  loops on `select` over stdin with a short timeout:
  - Once `SETTLE_S` has passed since the latest resize (including one that arrived during the first
    draw), write `REDRAW_CLEAR`, flush, and call `draw()`. A burst of resizes gives one redraw.
  - Any byte on stdin: consume it and return 0.
  - A stop request: return 0.

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
  runs bat (or git piped into delta), exactly as today. If `resident_enabled()`: enter
  `resident_terminal()`, write `redraw_prefix(rows)`, call `draw()`, and return
  `stay_resident(state, draw)` from inside the context. Otherwise write the prefix, call `draw()`
  once, and return its status.
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
6. **Lead ruling (final pass): an empty foreground list after a stop means "changing over".** Real
   herdr 0.8.0 briefly reports no foreground process between the renderer's exit and the shell's
   prompt; the real herdr check failed 3 of 3 runs on it. After collie stops its own renderer it keeps
   waiting through an empty list, up to the grace period. The first check is unchanged, so the user's
   own program still exits 4 at once.
