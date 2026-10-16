# Tasks: rerender-on-resize (issue #2)

## 0. Gates

Measured at `main` 697c10b plus the uncommitted spec and tests on branch `rerender-on-resize`:
`uv run pytest -q` gives `18 failed, 107 passed, 2 skipped in 33.04s`. The 18 are the new contract; 107 is the 105 existing tests plus `test_resident_off_draws_once` and `test_stale_renderer_pid_is_not_signalled`, which guard behavior that must not change; the 2 skips are the real herdr tests. The pty tests make the suite about 30 s.

- `uv run pytest -q`: all pass, exactly 2 skipped (`tests/test_real_herdr.py`), none edited except by a recorded lead ruling.
- `uv run ruff check .` and `uv run ruff format --check .` clean.
- `.venv/bin/python -m py_compile` passes on every `.py` file under `src/`.
- Inside Herdr: `COLLIE_REAL_HERDR=1 uv run pytest -q tests/test_real_herdr.py` gives 2 passed.

## Requirement table

| Requirement (spec.md) | Implementing step | Acceptance evidence |
|---|---|---|
| The code pane redraws after a resize | 1, 3 | `test_resident_constants`, `test_resize_redraws_at_new_width`, `test_burst_of_resizes_redraws_once`, `test_diff_redraws_on_resize`, `test_resident_renderer_redraws_on_resize` (real herdr) |
| The resident renderer gives the pane back cleanly | 1 | `test_any_key_exits_zero`, `test_signals_exit_zero[*]` (both also assert ECHO and ICANON are restored), `test_stays_resident_without_input` |
| Run once when not on a terminal | 1, 3 | `test_resident_enabled[*]`, `test_resident_off_draws_once`, every existing `test_render_*` (captured stdout; conftest's 30 s timeout fails a hang) |
| collie stops its own renderer before reusing or closing | 2, 4 | `test_renderer_pids`, `test_is_collie_renderer_reads_the_live_command`, `test_stop_renderers_signals_only_confirmed`, `test_resident_renderer_is_stopped_then_pane_reused`, `test_stale_renderer_pid_is_not_signalled`, `test_close_stops_resident_renderer`, `test_busy_code_pane_exits_4_without_input`, `test_show_reuse_scrollback_close` (real herdr) |

Callers: `resident_enabled`, `resident_terminal`, and `stay_resident` are called by `cmd_render_show` and `cmd_render_diff`; `stop_renderers` by `deliver` and `cmd_close`.

## Steps

1. `src/collie/resident.py`: `SETTLE_S`, `REDRAW_CLEAR`, `resident_enabled`, `resident_terminal`, `stay_resident` per design.md (handlers installed before the first draw).
2. `src/collie/panes.py`: `RENDER_MARK`, `renderer_pids`, `is_collie_renderer`, `stop_renderers`.
3. `src/collie/cli.py`: `draw()` closures in `cmd_render_show` and `cmd_render_diff`; stay resident when enabled.
4. `src/collie/cli.py`: `deliver` and `cmd_close` stop collie's renderer before waiting, per design.md.
5. `README.md` "Use": one line, "the code pane redraws when resized; press any key in it to get your shell back; `COLLIE_RESIDENT=off` draws once." `src/collie/skill/SKILL.md` Behavior: one line, "the code pane stays live and redraws on resize; collie stops it itself before the next render."
