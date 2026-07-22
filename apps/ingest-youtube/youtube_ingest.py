#!/usr/bin/env python3
"""youtube_ingest.py — YouTube adapter for the InfoTriage ingest-youtube container.

Produces DUAL output per channel run:
  1. Item (with content-addressed blob body_ref) → Postgres via store.put_item
     + "item.ingested" event → RabbitMQ bus (idempotent via persist_and_publish).
  2. data/feeds/youtube-<slug>.xml Atom feed → FreshRSS river-browsing (preserved
     from yt_to_atom.py; OUT_DIR bind-mounted by docker-compose Plan 06 stanza).

Transcription is opt-in. When a channel config sets ``transcribe: true`` (or the
``INFOTRIAGE_YOUTUBE_TRANSCRIBE`` environment variable is set to ``1``/``true``),
the adapter downloads the audio track with yt-dlp and transcribes it locally using
``faster-whisper`` (CPU, int8). On any failure the function falls back to a stub
message, so ingestion is never blocked. Real transcription requires ``ffmpeg``
and the faster-whisper model files.

yt-dlp is invoked only via subprocess (read-only public-channel metadata; no audio
download). No YouTube credentials are required or accepted (ADR-004 / SPEC C-9).

Environment variables (production; monkeypatched in tests):
    YT_CHANNELS                         — JSON array of channel config objects (required)
    INFOTRIAGE_PG_DSN                   — PostgreSQL libpq connection string (required)
    INFOTRIAGE_AMQP_DSN                 — AMQP URL for RabbitMQ (required; never logged)
    INFOTRIAGE_BLOB_ROOT                — filesystem root for blob storage (default: data/blobs)
    INFOTRIAGE_YOUTUBE_TRANSCRIBE       — global enable flag (1/true/yes)
    INFOTRIAGE_WHISPER_MODEL            — faster-whisper model name (default: tiny)
"""

import asyncio
import datetime
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any, cast

from contracts import Item
from ingest_common import build_bus, build_store, persist_and_publish

from _util import escape

# Logger for structured diagnostics from the ingest-youtube adapter.
logger = logging.getLogger("ingest-youtube")

# Atom output directory (bind-mounted in the container; tests monkeypatch this).
OUT_DIR = os.path.join("data", "feeds")

# Global transcription model name. Per-channel "transcribe" key in YT_CHANNELS wins.
_WHISPER_MODEL_LOCK = threading.Lock()


def _whisper_model() -> str:
    """Return the configured faster-whisper model name.

    Read at call time so tests and container restarts pick up env changes.
    """
    return os.environ.get("INFOTRIAGE_WHISPER_MODEL", "tiny")


def _transcribe_default() -> bool:
    """Return the global transcription enable flag from the environment.

    Kept as a function so tests can monkeypatch ``os.environ`` and the
    adapter sees the change at runtime (avoids import-time env capture).
    """
    return os.environ.get("INFOTRIAGE_YOUTUBE_TRANSCRIBE", "").lower() in (
        "1",
        "true",
        "yes",
    )


# Module-level cache for faster-whisper models keyed by model name.
# This avoids re-loading the model on every video in a run.
_WHISPER_MODELS: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Channel helpers — faithfully copied from apps/ingest/yt_to_atom.py
# ---------------------------------------------------------------------------


