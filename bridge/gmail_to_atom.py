#!/usr/bin/env python3
"""trimail bridge — Gmail newsletters -> local Atom feed.

READ-ONLY: connects to Gmail IMAP, fetches messages matching GMAIL_QUERY, writes
an Atom file into ../data/feeds/ which the `feeds` container serves to FreshRSS
at http://feeds/gmail.xml. Never sends, marks, or deletes anything.

Run on the host (not in Docker) so it can reach Gmail directly:
  python3 bridge/gmail_to_atom.py
Then in FreshRSS add subscription:  http://feeds/gmail.xml

Env (or .env): GMAIL_USER, GMAIL_APP_PASSWORD, GMAIL_QUERY.
"""
import os, email, imaplib, html, datetime
from email.header import decode_header

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "feeds", "gmail.xml")

def load_dotenv(path):
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def dec(s):
    if not s:
        return ""
    return "".join(
        (t.decode(enc or "utf-8", "replace") if isinstance(t, bytes) else t)
        for t, enc in decode_header(s))

def gmail_search(imap, query):
    # Gmail's X-GM-RAW lets us use normal Gmail search syntax over IMAP.
    typ, data = imap.search(None, "X-GM-RAW", f'"{query}"')
    return data[0].split() if typ == "OK" and data and data[0] else []

def body_text(msg):
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

def main():
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    user = os.environ.get("GMAIL_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    query = os.environ.get("GMAIL_QUERY", "newer_than:7d")
    if not user or not pw:
        raise SystemExit("Set GMAIL_USER and GMAIL_APP_PASSWORD in .env (app password, not real password).")

    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(user, pw)
    imap.select("INBOX", readonly=True)              # readonly: cannot modify mailbox
    ids = gmail_search(imap, query)

    entries = []
    for mid in ids[-60:]:                            # cap to recent 60
        typ, data = imap.fetch(mid, "(RFC822)")
        if typ != "OK":
            continue
        msg = email.message_from_bytes(data[0][1])
        subj = dec(msg.get("subject"))
        frm = dec(msg.get("from"))
        snippet = " ".join(body_text(msg).split())[:500]
        entries.append((subj, frm, snippet, msg.get("Message-ID", str(mid))))
    imap.logout()

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<feed xmlns="http://www.w3.org/2005/Atom">',
             '<title>trimail · Gmail newsletters</title>',
             f'<updated>{now}</updated>',
             '<id>urn:trimail:gmail</id>']
    for subj, frm, snippet, mid in reversed(entries):
        parts += ['<entry>',
                  f'<title>{html.escape(subj)}</title>',
                  f'<id>{html.escape(mid)}</id>',
                  f'<author><name>{html.escape(frm)}</name></author>',
                  f'<updated>{now}</updated>',
                  f'<summary>{html.escape(snippet)}</summary>',
                  '</entry>']
    parts.append('</feed>')

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(parts))
    print(f"Wrote {len(entries)} entries -> {os.path.abspath(OUT)}")

if __name__ == "__main__":
    main()
