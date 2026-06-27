#!/usr/bin/env python3
"""_codec.py — PyYAML frontmatter codec for InfoTriage.

Bridges Obsidian markdown YAML frontmatter and the Postgres JSONB payload.
Uses yaml.safe_load exclusively — the unsafe loader is never used (T-01-01).

Usage:
    from contracts import to_frontmatter, from_frontmatter

    text = to_frontmatter({"title": "Test", "ts": datetime.datetime.now(tz=utc)})
    # "---\ntitle: Test\n...\n---\n"

    payload = from_frontmatter(text)
    # {"title": "Test", "ts": datetime.datetime(...)}
"""
import yaml


def to_frontmatter(payload: dict) -> str:
    """Serialize payload dict to YAML frontmatter block (with --- delimiters).

    Preserves: tz-aware datetime (as YAML timestamp with UTC offset),
    Norwegian unicode, None→null, nested dicts/lists, [N] citation strings.
    Uses allow_unicode=True so Norwegian characters are not escaped.
    """
    body = yaml.safe_dump(payload, allow_unicode=True, default_flow_style=False)
    return f"---\n{body}---\n"


def from_frontmatter(text: str) -> dict:
    """Extract and parse YAML frontmatter from text, returning payload dict.

    Inverse of to_frontmatter. Datetime values are restored as datetime objects
    with UTC-offset tzinfo (ZoneInfo name is not preserved — acceptable per SPEC R3
    which requires no precision loss, not tzinfo type preservation).

    Raises ValueError if text contains no frontmatter delimiters (---).
    Returns {} if the frontmatter block is empty (valid YAML null).

    Delimiters are matched as whole lines (a leading '---' line and the next '---'
    line), so a '---' appearing inside a frontmatter VALUE does not split the block.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"No YAML frontmatter found in text: {text[:80]!r}")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":            # closing delimiter on its own line
            return yaml.safe_load("\n".join(lines[1:i])) or {}
    raise ValueError(f"Unterminated YAML frontmatter in text: {text[:80]!r}")
