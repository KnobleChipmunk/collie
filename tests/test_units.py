"""Pure function contract from design.md, section "Module contract"."""

from pathlib import Path

import pytest

from collie.panes import choose_direction, find_code_pane, is_idle_shell, is_own_render, label_for
from collie.ranges import Excerpt, find_match, parse_excerpt, parse_range
from collie.render import (
    CHROME_ROWS,
    DEFAULT_THEME,
    EXCERPT_ROWS,
    bat_argv,
    diff_argvs,
    header_text,
    note_line,
    overflow,
    redraw_prefix,
    theme,
)
from collie.setup import BLOCK_BEGIN, BLOCK_END, HOOK_COMMAND, ensure_hook, upsert_block

# ranges ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "expected"), [("36-64", (36, 64)), ("41", (41, 41)), ("7-7", (7, 7))])
def test_parse_range_accepts(text: str, expected: tuple[int, int]) -> None:
    assert parse_range(text) == expected


@pytest.mark.parametrize("text", ["", "a-b", "0-5", "-3-4", "64-36", "1-2-3", " ", "36:64", "١-٢"])
def test_parse_range_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        parse_range(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("src/a.py", Excerpt(Path("src/a.py"), None, ())),
        ("src/a.py:36-64", Excerpt(Path("src/a.py"), (36, 64), ())),
        ("src/a.py:41", Excerpt(Path("src/a.py"), (41, 41), ())),
        ("src/a.py:36-64@41-47,50", Excerpt(Path("src/a.py"), (36, 64), ((41, 47), (50, 50)))),
        ("src/a.py@3", Excerpt(Path("src/a.py"), None, ((3, 3),))),
        ("dir:with:colons/b.py:2-3", Excerpt(Path("dir:with:colons/b.py"), (2, 3), ())),
        ("ünï/çödé.py:1-2", Excerpt(Path("ünï/çödé.py"), (1, 2), ())),
    ],
)
def test_parse_excerpt_accepts(text: str, expected: Excerpt) -> None:
    assert parse_excerpt(text) == expected


@pytest.mark.parametrize("text", ["", ":1-2", "a.py:64-36", "a.py:1-10@20", "a.py@", "a.py:1-5@x"])
def test_parse_excerpt_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        parse_excerpt(text)


def test_excerpt_spec_and_subject() -> None:
    ex = Excerpt(Path("/r/src/a.py"), (36, 64), ((41, 47), (50, 50)))
    assert ex.spec() == "/r/src/a.py:36-64@41-47,50-50"
    assert ex.subject() == "a.py:36-64"
    assert Excerpt(Path("/r/a.py"), None, ()).subject() == "a.py"
    assert Excerpt(Path("/r/a.py"), None, ()).spec() == "/r/a.py"


def test_find_match() -> None:
    text = ["a", "target one", "b", "target two", ""]
    assert find_match(text, "target") == (2, 2)  # (first line, number of matching lines)
    assert find_match(text, "two") == (4, 1)
    assert find_match(text, "missing") is None
    assert find_match([], "x") is None


# render ---------------------------------------------------------------------------------------


def test_bat_argv_full() -> None:
    argv = bat_argv(Path("/r/f.py"), (36, 64), [(41, 47), (50, 50)], "Catppuccin Mocha")
    assert argv == [
        "bat",
        "--paging=never",
        "--color=always",
        "--theme=Catppuccin Mocha",
        "--style=numbers,grid,header",
        "--line-range=36:64",
        "--highlight-line=41:47",
        "--highlight-line=50:50",
        "/r/f.py",
    ]


def test_bat_argv_whole_file_no_highlights() -> None:
    argv = bat_argv(Path("/r/f.py"), None, [], "Nord")
    assert argv[-1] == "/r/f.py"
    assert not any(a.startswith(("--line-range", "--highlight-line")) for a in argv)
    assert "--paging=never" in argv


def test_diff_argvs_unified_and_isolated() -> None:
    git, delta = diff_argvs(Path("/r"), "HEAD~1", ["src/a.py"], "Catppuccin Mocha")
    assert git == ["git", "-C", "/r", "-c", "core.pager=cat", "diff", "HEAD~1", "--", "src/a.py"]
    assert delta == ["delta", "--no-gitconfig", "--paging=never", "--line-numbers", "--syntax-theme=Catppuccin Mocha"]


