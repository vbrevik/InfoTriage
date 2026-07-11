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

## Setting per-feed TTL manually (FreshRSS UI)

Some upstream sources are aggressively rate-limited. The most important example in this project is **NewsAPI.org**, whose free tier allows only **100 requests/day**. With the six NewsAPI feeds in [`apps/opml/feeds.opml`](../../apps/opml/feeds.opml), the default twice-an-hour cadence would exhaust the quota quickly.

To slow a feed down from the FreshRSS web UI:

1. Open <http://localhost:8088> and log in.
2. Go to **Subscriptions**.
3. Click the feed you want to throttle (e.g., one of the *NewsAPI · …* feeds).
4. Choose **Manage**.
5. Set **"Refresh at most every"** to a conservative interval:
   - **2 hours** = 72 requests/day for 6 feeds
   - **3 hours** = 48 requests/day for 6 feeds (recommended)
   - **4 hours** = 36 requests/day for 6 feeds
6. Save and repeat for each rate-limited feed.

For NewsAPI.org specifically, **3 hours** is the recommended starting point: it keeps the 6 feeds under the 100-requests/day free-tier cap while still refreshing several times a day.

## Automated TTL helper

If you prefer to set the TTL from the command line, use the helper script at [`scripts/set_newsapi_ttl.py`](../../scripts/set_newsapi_ttl.py):

```bash
# Default: 3 hours (10800 seconds)
python3 scripts/set_newsapi_ttl.py

# Or specify a different TTL in seconds
python3 scripts/set_newsapi_ttl.py 14400   # 4 hours
```

The script finds every feed whose URL contains `bridge=NewsAPI` in the FreshRSS SQLite database and updates its `ttl` value. It is safe to re-run after re-importing the OPML.

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

- [`apps/ingest/imap_to_atom.py`](imap_to_atom.py) — multi-IMAP mailboxes (Gmail / Outlook / Fastmail / ProtonMail / custom domain). One runner, per-account provider dispatch. Read-only.
- [`apps/ingest/yt_to_atom.py`](yt_to_atom.py) — YouTube channels → optional audio transcription → Atom feed. Read-only of channels.
- The legacy Gmail IMAP bridge has been retired; Gmail is now ingested via the `ingest-gmail` container using OAuth2/MCP (ADR-008).
