#!/usr/bin/env python3
"""InfoTriage bridge · YouTube channels -> local Atom feed with transcripts.

Per channel: yt-dlp fetches the latest N uploads → audio (.m4a) → mlx-whisper
(Apple Silicon) or `whisper` fallback transcription → Atom entry written to
../data/feeds/youtube-<slug>.xml (slug = lowercased, hyphenated, **last 32 chars
of the name**) which FreshRSS subscribes to at http://feeds/youtube-<slug>.xml.

The script is read-only of the YouTube channel. It does not require YouTube
credentials — yt-dlp fetches public-channel metadata and audio directly.
Output is local Atom, no third-party publication.

Configuration (YT_CHANNELS env JSON, or sibling .yt_channels.json):
    [{"channel": "https://www.youtube.com/@example",
      "max_per_run": 3,
      "transcribe": true,
      "name": "Example"}, ...]
    - name: optional, default derived from URL.
    - transcribe: true runs the audio-to-text pipeline. Setting false emits
      a stub summary so the wiring can be validated before MLX/whisper is set up.

Dependencies (operator-side install; not auto-installed):
    pipx install yt-dlp            # or: brew install yt-dlp
    pip install mlx-whisper         # Apple Silicon (M1/M2/M3/M4)
       — OR —
    pip install openai-whisper     # cross-platform, slower on Mac

If neither is installed, the "transcribe":false mode is enough to validate
the wiring; treat real ingestion as a follow-up.

Notes:
- **Slug-collision caveat:** per-channel output filename is `data/feeds/youtube-<slug>.xml`. Two names collide when their slugs match — this includes (a) names that normalize to the same string after lowercasing/hyphenation (e.g., `news-ru` / `news_ru` / `news ru` → `news-ru`), and (b) names whose **last 32 characters** match (the slug is truncated to the trailing 32 chars). Disambiguate via the explicit `name` field in `YT_CHANNELS`.
- **YT_CHANNELS (as a JSON array starting with `[`) is not loaded from `.env`** — the loader only handles `KEY=VALUE` lines and skips anything that doesn't fit. Set via shell `export YT_CHANNELS='[…]'` or write `.yt_channels.json`.
- **Read-only of channels.** yt-dlp fetches public metadata and audio; no YouTube credentials are required. **DO NOT** add a YouTube account to `.env` — none is needed, and storing one risks leaks with no upside.
- **Apple Silicon first.** `mlx_whisper` is the primary runner; `whisper` is the cross-platform fallback. With `transcribe: false`, the script emits a stub summary and the pipeline is wired without any MLX/whisper install.
"""
import os, sys, json, shutil, subprocess, tempfile, datetime, re
from _util import escape

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "data", "feeds")

def slug(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return (s or "untitled")[-32:] or "untitled"

def load_dotenv(path):
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line and not line.startswith("["):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def load_channels():
    raw = os.environ.get("YT_CHANNELS", "").strip()
    if not raw:
        alt = os.path.join(ROOT, ".yt_channels.json")
        if os.path.exists(alt):
            raw = open(alt).read().strip()
    if not raw:
        raise SystemExit("Set YT_CHANNELS (JSON) or write .yt_channels.json with the list.")
    return json.loads(raw)

def which(cmd):
    """Return path to executable or None."""
    return shutil.which(cmd)

def yt_dlp_list(channel, max_n):
    """Return list of (video_id, title) — uses yt-dlp flat-playlist (no downloads)."""
    if not which("yt-dlp"):
        print("yt-dlp not on PATH — install with `brew install yt-dlp` or `pipx install yt-dlp`.",
              file=sys.stderr)
        return []
    cmd = ["yt-dlp", "--flat-playlist", "--print", "%(id)s|||%(title)s",
           "-I", f"1:{max_n}", channel]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"yt-dlp timed out on {channel}", file=sys.stderr)
        return []
    return [tuple(line.split("|||", 1)) for line in out.stdout.splitlines()
            if "|||" in line]

def yt_audio_path(video_id):
    """Return a path to a unique audio file in a tmpdir for a given video id."""
    tmp = tempfile.mkdtemp(prefix="infotriage-yt-")
    return tmp, os.path.join(tmp, f"{video_id}.m4a")

def fetch_audio(video_id):
    """Pull audio (.m4a) for a single video via yt-dlp -x. Returns tmpdir (caller cleans up)."""
    if not which("yt-dlp"):
        return None, None
    tmp, audio = yt_audio_path(video_id)
    cmd = ["yt-dlp", "-x", "--audio-format", "m4a",
           "-o", audio, f"https://youtu.be/{video_id}"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        return tmp, None
    if r.returncode != 0 or not os.path.exists(audio):
        return tmp, None
    return tmp, audio

def transcribe_with(audio, runners):
    """Try each transcribe runner in order. Return first non-empty stdout, or None."""
    for runner in runners:
        if not which(runner[0]):
            continue
        try:
            t = subprocess.run(runner + [audio], capture_output=True,
                               text=True, timeout=900)
        except subprocess.TimeoutExpired:
            continue
        if t.returncode == 0 and t.stdout.strip():
            return t.stdout.strip()[:1000]
    return None

def transcribe(video_id, transcribe_wanted):
    if not transcribe_wanted:
        return f"(transcription disabled — set transcribe:true to enable; install mlx-whisper or whisper)"
    tmp, audio = fetch_audio(video_id)
    text = None
    if audio:
        text = transcribe_with(audio, [
            ["mlx_whisper"],                  # mlx-whisper CLI on Apple Silicon
            ["whisper"],                      # openai-whisper CLI fallback
        ])
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return text or "(transcription produced no output)"

def write_atom(name, entries):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<feed xmlns="http://www.w3.org/2005/Atom">',
             f'<title>InfoTriage · {name}</title>',
             f'<updated>{now}</updated>',
             f'<id>urn:infotriage:youtube:{slug(name)}</id>']
    for vid, title, text in entries:
        parts += ['<entry>',
                  f'<title>{escape(title)}</title>',
                  f'<id>urn:youtube:{vid}</id>',
                  f'<link href="https://youtu.be/{vid}"/>',
                  f'<updated>{now}</updated>',
                  f'<summary>{escape(text)}</summary>',
                  '</entry>']
    parts.append('</feed>')
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"youtube-{slug(name)}.xml")
    with open(out_path, "w") as f:
        f.write("\n".join(parts))
    return out_path, len(entries)

def main():
    load_dotenv(os.path.join(ROOT, ".env"))
    for c in load_channels():
        url = c["channel"]
        max_n = int(c.get("max_per_run", 3))
        tx = bool(c.get("transcribe", False))
        name = c.get("name") or url.rstrip("/").split("/")[-1] or "channel"
        vids = yt_dlp_list(url, max_n)
        entries = [(vid, title, transcribe(vid, tx)) for vid, title in vids]
        out, n = write_atom(name, entries)
        print(f"[youtube/{name}] wrote {n} entries -> {out}")


if __name__ == "__main__":
    main()
