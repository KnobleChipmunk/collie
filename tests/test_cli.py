"""End to end contract for the CLI against the fake herdr (spec.md requirements)."""

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import CALLER, TAB, FakeHerdr

LABEL = f"collie:{CALLER}"


def render_argv(fake: FakeHerdr) -> list[str]:
    ((_, command),) = fake.run_commands()
    return shlex.split(command)


# one reusable pane per agent ------------------------------------------------------------------


def test_first_call_splits_down_labels_and_runs(herdr: FakeHerdr, source_file: Path) -> None:
    r = herdr.cli("show", f"{source_file}:36-64@41-47", "--note", "retry loop")
    assert r.returncode == 0, r.stderr
    split = next(c for c in herdr.calls() if c[1] == "split")
    assert split[split.index("--pane") + 1] == CALLER
    assert split[split.index("--direction") + 1] == "down"  # caller is 128 wide
    assert "--no-focus" in split and "--focus" not in split
    assert herdr.panes()["w1:p9"]["label"] == LABEL
    assert "w1:p9" in r.stdout

    pane, _ = herdr.run_commands()[0]
    assert pane == "w1:p9"
    argv = render_argv(herdr)
    assert argv[:4] == [sys.executable, "-m", "collie", "render"]
    assert f"{source_file.resolve()}:36-64@41-47" in argv
    assert "retry loop" in argv


def test_wide_caller_splits_right(herdr: FakeHerdr, source_file: Path) -> None:
    herdr.set_panes({CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 255}})
    assert herdr.cli("show", str(source_file)).returncode == 0
    split = next(c for c in herdr.calls() if c[1] == "split")
    assert split[split.index("--direction") + 1] == "right"


def test_second_call_reuses_pane(herdr: FakeHerdr, source_file: Path) -> None:
    assert herdr.cli("show", f"{source_file}:1-10").returncode == 0
    assert herdr.cli("show", f"{source_file}:20-30").returncode == 0
    assert herdr.verbs().count("split") == 1
    assert [p for p, _ in herdr.run_commands()] == ["w1:p9", "w1:p9"]


def test_closed_pane_is_recreated(herdr: FakeHerdr, source_file: Path) -> None:
    assert herdr.cli("show", str(source_file)).returncode == 0
    panes = herdr.panes()
    del panes["w1:p9"]
    herdr.set_panes(panes, next_id="w1:p10")
    assert herdr.cli("show", str(source_file)).returncode == 0
    assert herdr.verbs().count("split") == 2
    assert herdr.panes()["w1:p10"]["label"] == LABEL


def test_label_in_other_tab_is_ignored(herdr: FakeHerdr, source_file: Path) -> None:
    herdr.set_panes(
        {
            CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128},
            "w1:p5": {"tab_id": "w1:t2", "cwd": "/tmp", "width": 80, "label": LABEL},
        }
    )
    assert herdr.cli("show", str(source_file)).returncode == 0
    assert herdr.verbs().count("split") == 1
    assert herdr.run_commands()[0][0] == "w1:p9"


def test_busy_code_pane_exits_4_without_input(herdr: FakeHerdr, source_file: Path) -> None:
    herdr.set_panes(
        {
            CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128},
            "w1:p5": {"tab_id": TAB, "cwd": "/tmp", "width": 80, "label": LABEL, "procs_seq": [["vim"]]},
        }
    )
    r = herdr.cli("show", str(source_file))
    assert r.returncode == 4
    assert "w1:p5" in r.stderr
    assert not {"run", "send-keys", "send-text", "split"} & set(herdr.verbs())
    assert herdr.calls_on("process-info", "w1:p5") == 1  # the user's program: no polling


def renderer_entry(pid: int) -> dict:
    return {"name": "Python", "cmdline": f"{sys.executable} -m collie render show /x", "pid": pid}


def test_resident_renderer_is_stopped_then_pane_reused(herdr: FakeHerdr, source_file: Path, processes) -> None:
    from conftest import RENDERER_LIKE

    renderer = processes(RENDERER_LIKE)
    herdr.set_panes(
        {
            CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128},
            "w1:p5": {
                "tab_id": TAB,
                "cwd": "/tmp",
                "width": 80,
                "label": LABEL,
                "procs_seq": [[renderer_entry(renderer.pid)], ["zsh"]],
            },
        }
    )
    r = herdr.cli("show", str(source_file))
    assert r.returncode == 0, r.stderr
    assert renderer.wait(timeout=5) == -15
    assert herdr.run_commands()[0][0] == "w1:p5"
    assert "split" not in herdr.verbs()
    assert not {"send-keys", "send-text"} & set(herdr.verbs())


