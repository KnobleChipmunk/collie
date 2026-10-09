# Design: collie

## Layout

```
collie/
  pyproject.toml            # hatchling; script entry collie = collie.cli:main
  src/collie/
    __main__.py             # python -m collie
    cli.py                  # argparse, exit codes, orchestration
    ranges.py               # parse_range, Excerpt, parse_excerpt, find_match
    render.py               # bat_argv, diff_argvs, note_line, clear sequence, theme
    panes.py                # Herdr client, label_for, find_code_pane, choose_direction, is_idle_shell
    setup.py                # skill link, AGENTS.md block, settings.json hook
    rule.md                 # the agent rule text (package data)
    skill/SKILL.md          # the skill agents load (package data)
  tests/                    # the acceptance contract; fakes/herdr is a scripted fake
  openspec/
```

Python 3.11+ (tests use `tomllib`), standard library only at runtime. Dev: pytest, ruff.

## Module contract (tests import these names)

### `collie.ranges`

- `parse_range(text: str) -> tuple[int, int]`. `"36-64"` gives `(36, 64)`; `"41"` gives `(41, 41)`.
  Raises `ValueError` for empty text, anything but ASCII digits and one dash, zero, or start greater
  than end. A dash matches the `file:36-64` citations agents already write.
- `@dataclass(frozen=True) Excerpt(path: Path, lines: tuple[int, int] | None, highlights: tuple[tuple[int, int], ...])`
  with `spec() -> str` (`<path>[:N-M][@H-H,...]`, highlights always written as ranges) and
  `subject() -> str` (`<file name>[:N-M]`).
- `parse_excerpt(text: str) -> Excerpt` reads `PATH[:N-M][@H[-H][,H[-H]...]]`. It splits `@` off the
  right first, then a `:` suffix only when it parses as a range, so paths containing colons work.
  Raises `ValueError` for an empty path, a bad range, an empty or bad highlight list, or a
  highlight outside the excerpt's lines. `@` was chosen over `#` because zsh with `extendedglob`
  treats `#` as a glob operator.
- `find_match(lines: list[str], text: str) -> tuple[int, int] | None`: 1 based number of the first
  line containing `text` (literal substring, not a regex) and how many lines contain it.

### `collie.render`

- `DEFAULT_THEME = "Catppuccin Mocha"`; `theme() -> str` returns `COLLIE_THEME` if set and
  nonempty, else `DEFAULT_THEME`.
- `NOTE_RGB = (203, 166, 247)` (Mocha mauve, `#cba6f7`).
- `note_line(text: str) -> str` returns `"\x1b[1;38;2;203;166;247m▶ " + text + "\x1b[0m"`.
- `header_text(subject: str, note: str | None) -> str`: `subject` alone, or `subject + " · " + note`.
  `subject` is `<file name>:<N>-<M>` (or the bare file name for a whole file) for show, and
  `diff <rev> -- <paths>` or `diff working tree` for diff. The pane always gets a header, note or not.
- `EXCERPT_ROWS = 6`: rows each additional excerpt adds (header, blank, 4 frame rows).
- `CHROME_ROWS = 8`: rows around the content that are not code (header line and blank, 4 bat or
  delta frame rows, 2 prompt rows after the render).
- `overflow(content_lines: int, pane_height: int, excerpts: int = 1) -> int`: rows that will scroll
  out of view, `max(0, content_lines + CHROME_ROWS + EXCERPT_ROWS * (excerpts - 1) - pane_height)`. Wrapped long lines are not counted; the
  report is a floor, not exact.
- `redraw_prefix(rows: int) -> str` returns `"\x1b[<rows>S\x1b[H"`: scroll the whole screen up by its
  height, which pushes the previous render (and the echoed command) into herdr's scrollback (fact
  20), then move home. Nothing ever clears scrollback, so earlier excerpts stay one scroll away.
  `rows` comes from `shutil.get_terminal_size()` inside the pane.
- `bat_argv(path: Path, line_range: tuple[int, int] | None, highlights: list[tuple[int, int]], theme: str) -> list[str]`
  returns, in this order: `bat`, `--paging=never`, `--color=always`, `--theme=<theme>`,
  `--style=numbers,grid,header`, then `--line-range=N:M` if given, then one `--highlight-line=N:M`
  per highlight, then `str(path)` last.
