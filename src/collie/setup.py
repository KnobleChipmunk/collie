"""One time, per machine: link the skill, add the rule to AGENTS.md, add the SessionStart hook."""

import copy
import json
import shutil
from datetime import datetime
from importlib import resources
from pathlib import Path

BLOCK_BEGIN = "<!-- collie:begin -->"
BLOCK_END = "<!-- collie:end -->"
HOOK_COMMAND = "collie rule"


def rule_text() -> str:
    return resources.files("collie").joinpath("rule.md").read_text(encoding="utf-8").strip()


def skill_dir() -> Path:
    return Path(str(resources.files("collie").joinpath("skill")))


def upsert_block(text: str, body: str) -> str:
    block = f"{BLOCK_BEGIN}\n{body.strip()}\n{BLOCK_END}"
    begin = text.find(BLOCK_BEGIN)
    if begin != -1:
        end = text.find(BLOCK_END, begin)
        if end == -1:
            raise ValueError(f"{BLOCK_BEGIN} without {BLOCK_END}; fix the file and rerun")
        return text[:begin] + block + text[end + len(BLOCK_END) :]
    if not text.strip():
        return block + "\n"
    return text.rstrip("\n") + "\n\n" + block + "\n"


def ensure_hook(settings: dict) -> tuple[dict, bool]:
    result = copy.deepcopy(settings)
    hooks = result.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise TypeError("settings.json hooks is not an object")
    entries = hooks.setdefault("SessionStart", [])
    if not isinstance(entries, list):
        raise TypeError("settings.json hooks.SessionStart is not a list")
    for entry in entries:
        for hook in entry.get("hooks", []) if isinstance(entry, dict) else []:
            if isinstance(hook, dict) and hook.get("command") == HOOK_COMMAND:
                return settings, False
    entries.append({"matcher": "", "hooks": [{"type": "command", "command": HOOK_COMMAND}]})
    return result, True


def _line(dry_run: bool, action: str, detail: str, changed: bool) -> str:
    return f"{'would ' if dry_run else ''}{action} {detail}" + ("" if changed else " unchanged")


def _setup_link(dry_run: bool) -> str:
    link = Path.home() / ".claude" / "skills" / "collie"
    target = skill_dir()
    detail = f"{link} -> {target}"
    if link.is_symlink() and link.resolve() == target.resolve():
        return _line(dry_run, "link", detail, False)
    if link.exists() and not link.is_symlink():
        return f"link {link} exists and is not a symlink; left alone"
    if not dry_run:
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            link.unlink()
        link.symlink_to(target, target_is_directory=True)
    return _line(dry_run, "link", detail, True)


def _setup_block(dry_run: bool) -> str:
    path = Path.home() / ".agents" / "AGENTS.md"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = upsert_block(current, rule_text())
    changed = updated != current
    if changed and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
    return _line(dry_run, "block", str(path), changed)


def _backup(path: Path) -> Path:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak.{stamp}")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak.{stamp}-{counter}")
        counter += 1
    shutil.copy2(path, backup)
    return backup


def _setup_hook(dry_run: bool) -> str:
    path = Path.home() / ".claude" / "settings.json"
    existed = path.exists()
    try:
        current = json.loads(path.read_text(encoding="utf-8")) if existed else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON ({exc}); fix it and rerun") from exc
    if not isinstance(current, dict):
        raise TypeError(f"{path} is not a JSON object")
    updated, changed = ensure_hook(current)
    if changed and not dry_run:
        if existed:
            _backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return _line(dry_run, "hook", str(path), changed)


def run_setup(dry_run: bool) -> list[str]:
    return [_setup_link(dry_run), _setup_block(dry_run), _setup_hook(dry_run)]
