#!/usr/bin/env python3
"""youtube_ingest.py — YouTube adapter for the InfoTriage ingest-youtube container.

Produces DUAL output per channel run:
  1. Item (with content-addressed blob body_ref) → Postgres via store.put_item
     + "item.ingested" event → RabbitMQ bus (idempotent via persist_and_publish).
  2. data/feeds/youtube-<slug>.xml Atom feed → FreshRSS river-browsing (preserved
     from yt_to_atom.py; OUT_DIR bind-mounted by docker-compose Plan 06 stanza).

Transcription is FORCED to the stub path — real transcription requires macOS Metal
and is never available in the Linux container. The transcribe() function always
returns a stub string regardless of transcribe_wanted.

yt-dlp is invoked only via subprocess (read-only public-channel metadata; no audio
download). No YouTube credentials are required or accepted (ADR-004 / SPEC C-9).

Environment variables (production; monkeypatched in tests):
    YT_CHANNELS          — JSON array of channel config objects (required)
    INFOTRIAGE_PG_DSN    — PostgreSQL libpq connection string (required)
    INFOTRIAGE_AMQP_DSN  — AMQP URL for RabbitMQ (required; never logged)
    INFOTRIAGE_BLOB_ROOT — filesystem root for blob storage (default: data/blobs)
"""
import datetime
import json
import os
import re
import subprocess
import sys

from contracts import Item
from ingest_common import build_bus, build_store, persist_and_publish

from _util import escape

# Atom output directory (bind-mounted in the container; tests monkeypatch this).
OUT_DIR = os.path.join("data", "feeds")


# ---------------------------------------------------------------------------
# Channel helpers — faithfully copied from apps/ingest/yt_to_atom.py
# ---------------------------------------------------------------------------


def slug(s: str) -> str:
    """Normalize a string to a URL-safe slug (last 32 chars, lowercased)."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return (s or "untitled")[-32:] or "untitled"


def load_channels() -> list[dict]:
    """Load channel configs from YT_CHANNELS environment variable (JSON array).

    Raises SystemExit if YT_CHANNELS is not set (clean fail, not a traceback).
    """
    raw = os.environ.get("YT_CHANNELS", "").strip()
    if not raw:
        raise SystemExit("Set YT_CHANNELS (JSON) with the channel config list.")
    return json.loads(raw)


def yt_dlp_list(channel: str, max_n: int) -> list[tuple[str, str]]:
    """Return list of (video_id, title) via yt-dlp flat-playlist (no downloads).

    Uses yt-dlp in flat-playlist mode: fetches public-channel metadata only,
    no audio download, no YouTube credentials (ADR-004 / T-04-07).
    Returns [] on yt-dlp absence, subprocess timeout, or empty channel.
    """
    import shutil

    if not shutil.which("yt-dlp"):
        print(
            "yt-dlp not on PATH — install with pip install yt-dlp",
            file=sys.stderr,
        )
        return []
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print",
        "%(id)s|||%(title)s",
        "-I",
        f"1:{max_n}",
        channel,
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"yt-dlp timed out on {channel}", file=sys.stderr)
        return []
    return [
        tuple(line.split("|||", 1))
        for line in out.stdout.splitlines()
        if "|||" in line
    ]


def transcribe(video_id: str, transcribe_wanted: bool = False) -> str:
    """Stub transcription — always returns a stub string. No audio pipeline invoked.

    transcribe_wanted is accepted for API compatibility with yt_to_atom.py but
    is always treated as False in this container (real transcription requires
    macOS Metal; SPEC R2 constraint / CONTEXT specifics).
    """
    return (
        "(transcription disabled — stub mode only; "
        "real transcription requires Apple Silicon + a transcription backend)"
    )


def write_atom(name: str, entries: list[tuple[str, str, str]]) -> tuple[str, int]:
    """Write Atom XML for a YouTube channel to OUT_DIR/youtube-<slug>.xml.

    All XML-interpolated fields pass through escape() (T-04-06 mitigation).
    Creates OUT_DIR if absent. Returns (out_path, entry_count).
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"<title>InfoTriage · {name}</title>",
        f"<updated>{now}</updated>",
        f"<id>urn:infotriage:youtube:{slug(name)}</id>",
    ]
    for vid, title, text in entries:
        parts += [
            "<entry>",
            f"<title>{escape(title)}</title>",
            f"<id>urn:youtube:{vid}</id>",
            f'<link href="https://youtu.be/{vid}"/>',
            f"<updated>{now}</updated>",
            f"<summary>{escape(text)}</summary>",
            "</entry>",
        ]
    parts.append("</feed>")
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"youtube-{slug(name)}.xml")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out_path, len(entries)


# ---------------------------------------------------------------------------
# Main ingest coroutine
# ---------------------------------------------------------------------------


async def ingest() -> None:
    """Main ingest coroutine: dual output (Item+blob+bus AND Atom XML), idempotent.

    Called by the POST /run trigger via make_trigger_app (main.py).
    Per channel:
      - yt_dlp_list fetches video metadata (no audio, no credentials)
      - Each video's stub text is written to the content-addressed blob store
      - Item (with body_ref) is persisted and published (idempotent)
      - Atom XML is written to OUT_DIR (FreshRSS dual output)
    Empty channels (yt_dlp_list returns []) produce 0 items and 0 events cleanly.
    """
    channels = load_channels()
    store = build_store()
    bus = build_bus()

    try:
        with store:
            for c in channels:
                url = c["channel"]
                max_n = int(c.get("max_per_run", 3))
                name = c.get("name") or url.rstrip("/").split("/")[-1] or "channel"
                vids = yt_dlp_list(url, max_n)

                atom_entries: list[tuple[str, str, str]] = []
                for vid, title in vids:
                    # Stub transcription — no audio pipeline invoked (SPEC R2 constraint)
                    text = transcribe(vid, transcribe_wanted=False)

                    # Write transcript stub to content-addressed blob store (R2, D-01a)
                    body_ref = store.put_blob(text.encode("utf-8"))

                    item = Item(
                        source=name,
                        source_type="yt",
                        url=f"https://youtu.be/{vid}",
                        title=title,
                        ts=datetime.datetime.now(tz=datetime.timezone.utc),
                        lang="und",
                        summary=text[:500],
                        body_ref=body_ref,
                    )
                    await persist_and_publish(store, bus, item)
                    atom_entries.append((vid, title, text))

                # Dual output: write Atom XML (preserved for FreshRSS river-browsing)
                write_atom(name, atom_entries)
    finally:
        # RabbitMQBus has close(); InMemoryBus does not — guard for test compat
        close_fn = getattr(bus, "close", None)
        if callable(close_fn):
            await close_fn()