- `diff_argvs(repo: Path, rev: str | None, paths: list[str], theme: str) -> tuple[list[str], list[str]]`
  returns `(git_argv, delta_argv)`:
  - git: `git -C <repo> -c core.pager=cat diff [rev] -- [paths...]` (`--` always present)
  - delta: `delta --no-gitconfig --paging=never --line-numbers --syntax-theme=<theme>`.
    Never contains `-s` or `--side-by-side`.

### `collie.panes`

- `LABEL_PREFIX = "collie:"`; `label_for(caller: str) -> str` gives `"collie:" + caller`.
- `find_code_pane(panes: list[dict], caller: str, tab_id: str) -> str | None`: the `pane_id` of the
  first pane whose `label` equals `label_for(caller)` and whose `tab_id` equals `tab_id`.
- `RIGHT_MIN_WIDTH = 160`; `choose_direction(width: int) -> str`: `"right"` when width is at least
  160, else `"down"`. Rationale: splitting right halves the width, and the code needs about 80
  columns to render without wrapping.
- `SHELLS = {"zsh", "bash", "fish", "sh", "nu", "dash"}`;
  `is_idle_shell(process_info: dict) -> bool`: true when `foreground_processes` is nonempty and
  every entry's `name` is in `SHELLS`.
- `RENDER_PROCS = {"bat", "delta", "git"}`; `is_own_render(process_info: dict) -> bool`: true when
  every foreground entry's `name` is in `RENDER_PROCS` or its `cmdline` contains `-m collie render`.
- `BUSY_GRACE_MS`: `COLLIE_BUSY_GRACE_MS` if set, else 2000. Polling interval 200 ms.
- `class Herdr`: thin wrapper that runs the `herdr` found on PATH, parses JSON stdout, and raises
  `HerdrError(code, message)` on exit status 1. Methods: `get`, `list_panes`, `layout`,
  `process_info`, `split`, `rename`, `run`, `close`.

### `collie.setup`

All paths derive from `Path.home()`, so tests point `HOME` at a temp dir.

- `BLOCK_BEGIN = "<!-- collie:begin -->"`, `BLOCK_END = "<!-- collie:end -->"`.
- `upsert_block(text: str, body: str) -> str`: replaces the marked block if present, else appends
  it after one blank line. Applying it twice gives the same text as applying it once.
- `HOOK_COMMAND = "collie rule"`. `ensure_hook(settings: dict) -> tuple[dict, bool]` adds
  `{"type": "command", "command": "collie rule"}` in a new `SessionStart` entry with matcher `""`
  unless any SessionStart hook already has that command; returns `(settings, changed)`.
- `run_setup(dry_run: bool) -> list[str]`: returns one line per action (`link`, `block`, `hook`).
  Each line is prefixed `would ` in dry run, and ends in `unchanged` when the action found nothing to
  do. Dry run writes nothing, not even parent directories. A real run creates missing parents and
  writes `settings.json.bak.<YYYYmmdd-HHMMSS>` before changing `settings.json`. No backup is written
  when nothing changes, so an unchanged rerun never adds a file.

## Flow of `show` and `diff`

1. **Preflight, before any Herdr call.** Exit 2 on any failure, naming what failed:
   1 to 5 excerpts, each parsing and naming an existing file; `--match` only with exactly one
   excerpt that has no range, and the text found in the file (otherwise exit 2 quoting the text); `bat` on PATH (show); `delta` and `git` on PATH (diff); `--repo PATH`
   (default current directory) is a git work tree; `git rev-parse --verify <rev>^{commit}` succeeds
   when a rev is given. The render command always gets resolved absolute paths.
2. If `COLLIE=off`: print `collie: disabled (COLLIE=off)` and exit 0. Nothing else runs.
3. If `HERDR_ENV` is not `1` or `HERDR_PANE_ID` is unset: print a message to stderr, exit 3.
4. `herdr pane get $HERDR_PANE_ID` for the caller's `tab_id` and `cwd`.
5. `herdr pane list --workspace $HERDR_WORKSPACE_ID`; `find_code_pane`.
6. **Found:** `process-info`.
   - Idle shell: continue.
   - `is_own_render`: poll every 200 ms up to `BUSY_GRACE_MS` until idle. Still not idle: exit 4.
   - Anything else (the user's program): exit 4 at once, no polling. Never send keys to it.
7. **Not found:** `layout` for the caller width, `choose_direction`,
   `split --pane <caller> --direction <d> --cwd <caller cwd> --no-focus`, then
   `rename <new> collie:<caller>`. If rename fails: `close <new>`, then exit 5. Then poll
   `process-info` on the new pane every 200 ms up to `BUSY_GRACE_MS` until it is an idle shell;
   if it never is, close it and exit 4 with "new code pane <id> did not reach a prompt".
8. `herdr pane run <code pane> "<cmd>"` where `<cmd>` is
   `shlex.join([sys.executable, "-m", "collie", "render", ...])`.
9. `layout` again for the code pane's `rect.height`; count content lines (sum of range lengths, or
   file length for a whole file; output line count of the same `git diff` for diff).
