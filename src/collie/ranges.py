"""Excerpt syntax: PATH[:N-M][@H[-H][,H[-H]...]]."""

import re
from dataclasses import dataclass
from pathlib import Path

_RANGE = re.compile(r"[0-9]+(?:-[0-9]+)?")


def parse_range(text: str) -> tuple[int, int]:
    """Parse `N` or `N-M` (ASCII digits, 1 based, N <= M) into `(start, end)`."""
    if not _RANGE.fullmatch(text):
        raise ValueError(f"invalid line range {text!r}; expected N or N-M")
    first, _, last = text.partition("-")
    start = int(first)
    end = int(last) if last else start
    if start < 1:
        raise ValueError(f"invalid line range {text!r}; lines start at 1")
    if end < start:
        raise ValueError(f"invalid line range {text!r}; start is after end")
    return start, end


@dataclass(frozen=True)
class Excerpt:
    path: Path
    lines: tuple[int, int] | None
    highlights: tuple[tuple[int, int], ...]

    def spec(self) -> str:
        text = str(self.path)
        if self.lines is not None:
            text += f":{self.lines[0]}-{self.lines[1]}"
        if self.highlights:
            text += "@" + ",".join(f"{a}-{b}" for a, b in self.highlights)
        return text

    def subject(self) -> str:
        if self.lines is None:
            return self.path.name
        return f"{self.path.name}:{self.lines[0]}-{self.lines[1]}"


def parse_excerpt(text: str) -> Excerpt:
    """Split `@` off the right first, then a range-shaped `:` suffix, so paths may contain colons."""
    body, highlight_text = text, None
    at = text.rfind("@")
    if at != -1:
        body, highlight_text = text[:at], text[at + 1 :]

    lines = None
    head, sep, tail = body.rpartition(":")
    if sep and _RANGE.fullmatch(tail):
        lines = parse_range(tail)
        body = head
    if not body:
        raise ValueError(f"empty path in {text!r}")

    highlights: tuple[tuple[int, int], ...] = ()
    if highlight_text is not None:
        if not highlight_text:
            raise ValueError(f"empty highlight list in {text!r}")
        parsed = tuple(parse_range(part) for part in highlight_text.split(","))
        if lines is not None and any(a < lines[0] or b > lines[1] for a, b in parsed):
            raise ValueError(f"highlight outside lines {lines[0]}-{lines[1]} in {text!r}")
        highlights = parsed
    return Excerpt(Path(body), lines, highlights)


def find_match(lines: list[str], text: str) -> tuple[int, int] | None:
    """First 1 based line containing `text` (literal substring) and how many lines contain it."""
    hits = [number for number, line in enumerate(lines, start=1) if text in line]
    if not hits:
        return None
    return hits[0], len(hits)
