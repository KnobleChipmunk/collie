## ADDED Requirements

### Requirement: Code is shown in one reusable pane per agent
`collie show` and `collie diff` SHALL render into the pane labeled `collie:<caller pane id>` in the caller's tab, creating it only when none exists.

#### Scenario: First call in a session
- **WHEN** no pane in the caller's tab carries the caller's label
- **THEN** the tool splits the caller with `--no-focus` and the caller's cwd, labels the new pane, and runs the render command in it

#### Scenario: Second call
- **WHEN** a pane with the caller's label exists in the caller's tab and runs an idle shell
- **THEN** the tool runs the render command in that pane and does not split

#### Scenario: The user closed the code pane
- **WHEN** the labeled pane no longer appears in `herdr pane list`
- **THEN** the next call creates a new one

#### Scenario: The code pane is busy
- **WHEN** the labeled pane's foreground process is not a shell
- **THEN** the tool exits 4, names the pane, and sends it no input

### Requirement: Split direction follows the caller's width
The tool SHALL split right when the caller pane is at least 160 columns wide and down otherwise.

#### Scenario: A narrow caller
- **WHEN** the caller pane is 128 columns wide
- **THEN** the split direction is `down`

### Requirement: File excerpts render with bat
The render command SHALL call bat with paging off, color on, the configured theme, numbers grid and header style, the requested line range, and every requested highlight.

#### Scenario: Excerpt with highlight and note
- **WHEN** an agent runs `collie show f.py:36-64@41-47 --note "retry loop"`
- **THEN** the old output scrolls into scrollback, the pane shows the header and note in Mocha mauve, then bat output for lines 36 to 64 with 41 to 47 highlighted

### Requirement: Diffs render unified only
Diff rendering SHALL pipe `git diff` through delta with `--no-gitconfig`, line numbers, and no side by side option, at every pane width.

#### Scenario: Gitconfig asks for side by side
- **WHEN** the machine's gitconfig sets `delta.side-by-side = true`
- **THEN** the rendered diff is still unified, because delta reads no gitconfig

### Requirement: The tool stays out of the way where it does not belong
The tool SHALL do nothing and exit 0 when `COLLIE=off`, and SHALL exit 3 without calling Herdr when not inside Herdr.

#### Scenario: Builder pane
- **WHEN** `COLLIE=off` is set
- **THEN** `show` and `diff` print the disabled message, exit 0, and never call Herdr; `rule` prints nothing

### Requirement: Arguments are validated before any pane is touched
The tool SHALL exit 2 for a missing file, an invalid range, or a diff outside a git work tree, before calling Herdr.

#### Scenario: Reversed range
- **WHEN** an agent passes `f.py:64-36`
- **THEN** the tool exits 2 and Herdr is never called

### Requirement: Setup is idempotent and previewable
`collie setup` SHALL link the skill, upsert the marked AGENTS.md block, and add the SessionStart hook once; `--dry-run` SHALL write nothing.

#### Scenario: Setup twice
- **WHEN** setup runs two times on the same home directory
- **THEN** AGENTS.md contains one block and settings.json contains one `collie rule` hook, and the second run reports no changes

#### Scenario: Backups are never overwritten
- **WHEN** setup changes settings.json
- **THEN** it first writes `settings.json.bak.<timestamp>`, and a run that changes nothing writes no backup

### Requirement: The agent learns what the pane could not show
After rendering, `show` and `diff` SHALL report in stdout how many content lines scrolled out of view when the content plus 8 rows of chrome exceeds the code pane's height.

#### Scenario: Excerpt taller than the pane
- **WHEN** an agent shows 29 lines in a code pane 28 rows tall
- **THEN** stdout says the pane fits about 20 of 29 lines and the first 9 scrolled out of view

#### Scenario: Excerpt that fits
- **WHEN** the content plus chrome fits the pane height
- **THEN** stdout carries no overflow text

### Requirement: Every render carries a header
The render command SHALL print a mauve header naming the file and range (or the diff subject) before the content, with the note appended when one is given.

#### Scenario: No note given
- **WHEN** an agent runs `collie show f.py:36-64` without `--note`
- **THEN** the pane's first line reads `▶ f.py:36-64`

### Requirement: collie's own render is not the user being busy
When the code pane's foreground is bat, delta, git, or collie's render command, the tool SHALL poll for up to 2 seconds before exiting 4; when it is any other program, the tool SHALL exit 4 at once.

#### Scenario: Two calls in quick succession
- **WHEN** the code pane is still running bat from the previous call and finishes within the grace period
- **THEN** the second call renders normally

#### Scenario: The user is in vim
- **WHEN** the code pane's foreground is vim
- **THEN** the tool exits 4 after one process check

### Requirement: Preflight catches what the pane would show as an error
Before any Herdr call, the tool SHALL exit 2 when bat (show) or delta or git (diff) is not on PATH, or a given revision does not resolve to a commit.

#### Scenario: Bad revision
- **WHEN** an agent runs `collie diff nosuchrev`
- **THEN** the tool exits 2 naming the revision and Herdr is never called

### Requirement: Creating the pane leaves nothing behind on failure
If labeling a new pane fails, the tool SHALL close it and exit 5. The tool SHALL wait for a new pane to reach an idle shell before running the render command.

#### Scenario: Rename fails
- **WHEN** `herdr pane rename` returns an error after a successful split
- **THEN** the new pane is closed and the tool exits 5

#### Scenario: Shell still starting
- **WHEN** the new pane's foreground is not yet a shell on the first check
- **THEN** the tool checks again and runs the render only once the shell is idle

### Requirement: Closing is safe and optional
`collie close` SHALL close only the caller's own idle code pane, exit 4 leaving a busy pane open, and exit 0 when there is nothing to close.

#### Scenario: Close while the user is in the pane
- **WHEN** the caller's code pane runs vim
- **THEN** close exits 4 and the pane stays

### Requirement: Earlier excerpts stay in scrollback
The render command SHALL start each render by scrolling the screen up by its height and SHALL never clear scrollback.

#### Scenario: A walkthrough of several steps
- **WHEN** an agent shows a second excerpt after a first
- **THEN** the screen shows only the second, and the first is still readable by scrolling up

### Requirement: Several excerpts render in one call
`collie show` SHALL accept one to five excerpts and render them in order in a single render, each with its own header; more than five SHALL exit 2.

#### Scenario: Explaining a flow across two files
- **WHEN** an agent runs `collie show a.py:10-20 b.py:40-45 --note "flow"`
- **THEN** one render shows `a.py:10-20 · flow` then its lines, then `b.py:40-45` then its lines

### Requirement: Lines can be found by text
`collie show PATH --match TEXT` SHALL show from 3 lines before the first line containing TEXT through `--context` lines (default 30), highlight that line, and say how many lines matched when more than one did.

#### Scenario: The agent edited the file
- **WHEN** an agent runs `collie show f.py --match "def _batch"` after its edits moved the function
- **THEN** the pane shows the function where it is now, with the `def` line highlighted

#### Scenario: Text not found
- **WHEN** the text is not in the file
- **THEN** the tool exits 2 quoting the text, and Herdr is never called

### Requirement: The fake herdr is checked against the real one
The repo SHALL include an opt-in test that runs collie against the real herdr and bat in an unfocused scratch tab and always closes that tab.

#### Scenario: Herdr changes its output
- **WHEN** a herdr upgrade changes a JSON shape collie relies on
- **THEN** `COLLIE_REAL_HERDR=1 uv run pytest tests/test_real_herdr.py` fails while the faked tests may still pass
