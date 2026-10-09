---
name: collie
description: Show code in a Herdr pane beside your own, colored with bat (files) and delta (diffs), instead of describing it. Use when you explain what code does, cite file:line to the user, or summarize a diff, and HERDR_ENV=1.
---

# collie

Show the exact lines you are talking about, then explain only what the pane does not show.

## Commands

- `collie show <file>:N-M[@H-H] [<file>:N-M ...] [--note "<one line>"]` renders 1 to 5 excerpts in one call.
  `@H-H` highlights lines inside the range; several highlights are comma separated (`@41-47,50`).
- `collie show <file> --match "<text>" [--context N]` finds lines by text (first match, default context 30).
  Use it after you edited the file, when line numbers have moved.
- `collie diff [<rev>] [--path <p>]... [--note "..."] [--repo DIR]` renders a unified diff.
- `collie close` closes your code pane if it is idle. Optional.

## Behavior

- The first call splits your pane without moving focus and labels the new pane `collie:<your pane id>`.
  Later calls reuse it. Earlier excerpts stay in the pane's scrollback.
- Exit 4: the user is using the code pane (or it never reached a prompt). Say so and continue in prose.
- Exit 3: not inside Herdr. Exit 2: bad arguments (nothing was shown). Exit 5: Herdr returned an error.
- If stdout reports lines scrolled out of view, show a smaller range; do not claim the user saw them.
- `COLLIE=off` disables the tool. Do not use it in delegated sessions (builder, reviewer).
