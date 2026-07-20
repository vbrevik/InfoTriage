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


def extract_entities(text: str, known_topics: Optional[list[str]] = None) -> list[str]:
    """DEPRECATED: use the entity graph (item['entities']) instead.

    Kept for backward compatibility with callers that imported this helper.
    It now returns the intersection of ``known_topics`` with the text, or an
    empty list when no topics are supplied.
    """
    import warnings

    warnings.warn(
        "extract_entities() is deprecated; use the entity graph via item['entities']",
        DeprecationWarning,
        stacklevel=2,
    )
    if not known_topics:
        return []
    text_lower = (text or "").lower()
    return [t for t in known_topics if t.lower() in text_lower]


def _entity_names(item: dict) -> list[str]:
    """Return canonical entity names from the item's entity graph links.

    Phase 8 populates each enrichment row with an list of entity-link dicts under
    the ``entities`` key (e.g. ``[{"name": "NATO", "mention": "NATO", ...}]``).
    The vault writer no longer extracts entities heuristically; it projects the
    canonical graph stored by the triage worker.
    """
    return [e["name"] for e in item.get("entities", []) if e.get("name")]


def render_wikilinked(text: str, entities: list[str]) -> str:
    """Replace entities with [[Entity]] wikilinks.

    Args:
        text: Text to transform
        entities: List of entities to replace with wikilinks

    Returns:
        Wikilinked text with markdown links
    """
    result = text
    # Longest-first so prefix entities ("Ukraine") don't corrupt longer forms
    # ("Ukrainian"); word boundaries + lookarounds skip text already wikilinked.
    for entity in sorted(entities, key=len, reverse=True):
        pattern = r"(?<!\[)\b" + re.escape(entity) + r"\b(?!\])"
        result = re.sub(pattern, f"[[{entity}]]", result)
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
    safe_id = re.sub(r"[^\w\-]", "", str(item_id))
    filename = f"{safe_id}.md"
    filepath = vault_path / filename

    # Project canonical entities from the entity graph (Phase 8).
    summary = item.get("summary") or ""
    why = item.get("why") or ""
    entities = _entity_names(item)

    # Render entities in summary and why with wikilinks
    summary_wikilinked = render_wikilinked(summary, entities)
    why_wikilinked = render_wikilinked(why, entities)

    frontmatter = to_frontmatter(
        {
            "title": item.get("title", ""),
            "date": item.get("ts", ""),
            "ccir": item.get("ccir", ""),
            "score": item.get("score", 0),
            "cnr": item.get("cnr", ""),
            "bucket": item.get("bucket", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "item_id": item.get("item_id", ""),
        }
    )
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
    by_ccir: dict[str, list[dict]] = {}
    for r in enrichment_rows:
        ccir = (r.get("ccir") or "none").upper()
        by_ccir.setdefault(ccir, []).append(r)

    # Build the document
    lines = ["# InfoTriage · Obsidian SAB", f"\n{len(enrichment_rows)} saker\n"]

    for ccir, items in by_ccir.items():
        lines.append(f"## {ccir}")

        # Sort by score descending
        sorted_items = sorted(items, key=lambda x: -(x.get("score") or 0))[:20]

        for item in sorted_items[:10]:
            summary = item.get("summary", "")

            # Project canonical entities from the entity graph (Phase 8).
            entities = _entity_names(item)
            summary_wikilinked = render_wikilinked(summary, entities)

            lines.append(f"- **[{item.get('score') or 0}] {item.get('title', '')}**")
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


def render_entity_graph(items: list[dict]) -> str:
    """Render the Entity Graph note from the digested items' entity links.

    Aggregates each item's ``entities`` links (``{name, mention, lang}``, as
    projected onto rows by ``consumer._attach_entities``) into one section per
    canonical entity, listing its language-tagged aliases and the number of
    linked items. Uses only data already on the rows, so it needs no extra
    store queries.
    """
    graph: dict[str, dict] = {}
    for item in items:
        item_id = item.get("item_id")
        for e in item.get("entities", []):
            name = e.get("name")
            if not name:
                continue
            node = graph.setdefault(name, {"aliases": set(), "items": set()})
            mention = e.get("mention")
            lang = e.get("lang") or "?"
            if mention:
                node["aliases"].add((mention, lang))
            if item_id is not None:
                node["items"].add(item_id)

    lines = ["# Entity Graph", ""]
    if not graph:
        lines.append("_No entities linked yet._")
        lines.append("")
    for name in sorted(graph):
        node = graph[name]
        aliases = sorted(f"{mention} ({lang})" for mention, lang in node["aliases"])
        lines.append(f"## {name}")
        lines.append(f"- Aliases: {', '.join(aliases) if aliases else '—'}")
        lines.append(f"- Linked items: {len(node['items'])}")
        lines.append("")
    return "\n".join(lines)


def write_entity_graph(
    items: list[dict],
    vault_path: Path,
    *,
    filename: str = "Entity Graph.md",
) -> Path:
    """Write the aggregated Entity Graph note to the vault (atomic replace)."""
    vault_path.mkdir(parents=True, exist_ok=True)
    filepath = vault_path / filename

    content = render_entity_graph(items)
    tmp_path = filepath.with_suffix(".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, filepath)

    return filepath


def render_entity_graph_from_store(entities: list[dict]) -> str:
    """Render the Entity Graph note from Store.get_all_entities() rows.

    Each row is expected to have: id, name, lang, type, alias_count, link_count.
    Aliases are not stored per entity in the current aggregation; the note lists
    canonical entities grouped by link_count with available language/type tags.
    """
    lines = ["# Entity Graph", ""]
    if not entities:
        lines.append("_No entities linked yet._")
        lines.append("")
        return "\n".join(lines)

    for entity in entities:
        name = entity["name"]
        lang = entity.get("lang") or "?"
        etype = entity.get("type") or "MISC"
        alias_count = entity.get("alias_count", 0)
        link_count = entity.get("link_count", 0)
        lines.append(f"## {name}")
        lines.append(f"- **Type:** {etype} · **Lang:** {lang}")
        lines.append(f"- **Aliases:** {alias_count}")
        lines.append(f"- **Linked items:** {link_count}")
        lines.append("")
    return "\n".join(lines)


def write_entity_graph_from_store(
    store,
    vault_path: Path,
    *,
    filename: str = "Entity Graph.md",
) -> Path:
    """Write the aggregated Entity Graph note using canonical store data.

    Queries Store.get_all_entities() so the graph is built from the Postgres
    system of record, not from the in-row entity projection.
    """
    vault_path.mkdir(parents=True, exist_ok=True)
    filepath = vault_path / filename

    entities = store.get_all_entities()
    content = render_entity_graph_from_store(entities)
    tmp_path = filepath.with_suffix(".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, filepath)

    return filepath


def write_vault_digest(
    enrichment_rows: list[dict],
    vault_path: Optional[Path] = None,
    *,
    write_items: bool = True,
    sab_filename: str = "obsidian-sab.md",
    store=None,
) -> list[Path]:
    """Write all high-extraction items to the vault.

    Args:
        enrichment_rows: List of enrichment row dicts
        vault_path: Directory path (defaults to ENV var INFOTRIAGE_VAULT_PATH, "data/obsidian")
        write_items: Whether to write individual item files (default: True)
        sab_filename: Optional filename for the SAB projection (default: obsidian-sab.md)
        store: Optional Store instance. When provided, the Entity Graph.md is
               generated by querying the store directly via get_all_entities().

    Returns:
        List of paths to written files
    """
    if vault_path is None:
        vault_path = Path(os.environ.get("INFOTRIAGE_VAULT_PATH", "data/obsidian"))

    # Include email-sourced items unless VAULT_INCLUDE_EMAIL is explicitly falsy
    # (accepts common truthy strings like "true"/"yes" without inverting intent)
    include_email = os.environ.get("VAULT_INCLUDE_EMAIL", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )

    # Filter: items with score >= 8, or all items with CCIR (but not none)
    kept = [
        r
        for r in enrichment_rows
        if (r.get("score") or 0) >= 8 or (r.get("ccir") or "none").lower() != "none"
    ]

    # Exclude email items if VAULT_INCLUDE_EMAIL=0. The url scheme is the
    # reliable email signal (see _EMAIL_URL_SCHEMES comment above); web-clip/
    # RSS/YouTube rows keep their http(s)/other schemes and are unaffected.
    if not include_email:
        kept = [
            r for r in kept if not (r.get("url") or "").startswith(_EMAIL_URL_SCHEMES)
        ]

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

    # Write the aggregated entity graph note. Prefer the store-backed graph
    # when a Store instance is available (Phase 8 Wave 5 — Postgres truth).
    if store is not None:
        paths.append(write_entity_graph_from_store(store, vault_path))
    else:
        paths.append(write_entity_graph(kept, vault_path))

    return paths
