# Add collie: agents show code in a Herdr pane instead of describing it

## Why

When an agent explains code, I read prose about lines I cannot see. I want the agent to open a
pane beside its own and render the exact lines it is talking about, colored like VS Code, then
explain only what the pane does not already show. This has to behave the same on every machine
I use, so it ships as an installable tool from a personal git repo, not as hand edits to dotfiles.

## Grounded facts

Every claim below was read or run on 2026-10-09 on the Mac (Darwin arm64).

Herdr 0.8.0 (`herdr --version`):

1. `herdr pane split [<pane_id>|--pane ID|--current] --direction right|down [--ratio FLOAT] [--cwd PATH] [--env KEY=VALUE] [--focus] [--no-focus]` (`herdr pane` help output). The new pane id is at `.result.pane.pane_id` (observed: split returned `w2:pED`).
2. `herdr pane rename <PANE_ID> [LABEL]` sets `label`, and `label` is then returned by `herdr pane get` and `herdr pane list` (observed: renamed `w2:pED` to `collie:w2:pEC`, read back from `pane get`).
3. `herdr pane get <id>` returns `.result.pane.tab_id`, `.result.pane.cwd`, `.result.pane.label` (when set). An unknown id returns `{"error":{"code":"pane_not_found",...}}` on stdout with exit status 1 (observed with `w2:pZZZ`).
4. `herdr pane layout --pane ID` returns `.result.layout.panes[]` with `pane_id` and `rect.width` (observed: caller `w2:pEC` width 128 after the split, 255 before).
5. `herdr pane process-info --pane ID` returns `.result.process_info.foreground_processes[]` with `name` (observed: `zsh` for an idle shell pane).
6. `herdr pane run <pane_id> <command>` types the command and Enter. It does not wait.
7. Herdr injects `HERDR_ENV=1`, `HERDR_PANE_ID`, `HERDR_TAB_ID`, `HERDR_WORKSPACE_ID` into managed panes (`/herdr` skill, "Use IDs and caller context").

bat 0.26.1:

8. `-r, --line-range <N:M>`, `-H, --highlight-line <N:M>`, `--paging <when>`, `--style <components>`, `--theme <theme>`, `--color <when>` (`bat --help` lines 191, 40, 97, 159, 119, 78). `BAT_THEME` sets the default theme (line 122).
9. `Catppuccin Mocha` is a built in theme (`bat --list-themes`).
10. Without `--paging=never`, bat opened a pager in the pane and waited for a key (observed in this session).

delta 0.20.1 (installed this session via `brew install git-delta`):

11. `-n, --line-numbers`, `--paging <auto|always|never>`, `--syntax-theme <SYNTAX_THEME>`, `-s, --side-by-side` (`delta --help` lines 451, 656, 754, 751).
12. `--no-gitconfig`: "Do not read any settings from git config" (`delta --help` line 644). Without it, a `[delta] side-by-side = true` in any machine's gitconfig would override our unified layout.
13. Side by side at 127 columns wrapped long lines with `↵` and `…` markers and doubled the row count of an 8 line comment block (observed, commit `4114846` of global-agent-memory). Unified at the same width did not wrap.

Instruction delivery:

14. `~/.claude/hooks/herdr-session-banner.sh` prints its banner only when `HERDR_ENV=1`; SessionStart hook output reaches the model as session context (observed at the start of this session).
15. `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` both say `~/.agents/AGENTS.md` applies "in full" but neither inlines it, so a rule placed only in `~/.agents/AGENTS.md` is not guaranteed to be in a Claude session's context. A SessionStart hook is.
16. `~/.agents/AGENTS.md` caps itself at 12 to 15 rules and currently has 11 numbered sections.

Added after the Hermes review (same day):

17. `herdr pane layout` rects include `height` (observed: `w2:pED` is width 133, height 28 after the user split it).
18. `herdr pane process-info` entries include `cmdline` as well as `name` (observed on `w2:pEE`).
19. bat with `--style=numbers,grid` wraps a long line onto continuation rows whose line number column is blank (tested with `--terminal-width=60`).
20. Printing `\e[<rows>S` then `\e[H` in a herdr pane left the screen showing only the new output while all 40 earlier lines stayed readable through `herdr pane read --source recent`; `max_offset_from_bottom` became 54 (tested in `w2:pED`).
21. `herdr pane read` prints plain text, while `pane wait-output` prints JSON with `.result.matched_line`; `herdr tab create [--workspace] [--cwd] [--label] [--no-focus]` and `herdr tab close <tab_id>` exist (`herdr tab` help).
22. `tab create` returns `.result.tab` and `.result.root_pane` (`/herdr` skill, "Use IDs and caller context"); `tests/test_real_herdr.py` is the first place this runs, and a wrong shape fails it loudly at fixture setup.

## What Changes

A new personal repo, `collie`, installable with `uv tool install`, providing one CLI:

| Command | Does |
|---|---|
| `collie show PATH[:N-M][@H-H,...] [...up to 5] [--note TEXT]` | Renders one to five excerpts with bat in the agent's code pane |
| `collie show PATH --match TEXT [--context N]` | Finds lines by text instead of numbers, then renders them |
| `collie diff [REV] [--path P]... [--note TEXT]` | Renders a git diff with delta, unified only, in the code pane |
| `collie close` | Closes this agent's code pane if it is idle; optional for agents |
| `collie rule` | Prints the agent rule, only when `HERDR_ENV=1` and not disabled |
| `collie setup [--dry-run]` | Installs the skill link, the AGENTS.md block, and the SessionStart hook on this machine |
| `collie render ...` | Internal: runs inside the code pane and draws the output |

Each calling agent pane owns at most one code pane, found again by its Herdr label, so repeated
calls redraw in place instead of opening new panes.

## Non-goals

1. No side by side diff mode, at any width.
2. No neovim, freeze, or silicon integration. Images for sharing are a separate change.
3. No Windows support. Herdr runs on macOS and Linux.
4. No change to the herd skills in this change. Turning panes off for builder and reviewer panes (passing `--env COLLIE=off` at split time) is a follow up in the herd repo.
5. No scrolling control. Herdr 0.8.0 exposes no command to scroll a pane to the bottom.

## Impact

New repo only. On each machine, `collie setup` writes three things outside the repo, each
idempotent and each previewable with `--dry-run`: a symlink at `~/.claude/skills/collie`, a
marked block in `~/.agents/AGENTS.md`, and one SessionStart hook entry in `~/.claude/settings.json`
(with a timestamped `.bak` copy written first, only when it changes).
