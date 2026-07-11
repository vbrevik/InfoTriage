#!/usr/bin/env python3
"""vault_writer.py — Obsidian vault writer for Phase 6 (SC2, SC3).

Writes high-value enrichment items and the SAB to Obsidian .md files.

- Front-matter follows existing codec pattern from libs/contracts
- Body contains item summary + wikilinked entities
- Uses lightweight proper-noun extraction heuristic (no Phase 8 dependency)
"""
import os
import re
from pathlib import Path
from typing import Optional

from contracts import to_frontmatter

# Production email adapters signal email via the row's url scheme, not source:
# gmail rows carry url=gmail://..., imap rows carry url=imap://... while their
# source field holds the adapter/mailbox name (e.g. "gmail" or "Telegraph Ukraine").
_EMAIL_URL_SCHEMES = ("imap://", "gmail://")

# Simple heuristic for entity extraction - no external dependencies
# In Phase 8, this will be replaced by proper entity resolution
_SYSTEM_TOPICS = {
    "norge", "norsk", "norway", "norway", "oslo", "bergen", "tromsø", " stavanger", " trondheim",
    "nato", "natos hq", "norwegian defense", "norwegian armed forces", "forsvaret",
    "ukraine", "russia", " putin", " zelensky", " warsaw", " poland", " belarus",
    "china", "beijing", " taiwan", " hong kong", " diplomatic",
    "america", "usa", "united states", "washington", "clearly",
    "climate", "environment", "green", "sustainable", "renewable",
    "technology", "ai", "artificial intelligence", "cybersecurity", "security",
    "ukrainian", "russian", "chinese", "american", "european",
}


def extract_entities(text: str, known_topics: Optional[list[str]] = None) -> list[str]:
    """Extract entities from text using simple heuristics.

    This is a placeholder until Phase 8 provides proper entity resolution.
    It uses known topic matching and simple capitalization heuristics.

    Args:
        text: Text to extract entities from
        known_topics: Optional list of known topics to match

    Returns:
        List of unique extracted entities
    """
    entities = set()

    text_lower = text.lower()

    if known_topics:
        for topic in known_topics:
            if topic.lower() in text_lower:
                entities.add(topic)
    else:
        for topic in _SYSTEM_TOPICS:
            if topic in text_lower:
                entities.add(topic.title())

    words = text.split()
    for word in words:
        clean_word = re.sub(r'^[^A-Za-z]+|[^A-Za-z]+$', '', word)
        if clean_word and clean_word[0].isupper() and len(clean_word) >= 2:
            if clean_word not in {"This", "That", "It", "There", "Where", "When", "Why", "How"}:
                entities.add(clean_word)

    return list(sorted(entities))


def render_wikilinked(text: str, entities: list[str]) -> str:
    """Replace entities with [[Entity]] wikilinks.

    Args:
        text: Text to transform
        entities: List of entities to replace with wikilinks

    Returns:
        Wikilinked text with markdown links
    """
    result = text
    for entity in entities:
        # Escape special regex characters in entity
        escaped_entity = re.escape(entity)
        # Replace with wikilink
        result = result.replace(entity, f"[[{entity}]]")
    return result


def write_item_obsidian(item: dict, vault_path: Path) -> Path:
    """Write a single enrichment item to an Obsidian .md file.

    Args:
        item: Enrichment row dict with fields: item_id, title, summary, source, url,
              ts, ccir, cnr, score, bucket, why, pmesii, tessoc, embedding
        vault_path: Directory path where the vault lives

    Returns:
        Path to the written file
    """
    vault_path.mkdir(parents=True, exist_ok=True)

    # Use simple item_id or slug for filename
    item_id = item.get("item_id", "unknown")
    # Sanitize filename: remove special characters
    safe_id = re.sub(r'[^\w\-]', '', str(item_id))
    filename = f"{safe_id}.md"
    filepath = vault_path / filename

    # Extract entities from summary and why
    summary = (item.get("summary") or "")
    why = (item.get("why") or "")
    all_text = f"{summary}. {why}"
    entities = extract_entities(all_text)

    # Render entities in summary and why with wikilinks
    summary_wikilinked = render_wikilinked(summary, entities)
    why_wikilinked = render_wikilinked(why, entities)

    frontmatter = to_frontmatter({
        "title": item.get("title", ""),
        "date": item.get("ts", ""),
        "ccir": item.get("ccir", ""),
        "score": item.get("score", 0),
        "cnr": item.get("cnr", ""),
        "bucket": item.get("bucket", ""),
        "source": item.get("source", ""),
        "url": item.get("url", ""),
        "item_id": item.get("item_id", ""),
    })
    file_content = f"""{frontmatter}

## Summary
{summary_wikilinked}

## Source
{item.get('source', '')} — [les]({item.get('url', '')})

## Why
{why_wikilinked}

## Entities
{', '.join(entities) if entities else '(ingen oppdaget)'}

"""

    # Write atomically using .tmp + os.replace pattern
    tmp_path = filepath.with_suffix(".tmp")
    tmp_path.write_text(file_content, encoding="utf-8")
    os.replace(tmp_path, filepath)

    return filepath


