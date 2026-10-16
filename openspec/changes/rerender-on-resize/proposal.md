# Redraw the code pane when it is resized (issue #2)

## Why

collie renders once, at the code pane's width at that moment, and the render process exits. When
the pane is resized or moved afterwards, the terminal re-folds the old output and wrapped lines
spill across bat's line number gutter. The user has to ask for the same excerpt again.

## Grounded facts

Read or run on 2026-10-16 on the Mac, against `main` at 697c10b.

1. Issue #2 (KnobleChipmunk/collie): a render at 150 columns stayed garbled after the pane was widened to 209, until `collie show` was run again by hand; after that, bat's own wrapping was clean.
2. `src/collie/cli.py:313-344`: `cmd_render_show` and `cmd_render_diff` write the redraw prefix, run bat (or git piped into delta) once, and return. Nothing handles a resize.
3. `src/collie/cli.py:244`: an existing code pane is reused only after `await_idle(..., is_own_render)` sees an idle shell; `src/collie/cli.py:289-291`: `cmd_close` exits 4 unless the pane is an idle shell. A renderer that stays in the foreground would make both fail today.
4. Setting a pseudo terminal's size with `TIOCSWINSZ` on the master side delivers `SIGWINCH` to the program in it, and `shutil.get_terminal_size()` then returns the new width (probe `/tmp/collie-probe/winch.py`: printed `WINCH 133` after a resize to 133 columns).
5. `herdr pane process-info` returns, per foreground process, `argv`, `argv0`, `cmdline`, `cwd`, `name`, `pid` (observed on the lead pane).
6. `ps -o command= -p <pid>` prints that process's full command line (observed: `sleep 30`). The same flags work with Linux procps, where `command` is an alias of `args`.
7. `herdr pane resize --direction left|right|up|down [--amount FLOAT] [--pane ID]` exists (`herdr pane resize --help`); the unit of `--amount` is not documented.
8. herdr's socket API lists `events.subscribe` and a `layout.updated` event (`herdr api schema --json`); whether that event carries pane sizes is not verified. Not used by this change.
9. Plan review round 1 (scratch tab): `herdr pane resize --amount 0.1` moved the split by 30 of the tab's 300 columns, so the unit is a fraction of the split; the pane's terminal is `rect.width - 3` columns and `rect.height - 2` rows (observed 147x67 inside a 150x69 rect); `tcgetattr` on the pty master after the child exits reads the slave's final ECHO and ICANON state.

## What Changes

1. The render command stays running after its first draw when both stdin and stdout are terminals. On `SIGWINCH` it waits until resizes stop for 150 ms, then clears the screen and draws the same excerpts or diff again at the new width. Any key pressed in the code pane, `SIGTERM`, `SIGHUP`, or `SIGINT` ends it cleanly and hands the pane back to the shell. `COLLIE_RESIDENT=off` restores the old run once behavior.
2. `collie show`, `collie diff`, and `collie close` stop collie's own resident renderer before they reuse or close the pane. They find it by `cmdline` in `herdr pane process-info`, confirm the live command line with `ps` before signalling, and send it `SIGTERM`. They still never type into the pane, and still exit 4 at once when the user's own program is in the foreground.

## Non-goals

1. Using herdr's event stream (`layout.updated`) instead of `SIGWINCH`.
2. Sending new excerpts to the resident renderer instead of typing a command into the shell. That would also fix the shell history follow up, but it is a separate change.
3. Counting wrapped rows in the overflow estimate (issue #2, "Related").
4. Remote herdr sessions (`herdr --remote`), where a pid from herdr is not a local process.

## Impact

`src/collie/cli.py` (render loop wiring, deliver, close), `src/collie/panes.py` (finding and stopping the renderer), a new `src/collie/resident.py` (the loop), README and `skill/SKILL.md` (one line each). Tests: new `tests/test_resident.py` (pty based), additions to `tests/test_units.py` and `tests/test_cli.py`, fakes for bat and delta print the terminal width when attached to a terminal, `tests/conftest.py` adds a timeout so a renderer that wrongly stays resident fails instead of hanging, and `tests/test_real_herdr.py` covers resize, reuse, and close with a resident renderer.