def test_stale_renderer_pid_is_not_signalled(herdr: FakeHerdr, source_file: Path, processes) -> None:
    from conftest import NOT_A_RENDERER

    impostor = processes(NOT_A_RENDERER)
    herdr.set_panes(
        {
            CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128},
            "w1:p5": {
                "tab_id": TAB,
                "cwd": "/tmp",
                "width": 80,
                "label": LABEL,
                "procs_seq": [[renderer_entry(impostor.pid)]],
            },
        }
    )
    r = herdr.cli("show", str(source_file))
    assert r.returncode == 4
    assert impostor.poll() is None
    assert "run" not in herdr.verbs()


@pytest.mark.parametrize("command", ["show", "close"])
def test_empty_foreground_after_stop_is_waited_out(
    herdr: FakeHerdr, source_file: Path, processes, command: str
) -> None:
    """Real herdr 0.8.0 briefly reports no foreground process between the renderer's exit and the shell's prompt."""
    from conftest import RENDERER_LIKE

    renderer = processes(RENDERER_LIKE)
    herdr.set_panes(
        {
            CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128},
            "w1:p5": {
                "tab_id": TAB,
                "cwd": "/tmp",
                "width": 80,
                "label": LABEL,
                "procs_seq": [[renderer_entry(renderer.pid)], [], [], ["zsh"]],
            },
        }
    )
    args = ["show", str(source_file)] if command == "show" else ["close"]
    r = herdr.cli(*args)
    assert r.returncode == 0, r.stderr
    assert renderer.wait(timeout=5) == -15


def test_close_stops_resident_renderer(herdr: FakeHerdr, processes) -> None:
    from conftest import RENDERER_LIKE

    renderer = processes(RENDERER_LIKE)
    herdr.set_panes(
        {
            CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128},
            "w1:p5": {
                "tab_id": TAB,
                "cwd": "/tmp",
                "width": 80,
                "label": LABEL,
                "procs_seq": [[renderer_entry(renderer.pid)], ["zsh"]],
            },
        }
    )
    r = herdr.cli("close")
    assert r.returncode == 0, r.stderr
    assert renderer.wait(timeout=5) == -15
    assert "w1:p5" not in herdr.panes()


def test_herdr_error_exits_5(herdr: FakeHerdr, source_file: Path) -> None:
    herdr.set_panes({})  # caller pane unknown to herdr
    r = herdr.cli("show", str(source_file))
    assert r.returncode == 5
    assert "pane_not_found" in r.stderr


def test_diff_routes_through_render(herdr: FakeHerdr, git_repo: Path) -> None:
    r = herdr.cli("diff", "HEAD", "--path", "a.py", "--repo", str(git_repo), "--note", "bump")
    assert r.returncode == 0, r.stderr
    argv = shlex.split(herdr.run_commands()[-1][1])
    assert argv[:5] == [sys.executable, "-m", "collie", "render", "diff"]
    assert "HEAD" in argv and "a.py" in argv and str(git_repo.resolve()) in argv
    assert "--side-by-side" not in argv and "-s" not in argv


def test_close_closes_only_own_pane(herdr: FakeHerdr) -> None:
    herdr.set_panes(
        {
            CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128},
            "w1:p5": {"tab_id": TAB, "cwd": "/tmp", "width": 80, "label": LABEL},
            "w1:p6": {"tab_id": TAB, "cwd": "/tmp", "width": 80, "label": "collie:w1:p2"},
        }
    )
    assert herdr.cli("close").returncode == 0
    assert set(herdr.panes()) == {CALLER, "w1:p6"}
    assert herdr.cli("close").returncode == 0  # nothing to close is not an error


def test_several_excerpts_render_in_one_call(herdr: FakeHerdr, source_file: Path, tmp_path: Path) -> None:
    other = tmp_path / "other.py"
    other.write_text("".join(f"o_{i} = {i}\n" for i in range(1, 51)))
    r = herdr.cli("show", f"{source_file}:10-20@12", f"{other}:40-45", "--note", "flow")
    assert r.returncode == 0, r.stderr
    assert herdr.verbs().count("run") == 1
    argv = render_argv(herdr)
    assert f"{source_file.resolve()}:10-20@12-12" in argv and f"{other.resolve()}:40-45" in argv