def render_sab_obsidian(enrichment_rows: list[dict]) -> str:
    """Render the Obsidian SAB projection markdown for the given rows.

    Args:
        enrichment_rows: List of enrichment row dicts

    Returns:
        Markdown string
    """
    # Group items by CCIR
    by_ccir = {}
    for r in enrichment_rows:
        ccir = (r.get("ccir") or "none").upper()
        by_ccir.setdefault(ccir, []).append(r)

    # Build the document
    lines = ["# InfoTriage · Obsidian SAB", f"\n{len(enrichment_rows)} saker\n"]

    for ccir, items in by_ccir.items():
        lines.append(f"## {ccir}")

        # Sort by score descending
        sorted_items = sorted(items, key=lambda x: -x.get("score", 0))[:20]

        for item in sorted_items[:10]:
            summary = item.get("summary", "")

            # Extract entities and render wikilinks
            why = item.get("why", "")
            all_text = f"{summary}. {why}"
            entities = extract_entities(all_text)
            summary_wikilinked = render_wikilinked(summary, entities)

            lines.append(f"- **[{item.get('score', 0)}] {item.get('title', '')}**")
            lines.append(f"  - {summary_wikilinked}")
            lines.append(f"  - {item.get('source', '')} — [les]({item.get('url', '')})")
            if entities:
                lines.append(f"  - **Emner**: {', '.join(entities)}")
            lines.append("")

    return "\n".join(lines)


def write_sab_obsidian(
    enrichment_rows: list[dict],
    vault_path: Path,
    *,
    filename: str = "obsidian-sab.md",
) -> Path:
    """Write a projection of the SAB (or summary) to Obsidian.

    Args:
        enrichment_rows: List of enrichment row dicts
        vault_path: Directory path where the vault lives
        filename: Optional filename for the SAB projection (default: obsidian-sab.md)

    Returns:
        Path to the written file
    """
    vault_path.mkdir(parents=True, exist_ok=True)
    filepath = vault_path / filename

    file_content = render_sab_obsidian(enrichment_rows)
    tmp_path = filepath.with_suffix(".tmp")
    tmp_path.write_text(file_content, encoding="utf-8")
    os.replace(tmp_path, filepath)

    return filepath


def write_vault_digest(
    enrichment_rows: list[dict],
    vault_path: Optional[Path] = None,
    *,
    write_items: bool = True,
    sab_filename: str = "obsidian-sab.md",
) -> list[Path]:
    """Write all high-extraction items to the vault.

    Args:
        enrichment_rows: List of enrichment row dicts
        vault_path: Directory path (defaults to ENV var INFOTRIAGE_VAULT_PATH, "data/obsidian")
        write_items: Whether to write individual item files (default: True)
        sab_filename: Optional filename for the SAB projection (default: obsidian-sab.md)

    Returns:
        List of paths to written files
    """
    if vault_path is None:
        vault_path = Path(os.environ.get("INFOTRIAGE_VAULT_PATH", "data/obsidian"))

    # Include email-sourced items if VAULT_INCLUDE_EMAIL=1
    include_email = os.environ.get("VAULT_INCLUDE_EMAIL", "1") == "1"

    # Filter: items with score >= 8, or all items with CCIR (but not none)
    kept = [
        r for r in enrichment_rows
        if r.get("score", 0) >= 8
        or (r.get("ccir") or "none").lower() != "none"
    ]

    # Exclude email items if VAULT_INCLUDE_EMAIL=0. The url scheme is the
    # reliable email signal (see _EMAIL_URL_SCHEMES comment above); web-clip/
    # RSS/YouTube rows keep their http(s)/other schemes and are unaffected.
    if not include_email:
        kept = [r for r in kept if not (r.get("url") or "").startswith(_EMAIL_URL_SCHEMES)]

    paths: list[Path] = []

    # Write individual items only once (default view)
    if write_items:
        for item in kept:
            try:
                path = write_item_obsidian(item, vault_path)
                paths.append(path)
            except Exception as e:
                print(f"Error writing item {item.get('item_id')}: {e}", flush=True)

    # Write SAB projection
    write_sab_obsidian(kept, vault_path, filename=sab_filename)
    paths.append(vault_path / sab_filename)

    return paths