10. Print one line and exit 0:
    `shown in <pane>: <subject>` and, when `overflow(...) > 0`,
    ` (pane fits ~<visible> of <total> lines; the first <n> scrolled out of view)`.
    With `--match` it also prints `matched <k> times; showing the first, at line <m>` when k > 1.

`--match TEXT [--context N]` (default 30) turns the one excerpt into lines
`max(1, m - 3)` to `min(file length, m + N - 1)` with line `m` highlighted, where `m` is the first
match. The render command receives that resolved range, never the text.

Any `HerdrError` exits 5 with the Herdr error code in the message. Focus never moves.

## `close`

Closes the pane labeled for the caller in the caller's tab, but only when it is an idle shell; a busy
pane gives exit 4 and stays open. No pane is exit 0. Closing is optional; agents are never required
to call it.

## `render` (runs inside the code pane)

Writes `redraw_prefix(rows)`, then for each excerpt in order: `note_line(header_text(subject, note))`
(the note only on the first excerpt), a blank line, and bat for that excerpt. For diff: the header,
a blank line, then `git ... | delta ...`. stdout is inherited. Empty diff prints `no changes` instead of
running delta.

## Real herdr check

`tests/test_real_herdr.py` runs only with `HERDR_ENV=1` and `COLLIE_REAL_HERDR=1`. It creates an
unfocused scratch tab, shows two excerpts, and asserts against the real herdr and bat: one code pane
labeled `collie:<root>`, the second excerpt visible, the first still in scrollback, and `close`
leaving only the root pane. The tab is closed in a `finally`. It replaces the manual Herdr gate.

## Rule text (draft, ships as `rule.md`)

```
HERDR CODE PANES (HERDR_ENV=1): when you explain what code does, or cite file:line to the user,
show it first: `collie show <file>:N-M[@H-H] [<file>:N-M ...] [--note "<one line>"]` (up to 5
excerpts in one call when the explanation spans files). If you edited the file this session, find
lines by text instead: `collie show <file> --match "<text>" [--context N]`.
For what changed: `collie diff [<rev>] [--path <p>] [--note "..."]`. Then explain only what
the pane does not show, citing file:line. The pane is reused; never open your own. Skip this in
delegated sessions (builder, reviewer) and when COLLIE=off. If collie reports lines scrolled out
of view, show a smaller range instead of claiming the user saw them. Exit 4 means the user is
using the pane: say so and continue without it. Closing the pane (`collie close`) is optional.
```

## Decisions

1. **Label, not a state file.** Herdr already stores and returns pane labels, so a closed pane
   disappears from `pane list` by itself. A state file would go stale when the user closes the pane.
2. **Exit 4 on a busy pane instead of interrupting.** The user may be typing in that pane.
3. **`sys.executable -m collie render`** instead of `collie render`, so the code pane runs the
   same install even when PATH differs between panes.
4. **Rule via SessionStart hook plus AGENTS.md block.** Fact 15: AGENTS.md alone is not loaded into
   Claude's context. The hook covers Claude; the block covers Codex and others that read AGENTS.md.
5. **`COLLIE=off` is enforced by the tool, not only by the rule.** A weak model in a builder
   pane may ignore the rule; it cannot ignore the exit.
6. **Excerpt syntax instead of `--lines`/`--highlight` flags.** One syntax serves one excerpt or five,
   and it matches how agents already cite code. `--match` stays a flag because it needs a text value.
7. **`\x1b[<rows>S` instead of clearing.** It gives the clean screen of a clear while keeping history.
8. **Report overflow, do not refuse it.** A tall excerpt is still useful if the agent knows the top
   scrolled away; refusing would force chunking even when the user is about to scroll anyway.
9. **Two kinds of busy.** collie's own render finishing is a wait; the user's program is a stop.
10. **Rejected (Hermes review, idea 5): wrap markers for bat.** bat already leaves the line number
   column blank on wrapped rows (fact 19), so wrapped lines are distinguishable.
11. **Rejected: side by side diffs** (fact 13), **neovim** (interactive, needs teardown), **one new
   pane per call** (clutters the tab).