def test_render_several_excerpts_in_order(herdr: FakeHerdr, source_file: Path, tmp_path: Path) -> None:
    other = tmp_path / "other.py"
    other.write_text("o = 1\n")
    r = herdr.cli("render", "show", f"{source_file}:10-20", f"{other}", "--note", "flow")
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    first = next(i for i, line in enumerate(lines) if "▶ example.py:10-20 · flow" in line)
    second = next(i for i, line in enumerate(lines) if "▶ other.py\x1b[0m" in line)
    bats = [i for i, line in enumerate(lines) if line.startswith("BAT ")]
    assert first < bats[0] < second < bats[1] and len(bats) == 2


def test_more_than_five_excerpts_exits_2(herdr: FakeHerdr, source_file: Path) -> None:
    r = herdr.cli("show", *[f"{source_file}:{i}-{i}" for i in range(1, 7)])
    assert r.returncode == 2
    assert herdr.calls() == []


def test_match_finds_lines_by_text(herdr: FakeHerdr, source_file: Path) -> None:
    r = herdr.cli("show", str(source_file), "--match", "line_50 =", "--context", "10")
    assert r.returncode == 0, r.stderr
    assert f"{source_file.resolve()}:47-59@50-50" in render_argv(herdr)


def test_match_reports_repeats_and_uses_first(herdr: FakeHerdr, source_file: Path) -> None:
    r = herdr.cli("show", str(source_file), "--match", "line_7")  # line_7, line_70 .. line_79
    assert r.returncode == 0, r.stderr
    assert f"{source_file.resolve()}:4-36@7-7" in render_argv(herdr)  # default context 30
    assert "matched 11 times" in r.stdout


def test_match_not_found_exits_2(herdr: FakeHerdr, source_file: Path) -> None:
    r = herdr.cli("show", str(source_file), "--match", "no such text")
    assert r.returncode == 2 and "no such text" in r.stderr
    assert herdr.calls() == []


def test_match_with_range_or_several_files_exits_2(herdr: FakeHerdr, source_file: Path) -> None:
    assert herdr.cli("show", f"{source_file}:1-5", "--match", "line_2").returncode == 2
    assert herdr.cli("show", str(source_file), str(source_file), "--match", "line_2").returncode == 2
    assert herdr.calls() == []


def test_overflow_is_reported(herdr: FakeHerdr, source_file: Path) -> None:
    r = herdr.cli("show", f"{source_file}:36-64")  # 29 lines + 8 chrome in 28 rows
    assert r.returncode == 0, r.stderr
    assert "fits ~20 of 29 lines" in r.stdout and "first 9 scrolled out of view" in r.stdout


def test_no_overflow_text_when_it_fits(herdr: FakeHerdr, source_file: Path) -> None:
    r = herdr.cli("show", f"{source_file}:1-10")
    assert r.returncode == 0, r.stderr
    assert "scrolled" not in r.stdout


def test_own_render_finishing_is_waited_for(herdr: FakeHerdr, source_file: Path) -> None:
    herdr.set_panes(
        {
            CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128},
            "w1:p5": {"tab_id": TAB, "cwd": "/tmp", "width": 80, "label": LABEL, "procs_seq": [["bat"], ["zsh"]]},
        }
    )
    r = herdr.cli("show", str(source_file))
    assert r.returncode == 0, r.stderr
    assert herdr.run_commands()[0][0] == "w1:p5"


def test_own_render_by_cmdline_is_waited_for(herdr: FakeHerdr, source_file: Path) -> None:
    render = {"name": "python3.12", "cmdline": "/x/python -m collie render show /f.py"}
    herdr.set_panes(
        {
            CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128},
            "w1:p5": {"tab_id": TAB, "cwd": "/tmp", "width": 80, "label": LABEL, "procs_seq": [[render], ["zsh"]]},
        }
    )
    assert herdr.cli("show", str(source_file)).returncode == 0


def test_own_render_that_never_finishes_exits_4(herdr: FakeHerdr, source_file: Path) -> None:
    herdr.set_panes(
        {
            CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128},
            "w1:p5": {"tab_id": TAB, "cwd": "/tmp", "width": 80, "label": LABEL, "procs_seq": [["delta"]]},
        }
    )
    r = herdr.cli("show", str(source_file))
    assert r.returncode == 4
    assert herdr.calls_on("process-info", "w1:p5") > 1
    assert "run" not in herdr.verbs()


def test_rename_failure_closes_new_pane(herdr: FakeHerdr, source_file: Path) -> None:
    herdr.set_panes({CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128}}, fail_rename=True)
    r = herdr.cli("show", str(source_file))
    assert r.returncode == 5
    assert "w1:p9" not in herdr.panes()
    assert "run" not in herdr.verbs()


