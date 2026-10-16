import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

FAKES = Path(__file__).parent / "fakes"
CALLER = "w1:p1"
TAB = "w1:t1"


@dataclass
class FakeHerdr:
    state_path: Path
    log_path: Path
    env: dict[str, str]

    def set_panes(self, panes: dict, next_id: str = "w1:p9", **extra: object) -> None:
        self.state_path.write_text(json.dumps({"panes": panes, "next_id": next_id, **extra}))

    def panes(self) -> dict:
        return json.loads(self.state_path.read_text())["panes"]

    def calls(self) -> list[list[str]]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text().splitlines()]

    def calls_on(self, verb: str, pane: str) -> int:
        return sum(1 for c in self.calls() if c[1] == verb and pane in c)

    def verbs(self) -> list[str]:
        return [c[1] for c in self.calls()]

    def run_commands(self) -> list[tuple[str, str]]:
        return [(c[2], c[3]) for c in self.calls() if c[1] == "run"]

    def cli(self, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        env = {**self.env, **(extra_env or {})}
        return subprocess.run(
            [sys.executable, "-m", "collie", *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,  # a render that wrongly stays resident fails here instead of hanging
        )


@pytest.fixture
def herdr(tmp_path: Path) -> FakeHerdr:
    for fake in FAKES.iterdir():
        fake.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in {"COLLIE", "COLLIE_THEME"} and not k.startswith("HERDR")}
    env.update(
        PATH=f"{FAKES}{os.pathsep}{env['PATH']}",
        HOME=str(home),
        HERDR_ENV="1",
        HERDR_PANE_ID=CALLER,
        HERDR_TAB_ID=TAB,
        HERDR_WORKSPACE_ID="w1",
        FAKE_HERDR_STATE=str(tmp_path / "herdr-state.json"),
        FAKE_HERDR_LOG=str(tmp_path / "herdr-log.jsonl"),
        COLLIE_BUSY_GRACE_MS="600",
    )
    fake = FakeHerdr(tmp_path / "herdr-state.json", tmp_path / "herdr-log.jsonl", env)
    fake.set_panes({CALLER: {"tab_id": TAB, "cwd": str(tmp_path), "width": 128}})
    return fake


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    path = tmp_path / "example.py"
    path.write_text("".join(f"line_{i} = {i}\n" for i in range(1, 101)))
    return path


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    (repo / "a.py").write_text("x = 1\n")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "one"], check=True)
    (repo / "a.py").write_text("x = 2\n")
    return repo


RENDERER_LIKE = [sys.executable, "-c", "import time; time.sleep(30)", "-m", "collie", "render", "show", "/x"]
NOT_A_RENDERER = ["sleep", "30"]


@pytest.fixture
def processes():
    """Start real throwaway processes; every one is killed at teardown."""
    started: list[subprocess.Popen] = []

    def start(argv: list[str]) -> subprocess.Popen:
        proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        started.append(proc)
        time.sleep(0.2)  # let exec finish so `ps` shows the final command line
        return proc

    yield start
    for proc in started:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