def test_diff_argvs_working_tree_never_side_by_side() -> None:
    git, delta = diff_argvs(Path("/r"), None, [], "Nord")
    assert git == ["git", "-C", "/r", "-c", "core.pager=cat", "diff", "--"]
    assert "-s" not in delta and "--side-by-side" not in delta


def test_note_line_is_mocha_mauve() -> None:
    assert note_line("retry loop") == "\x1b[1;38;2;203;166;247m▶ retry loop\x1b[0m"


def test_theme_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COLLIE_THEME", raising=False)
    assert theme() == DEFAULT_THEME == "Catppuccin Mocha"
    monkeypatch.setenv("COLLIE_THEME", "")
    assert theme() == DEFAULT_THEME
    monkeypatch.setenv("COLLIE_THEME", "Nord")
    assert theme() == "Nord"


def test_header_text() -> None:
    assert header_text("example.py:36-64", None) == "example.py:36-64"
    assert header_text("example.py:36-64", "retry loop") == "example.py:36-64 · retry loop"
    assert header_text("diff working tree", "ünïcode") == "diff working tree · ünïcode"


@pytest.mark.parametrize(
    ("content", "height", "excerpts", "hidden"),
    [(29, 28, 1, 9), (20, 28, 1, 0), (0, 28, 1, 0), (100, 0, 1, 108), (20, 28, 2, 6), (10, 54, 5, 0)],
)
def test_overflow(content: int, height: int, excerpts: int, hidden: int) -> None:
    assert (CHROME_ROWS, EXCERPT_ROWS) == (8, 6)
    assert overflow(content, height, excerpts) == hidden


def test_redraw_prefix_keeps_scrollback() -> None:
    assert redraw_prefix(28) == "\x1b[28S\x1b[H"


# panes ----------------------------------------------------------------------------------------


def test_label_for() -> None:
    assert label_for("w2:pEC") == "collie:w2:pEC"


def test_find_code_pane_matches_label_and_tab() -> None:
    panes = [
        {"pane_id": "w1:p2", "tab_id": "w1:t2", "label": "collie:w1:p1"},  # other tab
        {"pane_id": "w1:p3", "tab_id": "w1:t1", "label": "collie:w1:p7"},  # other caller
        {"pane_id": "w1:p4", "tab_id": "w1:t1"},  # no label
        {"pane_id": "w1:p5", "tab_id": "w1:t1", "label": "collie:w1:p1"},
    ]
    assert find_code_pane(panes, "w1:p1", "w1:t1") == "w1:p5"
    assert find_code_pane(panes, "w1:p1", "w1:t9") is None
    assert find_code_pane([], "w1:p1", "w1:t1") is None


@pytest.mark.parametrize(("width", "direction"), [(255, "right"), (160, "right"), (159, "down"), (128, "down")])
def test_choose_direction(width: int, direction: str) -> None:
    assert choose_direction(width) == direction


@pytest.mark.parametrize(
    ("names", "idle"),
    [(["zsh"], True), (["bash"], True), (["nu"], True), (["bat"], False), (["zsh", "vim"], False), ([], False)],
)
def test_is_idle_shell(names: list[str], idle: bool) -> None:
    assert is_idle_shell({"foreground_processes": [{"name": n} for n in names]}) is idle


@pytest.mark.parametrize(
    ("procs", "own"),
    [
        ([{"name": "bat", "cmdline": "bat x"}], True),
        ([{"name": "git", "cmdline": "git diff"}, {"name": "delta", "cmdline": "delta"}], True),
        ([{"name": "python3.12", "cmdline": "/py -m collie render show /f"}], True),
        ([{"name": "python3.12", "cmdline": "/py manage.py runserver"}], False),
        ([{"name": "vim", "cmdline": "vim x"}], False),
        ([], False),
    ],
)
def test_is_own_render(procs: list[dict], own: bool) -> None:
    assert is_own_render({"foreground_processes": procs}) is own


# setup ----------------------------------------------------------------------------------------