def test_new_pane_waits_for_shell(herdr: FakeHerdr, source_file: Path) -> None:
    herdr.set_panes(
        {CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128}}, new_pane={"procs_seq": [["direnv"], ["zsh"]]}
    )
    assert herdr.cli("show", str(source_file)).returncode == 0
    calls = herdr.calls()
    checks = [i for i, c in enumerate(calls) if c[1] == "process-info" and "w1:p9" in c]
    run_at = next(i for i, c in enumerate(calls) if c[1] == "run")
    assert len(checks) >= 2 and max(checks) < run_at


def test_new_pane_that_never_reaches_prompt_is_closed(herdr: FakeHerdr, source_file: Path) -> None:
    herdr.set_panes({CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128}}, new_pane={"procs_seq": [["direnv"]]})
    r = herdr.cli("show", str(source_file))
    assert r.returncode == 4
    assert "w1:p9" not in herdr.panes()
    assert "run" not in herdr.verbs()


def test_close_leaves_busy_pane_open(herdr: FakeHerdr) -> None:
    herdr.set_panes(
        {
            CALLER: {"tab_id": TAB, "cwd": "/tmp", "width": 128},
            "w1:p5": {"tab_id": TAB, "cwd": "/tmp", "width": 80, "label": LABEL, "procs_seq": [["vim"]]},
        }
    )
    assert herdr.cli("close").returncode == 4
    assert "w1:p5" in herdr.panes()


# validation before any pane is touched --------------------------------------------------------


def test_reversed_range_exits_2_without_herdr(herdr: FakeHerdr, source_file: Path) -> None:
    r = herdr.cli("show", f"{source_file}:64-36")
    assert r.returncode == 2
    assert herdr.calls() == []


def test_missing_file_exits_2_without_herdr(herdr: FakeHerdr, tmp_path: Path) -> None:
    assert herdr.cli("show", str(tmp_path / "nope.py")).returncode == 2
    assert herdr.calls() == []


