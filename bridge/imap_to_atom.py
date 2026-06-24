#!/usr/bin/env python3
"""InfoTriage bridge · multi-mailbox IMAP -> local Atom feeds.

READ-ONLY: connects to one or more IMAP mailboxes, fetches messages matching a
per-account query, writes one Atom file per mailbox into ../data/feeds/{name}.xml
which FreshRSS subscribes to at http://feeds/{name}.xml. Never sends, marks,
or deletes anything (imap.select(..., readonly=True); no STORE/EXPUNGE calls).

Configuration (either path works; env wins):
  MAILBOXES = JSON array of mailbox specs, OR a sibling file `.mailboxes.json`.
  Each entry: {"name": str, "host": str, "user": str, "password": str,
                "query": str, "provider": str}

  provider in {"gmail","imap"}. Defaults: gmail.com host -> gmail; else imap.
  Gmail uses X-GM-RAW (proprietary search). All others use standard IMAP
  SEARCH (RFC 3501) — Outlook, Fastmail, ProtonMail, custom-domain mailboxes.

  Example:
    MAILBOXES='[
      {"name":"gmail-multi","host":"imap.gmail.com","user":"x@example.com","password":"APP_PW",
       "query":"newer_than:7d","provider":"gmail"},
      {"name":"outlook","host":"outlook.office365.com","user":"x@example.com","password":"X",
       "query":"SINCE 01-Jan-2024 SUBJECT newsletter"}
    ]'

Per-account output:
  /Users/vidarbrevik/projects/InfoTriage/data/feeds/<name>.xml

Subscribe in FreshRSS: Subscriptions ▸ add `http://feeds/<name>.xml`.

Notes:
- **provider="gmail"** uses Gmail's proprietary search (`X-GM-RAW`). Gmail query syntax: `newer_than:7d`, `from:x@y`, `subject:foo`, etc.
- **provider="imap"** uses standard RFC 3501 SEARCH keywords (`SINCE`, `BEFORE`, `FROM`, `SUBJECT`, `BODY`, `TEXT`, etc.). Outlook/Fastmail/ProtonMail IMAP accept this. Gmail-style compound syntax (e.g. `received>=01-Jan-2024 subject:foo`) is silently dropped.
- **MAILBOXES (as a JSON array starting with `[`) is not loaded from `.env`** — the loader only handles `KEY=VALUE` lines and skips anything that doesn't fit. Set via shell `export MAILBOXES='[…]'` or write `.mailboxes.json`.
- **Filename collision:** if `name="gmail"`, this script writes `data/feeds/gmail.xml` — the same file the pre-existing `bridge/gmail_to_atom.py` produces. Avoid by giving IMAP Gmail a different `name` (e.g. `name="gmail-multi"`), or run only one of the two scripts against Gmail.
"""
import os, sys, json, email, imaplib, datetime
from email.header import decode_header
from _util import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "feeds")

def load_dotenv(path):
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line and not line.startswith("["):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def load_mailboxes():
    """Load mailbox list from MAILBOXES env, fallback to .mailboxes.json."""
    raw = os.environ.get("MAILBOXES", "").strip()
    if not raw:
        alt = os.path.join(ROOT, ".mailboxes.json")
        if os.path.exists(alt):
            raw = open(alt).read().strip()
    if not raw:
        raise SystemExit("Set MAILBOXES (JSON) or write .mailboxes.json with the list.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"MAILBOXES JSON parse error: {e}")

def dec(s):
    if not s:
        return ""
    return "".join(
        (t.decode(enc or "utf-8", "replace") if isinstance(t, bytes) else t)
        for t, enc in decode_header(s))

def infer_provider(host):
    h = host.lower()
    # gmail.com and legacy googlemail.com (still used by some EU accounts).
    if "gmail.com" in h or "googlemail.com" in h:
        return "gmail"
    return "imap"  # standard IMAP SEARCH works for Outlook / Fastmail / ProtonMail / custom

def connect(host, user, pw):
    imap = imaplib.IMAP4_SSL(host)
    imap.login(user, pw)
    return imap

def search_ids(imap, query, provider):
    """Provider-aware SEARCH. Gmail uses X-GM-RAW; everything else standard SEARCH."""
    if provider == "gmail":
        typ, data = imap.search(None, 'X-GM-RAW', f'"{query}"')
    else:
        typ, data = imap.search(None, query)
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()

def body_text(msg):
    """Concatenate visible text content of an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    pass
        return msg.get("subject", "")
    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", "replace")
    except Exception:
        return ""

def fetch_entries(imap, ids, max_recent=60):
    out = []
    for mid in ids[-max_recent:]:
        typ, data = imap.fetch(mid, "(RFC822)")
        if typ != "OK":
            continue
        msg = email.message_from_bytes(data[0][1])
        out.append((
            dec(msg.get("subject")) or "(no subject)",
            dec(msg.get("from")) or "(unknown sender)",
            " ".join(body_text(msg).split())[:500],
            msg.get("Message-ID", str(mid))))
    return out

def write_atom(name, entries):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<feed xmlns="http://www.w3.org/2005/Atom">',
             f'<title>InfoTriage · {name}</title>',
             f'<updated>{now}</updated>',
             f'<id>urn:infotriage:{name}</id>']
    for subj, frm, snippet, mid in reversed(entries):
        parts += ['<entry>',
                  f'<title>{escape(subj)}</title>',
                  f'<id>{escape(mid)}</id>',
                  f'<author><name>{escape(frm)}</name></author>',
                  f'<updated>{now}</updated>',
                  f'<summary>{escape(snippet)}</summary>',
                  '</entry>']
    parts.append('</feed>')
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{name}.xml")
    with open(out_path, "w") as f:
        f.write("\n".join(parts))
    return out_path, len(entries)

def main():
    load_dotenv(os.path.join(ROOT, ".env"))
    mailboxes = load_mailboxes()
    failures = 0
    for mb in mailboxes:
        name = mb["name"]
        host = mb["host"]
        user = mb["user"]
        pw = mb["password"]
        query = mb.get("query", "ALL")
        provider = mb.get("provider") or infer_provider(host)
        print(f"[{name}] connecting to {host} as {user}…", file=sys.stderr, flush=True)
        try:
            imap = connect(host, user, pw)
            imap.select("INBOX", readonly=True)            # read-only posture, cannot modify mailbox
            ids = search_ids(imap, query, provider)
            entries = fetch_entries(imap, ids)
            imap.logout()
            out, n = write_atom(name, entries)
            print(f"[{name}] wrote {n} entries -> {out}")
        except imaplib.IMAP4.error as e:
            print(f"[{name}] IMAP error: {e}", file=sys.stderr)
            failures += 1
        except Exception as e:
            print(f"[{name}] unhandled: {e}", file=sys.stderr)
            failures += 1
    if failures:
        print(f"\n{failures} mailbox(es) failed; the rest succeeded.", file=sys.stderr)
        sys.exit(1 if failures == len(mailboxes) else 0)


if __name__ == "__main__":
    main()
