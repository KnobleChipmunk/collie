# Tasks: add-collie

## 0. Gates

- `uv run pytest` passes: every test in `tests/test_units.py` and `tests/test_cli.py`, none skipped, none edited except by a recorded lead ruling.
- `uv run ruff check .` and `uv run ruff format --check .` are clean.
- `.venv/bin/python -m py_compile` passes on every file under `src/`.
- Inside Herdr: `COLLIE_REAL_HERDR=1 uv run pytest tests/test_real_herdr.py` passes (replaces the manual pane check). Then the operator runs `collie diff HEAD~1` once by eye to confirm unified output.

## Requirement table

| Requirement (spec.md) | Implementing step | Acceptance evidence |
|---|---|---|
| One reusable pane per agent | 3, 4 | `test_first_call_splits_down_labels_and_runs`, `test_second_call_reuses_pane`, `test_closed_pane_is_recreated`, `test_label_in_other_tab_is_ignored`, `test_busy_code_pane_exits_4_without_input`, `test_close_closes_only_own_pane` |
| Split direction follows width | 3 | `test_choose_direction`, `test_wide_caller_splits_right` |
| File excerpts render with bat | 2, 5 | `test_bat_argv_*`, `test_note_line_is_mocha_mauve`, `test_render_show_clears_notes_and_calls_bat` |
| Diffs render unified only | 2, 5 | `test_diff_argvs_*`, `test_render_diff_pipes_git_into_unified_delta`, `test_render_empty_diff_says_no_changes`, `test_diff_routes_through_render` |
| Stays out of the way | 4 | `test_disabled_is_silent_success`, `test_outside_herdr_exits_3`, `test_rule_prints_only_in_herdr` |
| Validate before touching panes | 1, 4 | `test_parse_range_*`, `test_parse_excerpt_*`, `test_more_than_five_excerpts_exits_2`, `test_reversed_range_exits_2_without_herdr`, `test_missing_file_exits_2_without_herdr`, `test_diff_outside_git_exits_2` |
| Setup idempotent and previewable | 6 | `test_upsert_block_*`, `test_ensure_hook_*`, `test_setup_dry_run_writes_nothing`, `test_setup_twice_is_idempotent` |
| The agent learns what the pane could not show | 2, 4 | `test_overflow`, `test_overflow_is_reported`, `test_no_overflow_text_when_it_fits` |
| Every render carries a header | 2, 5 | `test_header_text`, `test_render_header_without_note`, `test_render_diff_header`, `test_render_show_clears_notes_and_calls_bat` |
| Own render is not the user being busy | 3, 4 | `test_is_own_render`, `test_own_render_finishing_is_waited_for`, `test_own_render_by_cmdline_is_waited_for`, `test_own_render_that_never_finishes_exits_4`, `test_busy_code_pane_exits_4_without_input` |
| Preflight catches pane errors | 4 | `test_missing_bat_exits_2_without_herdr`, `test_missing_delta_exits_2_without_herdr`, `test_bad_revision_exits_2_without_herdr` |
| Creating the pane leaves nothing behind | 4 | `test_rename_failure_closes_new_pane`, `test_new_pane_waits_for_shell`, `test_new_pane_that_never_reaches_prompt_is_closed` |
| Closing is safe and optional | 4 | `test_close_closes_only_own_pane`, `test_close_leaves_busy_pane_open` |
| Earlier excerpts stay in scrollback | 2, 5 | `test_redraw_prefix_keeps_scrollback`, `test_render_show_clears_notes_and_calls_bat`, `test_show_reuse_scrollback_close` (real herdr) |
| Several excerpts in one call | 1, 4, 5 | `test_parse_excerpt_*`, `test_excerpt_spec_and_subject`, `test_several_excerpts_render_in_one_call`, `test_render_several_excerpts_in_order`, `test_more_than_five_excerpts_exits_2`, `test_overflow` |
| Lines found by text | 1, 4 | `test_find_match`, `test_match_finds_lines_by_text`, `test_match_reports_repeats_and_uses_first`, `test_match_not_found_exits_2`, `test_match_with_range_or_several_files_exits_2` |
| Fake checked against real herdr | 8 | `tests/test_real_herdr.py` |
| Installable via uv | 7 | `test_installed_entry_point_exists`, operator runs `uv tool install` on a second machine |

Callers of every new command: `show`, `diff`, `close` are called by agents per `rule.md` and `skill/SKILL.md`; `rule` is called by the SessionStart hook; `setup` by the operator once per machine; `render` only by `show` and `diff` through `herdr pane run`.

## Steps

1. `ranges.py`: `parse_range`, `Excerpt`, `parse_excerpt`, `find_match`.
2. `render.py`: theme, `note_line`, `header_text`, `CHROME_ROWS`, `EXCERPT_ROWS`, `overflow`, `redraw_prefix`, `bat_argv`, `diff_argvs`.
3. `panes.py`: `label_for`, `find_code_pane`, `choose_direction`, `is_idle_shell`, `is_own_render`, `BUSY_GRACE_MS`, `Herdr`, `HerdrError`.
4. `cli.py` and `__main__.py`: subcommands, exit codes 0/2/3/4/5, flow from design.md.
5. `render` subcommand: clear, note, bat or git piped into delta, `no changes` on an empty diff.
6. `setup.py`, `rule.md`, `skill/SKILL.md`: rule text as drafted in design.md.
7. `README.md` install section: `uv tool install git+ssh://git@github.com/KnobleChipmunk/collie`, then `collie setup --dry-run`, then `collie setup`. Prerequisites: `brew install bat git-delta` (macOS) or the distro packages (Linux).
8. `tests/test_real_herdr.py` stays green against the installed herdr; record the herdr version it passed on in the PR.

Review source: the Hermes (Qwen 3.8) design review on 2026-10-09; ideas 1 to 4 and both notes adopted, idea 5 rejected (design.md decision 8).

## Follow ups (separate changes, not this one)

1. herd and herd-claude skills: split builder and reviewer panes with `--env COLLIE=off`.
2. Image export (freeze or silicon) for tickets and Slack.
3. Symbol lookup (`--symbol create_http_app`) via a parser, if `--match` proves too loose.