def test_diff_outside_git_exits_2(herdr: FakeHerdr, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert herdr.cli("diff", "--repo", str(plain)).returncode == 2
    assert herdr.calls() == []


def path_with(tmp_path: Path, *tools: str) -> str:
    """A PATH holding only the fake herdr plus the named real or fake tools."""
    import shutil

    from conftest import FAKES

    bin_dir = tmp_path / "limited-bin"
    bin_dir.mkdir(exist_ok=True)
    for tool in ("herdr", *tools):
        source = FAKES / tool if (FAKES / tool).exists() else Path(shutil.which(tool) or "")
        (bin_dir / tool).symlink_to(source)
    return str(bin_dir)


def test_missing_bat_exits_2_without_herdr(herdr: FakeHerdr, source_file: Path, tmp_path: Path) -> None:
    r = herdr.cli("show", str(source_file), extra_env={"PATH": path_with(tmp_path)})
    assert r.returncode == 2 and "bat" in r.stderr
    assert herdr.calls() == []


def test_missing_delta_exits_2_without_herdr(herdr: FakeHerdr, git_repo: Path, tmp_path: Path) -> None:
    r = herdr.cli("diff", "--repo", str(git_repo), extra_env={"PATH": path_with(tmp_path, "git")})
    assert r.returncode == 2 and "delta" in r.stderr
    assert herdr.calls() == []


def test_bad_revision_exits_2_without_herdr(herdr: FakeHerdr, git_repo: Path) -> None:
    r = herdr.cli("diff", "nosuchrev", "--repo", str(git_repo))
    assert r.returncode == 2 and "nosuchrev" in r.stderr
    assert herdr.calls() == []


# staying out of the way -----------------------------------------------------------------------


def test_disabled_is_silent_success(herdr: FakeHerdr, source_file: Path, git_repo: Path) -> None:
    off = {"COLLIE": "off"}
    r = herdr.cli("show", str(source_file), extra_env=off)
    assert r.returncode == 0 and "disabled" in r.stdout
    r = herdr.cli("diff", "--repo", str(git_repo), extra_env=off)
    assert r.returncode == 0 and "disabled" in r.stdout
    r = herdr.cli("rule", extra_env=off)
    assert r.returncode == 0 and r.stdout == ""
    assert herdr.calls() == []


def test_outside_herdr_exits_3(herdr: FakeHerdr, source_file: Path) -> None:
    r = herdr.cli("show", str(source_file), extra_env={"HERDR_ENV": ""})
    assert r.returncode == 3
    assert herdr.calls() == []


def test_rule_prints_only_in_herdr(herdr: FakeHerdr) -> None:
    r = herdr.cli("rule")
    assert r.returncode == 0
    assert "collie show" in r.stdout and "collie diff" in r.stdout and "COLLIE=off" in r.stdout
    assert herdr.cli("rule", extra_env={"HERDR_ENV": ""}).stdout == ""


# render, inside the code pane -----------------------------------------------------------------


def test_render_show_clears_notes_and_calls_bat(herdr: FakeHerdr, source_file: Path) -> None:
    r = herdr.cli("render", "show", f"{source_file}:36-64@41-47", "--note", "hi", extra_env={"LINES": "30"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("\x1b[30S\x1b[H")  # scroll old output into scrollback, then home
    assert "\x1b[3J" not in r.stdout and "\x1b[2J" not in r.stdout  # scrollback is never wiped
    assert "\x1b[1;38;2;203;166;247m▶ example.py:36-64 · hi\x1b[0m" in r.stdout
    bat_line = next(line for line in r.stdout.splitlines() if line.startswith("BAT "))
    argv = json.loads(bat_line[4:])
    assert "--theme=Catppuccin Mocha" in argv and "--line-range=36:64" in argv and "--highlight-line=41:47" in argv


def test_render_diff_pipes_git_into_unified_delta(herdr: FakeHerdr, git_repo: Path) -> None:
    gitconfig = Path(herdr.env["HOME"]) / ".gitconfig"
    gitconfig.write_text("[delta]\n\tside-by-side = true\n")
    r = herdr.cli("render", "diff", "--repo", str(git_repo), "HEAD", "--path", "a.py")
    assert r.returncode == 0, r.stderr
    delta_line = next(line for line in r.stdout.splitlines() if line.startswith("DELTA "))
    argv = json.loads(delta_line[6:])
    assert "--no-gitconfig" in argv and "--side-by-side" not in argv and "-s" not in argv
    assert "DELTA_STDIN_LINES 0" not in r.stdout


def test_render_header_without_note(herdr: FakeHerdr, source_file: Path) -> None:
    r = herdr.cli("render", "show", f"{source_file}:36-64")
    assert "\x1b[1;38;2;203;166;247m▶ example.py:36-64\x1b[0m" in r.stdout
    r = herdr.cli("render", "show", str(source_file))
    assert "\x1b[1;38;2;203;166;247m▶ example.py\x1b[0m" in r.stdout


def test_render_diff_header(herdr: FakeHerdr, git_repo: Path) -> None:
    r = herdr.cli("render", "diff", "--repo", str(git_repo), "HEAD", "--path", "a.py")
    assert "▶ diff HEAD -- a.py" in r.stdout
    r = herdr.cli("render", "diff", "--repo", str(git_repo))
    assert "▶ diff working tree" in r.stdout


def test_render_empty_diff_says_no_changes(herdr: FakeHerdr, git_repo: Path) -> None:
    subprocess.run(["git", "-C", str(git_repo), "checkout", "-q", "--", "a.py"], check=True)
    r = herdr.cli("render", "diff", "--repo", str(git_repo))
    assert r.returncode == 0
    assert "no changes" in r.stdout and "DELTA" not in r.stdout


# setup ----------------------------------------------------------------------------------------


def test_setup_dry_run_writes_nothing(herdr: FakeHerdr) -> None:
    home = Path(herdr.env["HOME"])
    r = herdr.cli("setup", "--dry-run")
    assert r.returncode == 0
    assert r.stdout.count("would ") == 3
    assert list(home.rglob("*")) == []


def test_setup_twice_is_idempotent(herdr: FakeHerdr) -> None:
    home = Path(herdr.env["HOME"])
    (home / ".agents").mkdir()
    (home / ".agents" / "AGENTS.md").write_text("# Global agent instructions\n")
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text(json.dumps({"model": "opus"}))

    assert herdr.cli("setup").returncode == 0
    second = herdr.cli("setup")
    assert second.returncode == 0
    assert "unchanged" in second.stdout

    agents = (home / ".agents" / "AGENTS.md").read_text()
    assert agents.startswith("# Global agent instructions\n")
    assert agents.count("<!-- collie:begin -->") == 1
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    assert settings["model"] == "opus"
    commands = [h["command"] for e in settings["hooks"]["SessionStart"] for h in e["hooks"]]
    assert commands.count("collie rule") == 1
    assert len(list((home / ".claude").glob("settings.json.bak.*"))) == 1  # unchanged rerun adds none
    link = home / ".claude" / "skills" / "collie"
    assert link.is_symlink() and (link / "SKILL.md").exists()


def test_installed_entry_point_exists() -> None:
    """`uv tool install` exposes the console script declared in pyproject.toml."""
    import tomllib

    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert pyproject["project"]["scripts"]["collie"] == "collie.cli:main"
