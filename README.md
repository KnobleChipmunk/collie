# collie

Agents running in [Herdr](https://herdr.dev) show you the code they are talking about, in a pane
beside their own, colored with bat (files) and delta (diffs, unified only) in Catppuccin Mocha.
Named for the dog that works the herd.

## Install

Prerequisites: `brew install bat git-delta` (macOS) or the distro packages (Linux).

```bash
uv tool install git+https://github.com/KnobleChipmunk/collie
collie setup --dry-run   # preview: skill link, AGENTS.md block, SessionStart hook
collie setup
```

`collie setup` is idempotent and writes `settings.json.bak.<timestamp>` before changing `~/.claude/settings.json`.

## Use

```bash
collie show path/to/file.py:36-64@41-47 --note "retry loop"
collie show path/to/file.py --match "def _batch"
collie diff HEAD~1 --path src/a.py
collie close
```

The code pane redraws when resized; press any key in it to get your shell back; `COLLIE_RESIDENT=off` draws once.

Set `COLLIE=off` to disable it (builder and reviewer panes). To change the theme, set
`COLLIE_THEME` in your shell profile: the code pane runs its own shell, so a value set only in the
agent's environment does not reach it.

Known limitations: a path with `@` in any parent directory exits 2 (the pane could not parse it back);
each render adds one line to the code pane shell's history.

See `openspec/changes/add-collie/` for the spec.
