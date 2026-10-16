## ADDED Requirements

### Requirement: The code pane redraws after a resize
When the render command runs with a terminal on stdin and stdout, it SHALL stay running after its first draw and, after each burst of resizes settles for 150 ms, clear the screen and draw the same content again at the new width.

#### Scenario: The user widens the code pane
- **WHEN** the code pane goes from 100 to 133 columns after `collie show f.py:1-5`
- **THEN** bat runs again and sees 133 columns, after a screen clear and without another scroll up

#### Scenario: A drag produces many resizes
- **WHEN** five resizes arrive within 50 ms
- **THEN** the content is drawn again exactly once, at the final width

#### Scenario: A diff is on screen
- **WHEN** the pane is resized after `collie diff`
- **THEN** delta runs again at the new width

### Requirement: The resident renderer gives the pane back cleanly
The resident renderer SHALL exit 0 and restore the terminal on any key press in the code pane, and on SIGTERM, SIGHUP, or SIGINT.

#### Scenario: The user presses a key
- **WHEN** the user types any key in the code pane
- **THEN** the renderer exits 0 and the shell prompt returns

### Requirement: Run once when not on a terminal
The render command SHALL draw once and exit when stdin or stdout is not a terminal, or when `COLLIE_RESIDENT=off`.

#### Scenario: Output is captured
- **WHEN** `render show` runs with stdout piped
- **THEN** it exits after one draw

### Requirement: collie stops its own renderer before reusing or closing the pane
`collie show`, `collie diff`, and `collie close` SHALL send SIGTERM to a foreground process whose herdr `cmdline` and live `ps` command line both contain `-m collie render`, then wait up to the busy grace period for the shell, and SHALL never type into the pane.

#### Scenario: Second show while the first is resident
- **WHEN** the code pane's foreground is collie's resident renderer
- **THEN** the renderer is stopped, the new render runs in the same pane, and no new pane is split

#### Scenario: herdr's pid no longer belongs to collie
- **WHEN** herdr reports a collie renderer but `ps` shows a different command for that pid
- **THEN** no signal is sent, and the tool exits 4 once the grace period ends

#### Scenario: Close while resident
- **WHEN** `collie close` finds collie's resident renderer in the pane
- **THEN** it stops the renderer and closes the pane, exit 0
