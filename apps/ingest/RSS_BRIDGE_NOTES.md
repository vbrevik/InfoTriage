# Sites via rss-bridge — operational notes

InfoTriage's `FreshRSS` + `rss-bridge` stack is already running per [`docker-compose.yml`](../../docker-compose.yml):

- FreshRSS: <http://localhost:8088>
- rss-bridge: <http://localhost:3000>

rss-bridge is the answer for **sites that don't ship their own RSS**. This file is a small ops note for the Norwegian defense / policy sites listed in [`opml/feeds.opml`](../../opml/feeds.opml) under `<!-- ===== NO native RSS (404) =====`.

## Sites already noted (no native RSS)

| Site | Recommended bridge | Status |
|---|---|---|
| <https://www.forsvaretsforum.no/> | XPathBridge | not configured |
| <https://www.ffi.no/> | XPathBridge | not configured |
| <https://www.nupi.no/> | XPathBridge | not configured |
| <https://www.utsyn.no/> | XPathBridge | not configured |
| <https://www.highnorthnews.com/> | CssSelectorBridge | not configured |

## Workflow (manual, via web UI)

1. Open <http://localhost:3000> in a browser.
2. Pick a bridge:
   - **XPathBridge** — best when the site exposes a clean article container (typical for the Norwegian defense/policy press).
   - **CssSelectorBridge** — when XPath is brittle (ad-heavy sites, complex layouts).
3. Configure the URL selector under "Parameters":
   - URL: the homepage or category page you want bridged.
   - Item selector: usually `<article>` or a class like `.news-list > li`.
   - Title: `h2` (or specific class).
   - Content: `article` body (or specific section).
4. Click **Generate feed**. rss-bridge returns a URL like:
   `http://localhost:3000/?action=display&bridge=XPathBridge&u=https%3A%2F%2Fwww.ffi.no%2F&...`
5. In FreshRSS: **Subscriptions ▸ add a feed** and paste that URL.

Repeat for each site. Once you've captured the URLs, add them to `opml/feeds.opml` so the operator can re-import the curated list.

## Refresh cadence

rss-bridge doesn't refresh on its own — FreshRSS pulls the rss-bridge-generated feed on its cycle. The project's [`docker-compose.yml`](../../docker-compose.yml) already configures `CRON_MIN: "23,53"` (twice an hour, off the `:00` stampede). That's fine for these publishers.

If you have a feed that rss-bridge struggles with (rate limits, Cloudflare), set a long per-feed TTL in FreshRSS (feed ▸ Manage ▸ Refresh at most every N hours).

## When to automate (optional CLI driver)

If you find yourself adding >5 sites this way, or you want a CI gate that re-validates the bridge URLs exist, a small `bridge/sites_to_feeds.py` driver can:

- read a JSON/YAML list of `{site, bridge, params}`;
- generate the rss-bridge URL per entry;
- emit a synthesized `opml/sites-via-rssbridge.opml` for FreshRSS to import.

**Currently deferred** — the manual workflow is fast enough at the current scale. Build the CLI driver only when the manual cost becomes non-trivial.

## When this list grows

If you add sites to `opml/feeds.opml` that have native RSS, prefer that — bridging should be reserved for sites that genuinely lack RSS. The OPML header includes an inline checklist:

```xml
<!-- ===== NO native RSS (404) — build with rss-bridge (CSS-selector scrape) =====
     Forsvarets forum   https://www.forsvaretsforum.no/
     FFI                https://www.ffi.no/
     NUPI               https://www.nupi.no/
     UTSYN              https://www.utsyn.no/
     High North News    https://www.highnorthnews.com/
     X / Twitter        — no free RSS; see README "X / Twitter" section
-->
```When you bridge a new site, drop the comment that marks it as such and add a new comment only if the bridge no longer works (404 / 403).

## Related bridges (same ingest story)

rss-bridge (this file) is one of three ingest paths. The other two are:

- [`bridge/imap_to_atom.py`](imap_to_atom.py) — multi-IMAP mailboxes (Gmail / Outlook / Fastmail / ProtonMail / custom domain). One runner, per-account provider dispatch. Read-only.
- [`bridge/yt_to_atom.py`](yt_to_atom.py) — YouTube channels → optional audio transcription → Atom feed. Read-only of channels.
- [`bridge/gmail_to_atom.py`](gmail_to_atom.py) — single-account Gmail bridge (pre-existing). Use either this OR a `name="gmail"` entry in `imap_to_atom.py`; not both against the same Gmail account (`data/feeds/gmail.xml` collision).
