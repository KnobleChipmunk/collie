HERDR CODE PANES (HERDR_ENV=1): when you explain what code does, or cite file:line to the user,
show it first: `collie show <file>:N-M[@H-H] [<file>:N-M ...] [--note "<one line>"]` (up to 5
excerpts in one call when the explanation spans files). If you edited the file this session, find
lines by text instead: `collie show <file> --match "<text>" [--context N]`.
For what changed: `collie diff [<rev>] [--path <p>] [--note "..."]`. Then explain only what
the pane does not show, citing file:line. The pane is reused; never open your own. Skip this in
delegated sessions (builder, reviewer) and when COLLIE=off. If collie reports lines scrolled out
of view, show a smaller range instead of claiming the user saw them. Exit 4 means the user is
using the pane: say so and continue without it. Closing the pane (`collie close`) is optional.