def slug(s: str) -> str:
    """Normalize a string to a URL-safe slug (last 32 chars, lowercased)."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return (s or "untitled")[-32:] or "untitled"


def load_channels() -> list[dict[str, Any]]:
    """Load channel configs from YT_CHANNELS environment variable (JSON array).

    Raises SystemExit if YT_CHANNELS is not set (clean fail, not a traceback).
    """
    raw = os.environ.get("YT_CHANNELS", "").strip()
    if not raw:
        raise SystemExit("Set YT_CHANNELS (JSON) with the channel config list.")
    return cast(list[dict[str, Any]], json.loads(raw))


_TAB_SUFFIXES = ("/videos", "/shorts", "/streams", "/playlists")


def _videos_tab_url(channel: str) -> str:
    """Pin a bare channel URL to its Videos tab.

    A channel-root URL (e.g. https://www.youtube.com/@NATO) is expanded by
    yt-dlp into up to three tab playlists (Videos, Shorts, Live), and
    `-I 1:N` applies PER TAB — so a limit of 3 returned up to 9 entries.
    Appending /videos restricts the listing to the Videos tab only.
    URLs that already name a tab are left untouched.
    """
    base = channel.rstrip("/")
    if base.endswith(_TAB_SUFFIXES):
        return base
    return base + "/videos"


def yt_dlp_list(channel: str, max_n: int) -> list[tuple[str, str]]:
    """Return list of (video_id, title) via yt-dlp flat-playlist (no downloads).

    Uses yt-dlp in flat-playlist mode: fetches public-channel metadata only,
    no audio download, no YouTube credentials (ADR-004 / T-04-07).
    Returns [] on yt-dlp absence, subprocess timeout, or empty channel.
    yt-dlp failures (non-zero exit) are reported to stderr, not swallowed.
    """
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
        _videos_tab_url(channel),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"yt-dlp timed out on {channel}", file=sys.stderr)
        return []
    if out.returncode != 0:
        tail = out.stderr.strip().splitlines()[-3:]
        print(
            f"yt-dlp failed on {channel} (exit {out.returncode}): " + " / ".join(tail),
            file=sys.stderr,
        )
    return [
        (line.split("|||", 1)[0], line.split("|||", 1)[1])
        for line in out.stdout.splitlines()
        if "|||" in line
    ]


def _download_audio(video_id: str) -> tuple[str, str] | None:
    """Download the audio track for a YouTube video to a temporary directory.

    Uses yt-dlp in extract-audio mode (no video download, no credentials).
    Returns ``(tmpdir, audio_path)`` on success. The caller is responsible for
    deleting ``tmpdir``. Returns ``None`` if yt-dlp is missing, the download
    times out, or the audio file is not produced.
    """
    if not shutil.which("yt-dlp"):
        logger.warning("yt-dlp not on PATH; cannot download audio for %s", video_id)
        return None

    tmp_dir = tempfile.mkdtemp(prefix="infotriage-yt-audio-")
    audio_path = os.path.join(tmp_dir, f"{video_id}.mp3")
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "-o",
        audio_path,
        f"https://youtu.be/{video_id}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp audio download timed out for %s", video_id)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    if result.returncode != 0 or not os.path.exists(audio_path):
        logger.warning(
            "yt-dlp audio download failed for %s (exit %s): %s",
            video_id,
            result.returncode,
            result.stderr.decode(errors="ignore")[-200:],
        )
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    return tmp_dir, audio_path


def _transcribe_audio(audio_path: str, model_name: str = "tiny") -> str | None:
    """Transcribe an audio file using a local faster-whisper model.

    The model is loaded once per process and cached by ``model_name``.
    Returns the transcribed text, or ``None`` if faster-whisper is unavailable
    or transcription fails.
    """
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        logger.warning("faster-whisper not available: %s", exc)
        return None

    try:
        with _WHISPER_MODEL_LOCK:
            model = _WHISPER_MODELS.get(model_name)
            if model is None:
                model = WhisperModel(model_name, device="cpu", compute_type="int8")
                _WHISPER_MODELS[model_name] = model
        segments, _ = model.transcribe(audio_path, beam_size=5)
        text = " ".join(segment.text for segment in segments).strip()
        return text or None
    except Exception as exc:
        logger.warning("faster-whisper transcription failed: %s", exc)
        return None


def transcribe(video_id: str, transcribe_wanted: bool = False) -> str:
    """Return a transcript for ``video_id``.

    When ``transcribe_wanted`` is true, the audio track is downloaded with
    yt-dlp and transcribed locally with faster-whisper. On any failure the
    function returns a stub/fallback string so that ingestion is not blocked.
    """
    if not transcribe_wanted:
        return (
            "(transcription disabled — set transcribe:true to enable; "
            "install faster-whisper and ffmpeg)"
        )

    tmp_dir = None
    try:
        result = _download_audio(video_id)
        if result is None:
            return "(transcription failed — could not download audio)"
        tmp_dir, audio_path = result

        text = _transcribe_audio(audio_path, model_name=_whisper_model())
        if text:
            return text
        return "(transcription produced no output)"
    except Exception as exc:
        logger.warning("transcription failed for %s: %s", video_id, exc)
        return "(transcription failed — see logs)"
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


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
                max_n = int(c.get("max_n", 3))
                name = c.get("name") or url.rstrip("/").split("/")[-1] or "channel"
                transcribe_wanted = bool(c.get("transcribe", _transcribe_default()))
                vids = yt_dlp_list(url, max_n)

                atom_entries: list[tuple[str, str, str]] = []
                for vid, title in vids:
                    # Local-only transcription is opt-in (ADR-004).
                    # Run the heavy download/STT work off the event loop so the
                    # FastAPI trigger stays responsive for long videos.
                    text = await asyncio.to_thread(
                        transcribe, vid, transcribe_wanted=transcribe_wanted
                    )

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