def test_upsert_block_appends_then_replaces() -> None:
    once = upsert_block("# Rules\n", "rule v1")
    assert once.count(BLOCK_BEGIN) == 1 and "rule v1" in once and once.startswith("# Rules\n")
    assert upsert_block(once, "rule v1") == once
    twice = upsert_block(once, "rule v2")
    assert twice.count(BLOCK_BEGIN) == 1 and twice.count(BLOCK_END) == 1
    assert "rule v2" in twice and "rule v1" not in twice


def test_upsert_block_empty_file() -> None:
    out = upsert_block("", "body ✓")
    assert out.count(BLOCK_BEGIN) == 1 and "body ✓" in out


def test_ensure_hook_adds_once_and_keeps_existing() -> None:
    existing = {"hooks": {"SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": "other.sh"}]}]}}
    settings, changed = ensure_hook(existing)
    assert changed
    commands = [h["command"] for e in settings["hooks"]["SessionStart"] for h in e["hooks"]]
    assert commands.count(HOOK_COMMAND) == 1 and "other.sh" in commands
    settings, changed = ensure_hook(settings)
    assert not changed


def test_ensure_hook_on_empty_settings() -> None:
    settings, changed = ensure_hook({})
    assert changed
    assert settings["hooks"]["SessionStart"][0]["hooks"] == [{"type": "command", "command": "collie rule"}]


# resident renderer (rerender-on-resize) -------------------------------------------------------


def test_resident_constants() -> None:
    from collie.panes import RENDER_MARK
    from collie.resident import REDRAW_CLEAR, SETTLE_S

    assert REDRAW_CLEAR == "\x1b[H\x1b[2J"
    assert SETTLE_S == 0.15
    assert RENDER_MARK == "-m collie render"


class _Tty:
    def __init__(self, tty: bool) -> None:
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


@pytest.mark.parametrize(
    ("stdin", "stdout", "env", "expected"),
    [(True, True, None, True), (False, True, None, False), (True, False, None, False), (True, True, "off", False)],
)
def test_resident_enabled(
    monkeypatch: pytest.MonkeyPatch, stdin: bool, stdout: bool, env: str | None, expected: bool
) -> None:
    import sys

    from collie.resident import resident_enabled

    monkeypatch.setattr(sys, "stdin", _Tty(stdin))
    monkeypatch.setattr(sys, "stdout", _Tty(stdout))
    if env is None:
        monkeypatch.delenv("COLLIE_RESIDENT", raising=False)
    else:
        monkeypatch.setenv("COLLIE_RESIDENT", env)
    assert resident_enabled() is expected


def test_renderer_pids() -> None:
    from collie.panes import renderer_pids

    info = {
        "foreground_processes": [
            {"name": "Python", "cmdline": "/py -m collie render show /f", "pid": 11},
            {"name": "bat", "cmdline": "bat --paging=never /f", "pid": 12},
            {"name": "Python", "cmdline": "/py -m collie render diff --repo /r", "pid": "13"},
            {"name": "Python", "cmdline": "/py -m collie render show /g"},
        ]
    }
    assert renderer_pids(info) == [11]
    assert renderer_pids({"foreground_processes": []}) == []


def test_is_collie_renderer_reads_the_live_command(processes) -> None:
    from collie.panes import is_collie_renderer
    from conftest import NOT_A_RENDERER, RENDERER_LIKE

    renderer = processes(RENDERER_LIKE)
    other = processes(NOT_A_RENDERER)
    assert is_collie_renderer(renderer.pid) is True
    assert is_collie_renderer(other.pid) is False
    other.kill()
    other.wait()
    assert is_collie_renderer(other.pid) is False  # gone: never signalled


def test_stop_renderers_signals_only_confirmed(processes) -> None:
    from collie.panes import stop_renderers
    from conftest import NOT_A_RENDERER, RENDERER_LIKE

    renderer = processes(RENDERER_LIKE)
    impostor = processes(NOT_A_RENDERER)  # herdr claims it is a renderer; ps says otherwise
    info = {
        "foreground_processes": [
            {"name": "Python", "cmdline": "/py -m collie render show /x", "pid": renderer.pid},
            {"name": "Python", "cmdline": "/py -m collie render show /y", "pid": impostor.pid},
        ]
    }
    assert stop_renderers(info) == 1
    assert renderer.wait(timeout=5) == -15  # SIGTERM
    assert impostor.poll() is None
