#!/usr/bin/env python3
"""obsidian_ingest.py — Obsidian Web Clipper ingest adapter for InfoTriage.

Reads .md clips from $OBSIDIAN_VAULT_PATH/articles-inbox/, maps their YAML
frontmatter to Item via libs/contracts.from_frontmatter (D-08/D-09), and
persists + publishes via libs/ingest_common.persist_and_publish.

Field mapping (D-09):
    title       → Item.title       (fallback: "")
    url         → Item.url         (fallback: "")
    date        → Item.ts          (fallback: datetime.now(utc); naive → UTC)
    site        → Item.source      (fallback: "obsidian")
    description → Item.summary
    lang        → inferred from title: æ/ø/å → "no"; empty → "und"; else "en"
    source_type always "obsidian"

Security:
    - Vault files opened read-only only (no write/append modes) — T-04-09
    - from_frontmatter uses yaml.safe_load exclusively — T-04-08
    - No write, unlink, rename, or rmtree calls against the vault path
"""
import glob
import logging
import os
import re
from datetime import datetime, timezone

from contracts import Item, from_frontmatter
from ingest_common import build_bus, build_store, persist_and_publish

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Language inference (D-09)
# ---------------------------------------------------------------------------


def _infer_lang(text: str) -> str:
    """Infer language from title text per D-09.

    Returns:
        "no"  — text contains Norwegian characters (æ/ø/å, any case)
        "und" — text is empty or None (indeterminate)
        "en"  — otherwise
    """
    if not text:
        return "und"
    if re.search(r"[æøåÆØÅ]", text):
        return "no"
    return "en"


# ---------------------------------------------------------------------------
# Clip → Item (D-09 mapping)
# ---------------------------------------------------------------------------


def item_from_obsidian_clip(path: str) -> Item:
    """Read an Obsidian Web Clipper .md file and map its frontmatter to an Item.

    Opens the file read-only (never write/append). Parses frontmatter via
    from_frontmatter() (yaml.safe_load — T-04-08). Missing required fields
    (title, url, date) fall back to safe defaults per D-09; a WARNING is logged
    but the clip is NOT rejected.

    Args:
        path: Absolute or relative path to the .md clip file.

    Returns:
        Item with source_type="obsidian" and D-09-mapped fields.
    """
    # Read-only file access — T-04-09 (no write/append mode ever used here)
    text = open(path, "r", encoding="utf-8").read()  # noqa: WPS515

    try:
        fm = from_frontmatter(text)
    except ValueError:
        fm = {}
        log.warning("Obsidian clip %r has no YAML frontmatter delimiters; using empty dict", path)

    # --- required field extraction with fallback + warning ---
    title: str = fm.get("title") or ""
    url: str = fm.get("url") or ""
    source: str = fm.get("site") or "obsidian"
    summary = fm.get("description")

    if not title:
        log.warning("Obsidian clip %r missing 'title' frontmatter field; defaulting to ''", path)
    if not url:
        log.warning("Obsidian clip %r missing 'url' frontmatter field; defaulting to ''", path)

    # --- date → tz-aware ts ---
    date_raw = fm.get("date")
    if date_raw is None:
        ts = datetime.now(tz=timezone.utc)
        log.warning(
            "Obsidian clip %r missing 'date' frontmatter field; defaulting to utcnow()", path
        )
    elif isinstance(date_raw, datetime):
        # from_frontmatter may return naive datetime if no TZ offset in YAML
        ts = date_raw if date_raw.tzinfo is not None else date_raw.replace(tzinfo=timezone.utc)
    else:
        # Unexpected type (e.g. plain date object) — fall back to utcnow
        ts = datetime.now(tz=timezone.utc)
        log.warning(
            "Obsidian clip %r 'date' has unexpected type %s; defaulting to utcnow()",
            path,
            type(date_raw).__name__,
        )

    lang = _infer_lang(title)

    return Item(
        source=source,
        source_type="obsidian",
        url=url,
        title=title,
        ts=ts,
        lang=lang,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Directory scan
# ---------------------------------------------------------------------------


def fetch_items(inbox_dir: str) -> list[Item]:
    """Glob *.md files under inbox_dir and return a list of Items.

    The vault is read-only — no files are created, modified, or deleted.
    Parse errors for individual clips are logged at ERROR level and skipped;
    other clips in the directory are still processed.

    Args:
        inbox_dir: Path to the articles-inbox directory (already resolved).

    Returns:
        List of Items in filesystem order (sorted by path for determinism).
    """
    pattern = os.path.join(inbox_dir, "*.md")
    paths = sorted(glob.glob(pattern))
    items: list[Item] = []
    for path in paths:
        try:
            item = item_from_obsidian_clip(path)
            items.append(item)
        except Exception as exc:
            log.error("Failed to parse Obsidian clip %r: %s", path, exc)
    return items


# ---------------------------------------------------------------------------
# Ingest coroutine (entry point for make_trigger_app)
# ---------------------------------------------------------------------------


async def ingest() -> None:
    """Ingest all Obsidian Web Clipper clips from $OBSIDIAN_VAULT_PATH/articles-inbox/.

    Reads OBSIDIAN_VAULT_PATH from environment and appends 'articles-inbox'
    to locate the clip directory (RESEARCH Pitfall 4). Iterates clips via
    fetch_items(), persists and publishes each via persist_and_publish() (R6
    idempotency: no duplicate rows or extra bus events on re-run).

    Environment variables:
        OBSIDIAN_VAULT_PATH  — path to the Obsidian vault root (required)
        INFOTRIAGE_PG_DSN    — Postgres libpq DSN (required by build_store)
        INFOTRIAGE_AMQP_DSN  — AMQP URL for RabbitMQ (required by build_bus)
        INFOTRIAGE_BLOB_ROOT — blob storage root (optional; default data/blobs)
    """
    vault_path = os.environ["OBSIDIAN_VAULT_PATH"]
    inbox_dir = os.path.join(vault_path, "articles-inbox")

    items = fetch_items(inbox_dir)
    log.info("ingest-obsidian: found %d clip(s) in %s", len(items), inbox_dir)

    with build_store() as store:
        bus = build_bus()
        try:
            for item in items:
                is_new = await persist_and_publish(store, bus, item)
                log.debug(
                    "clip %r: %s",
                    item.url or item.title,
                    "new — published" if is_new else "duplicate — skipped",
                )
        finally:
            # RabbitMQBus requires explicit close; InMemoryBus is a no-op
            if hasattr(bus, "close"):
                await bus.close()
