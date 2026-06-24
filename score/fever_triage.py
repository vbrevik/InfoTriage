#!/usr/bin/env python3
"""InfoTriage · Fever-wired triage.

Pulls UNREAD items from FreshRSS (Fever API), scores each with the LOCAL model,
and marks the skip-bucket items READ — so your unread list is only what matters.
Keepers (read/maybe) stay unread and are written to a digest.

  python3 score/fever_triage.py --dry-run     # score + report, change nothing
  python3 score/fever_triage.py               # also mark skips read
  python3 score/fever_triage.py --max 50      # cap items scored this run

Env (.env): FRESHRSS_FEVER_URL, FRESHRSS_FEVER_USER, FRESHRSS_FEVER_API_PASSWORD,
LLM_BASE_URL, LLM_API_KEY, LLM_MODEL. Reuses scoring from triage_score.py.
"""
import os, sys, re, json, time, hashlib, argparse, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from triage_score import llm, score_item, load_dotenv  # noqa: E402

ENV = os.path.join(os.path.dirname(__file__), "..", ".env")

def fever_key():
    user = os.environ["FRESHRSS_FEVER_USER"]
    pw = os.environ["FRESHRSS_FEVER_API_PASSWORD"]
    return hashlib.md5(f"{user}:{pw}".encode()).hexdigest()

def fever(api_key, query, **params):
    """POST to the Fever endpoint. query e.g. 'items', 'unread_item_ids', 'feeds'."""
    url = os.environ["FRESHRSS_FEVER_URL"] + "?api&" + query
    body = urllib.parse.urlencode({"api_key": api_key, **params}).encode()
    req = urllib.request.Request(url, data=body)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="score + report, mark nothing")
    ap.add_argument("--max", type=int, default=80, help="max items to score this run")
    ap.add_argument("--skip-threshold", type=int, default=3, help="score <= this -> mark read")
    args = ap.parse_args()
    load_dotenv(ENV)

    key = fever_key()
    if fever(key, "")["auth"] != 1:
        raise SystemExit("Fever auth failed — check FRESHRSS_FEVER_USER / _API_PASSWORD "
                         "and that the API is enabled in FreshRSS settings.")

    feeds = {f["id"]: f["title"] for f in fever(key, "feeds").get("feeds", [])}

    ids_raw = fever(key, "unread_item_ids").get("unread_item_ids", "")
    unread = [i for i in ids_raw.split(",") if i]
    if not unread:
        print("Nothing unread. Inbox already clean."); return
    unread = unread[-args.max:]                      # newest first (highest ids)
    print(f"{len(unread)} unread to triage (of {len(ids_raw.split(','))} total)\n")

    # Fetch item bodies in batches of 50 (Fever cap).
    items = []
    for i in range(0, len(unread), 50):
        chunk = ",".join(unread[i:i+50])
        items += fever(key, "items", with_ids=chunk).get("items", [])

    kept, skipped = [], []
    total = len(items)
    for n, it in enumerate(items, 1):
        v = score_item({
            "title": it.get("title", ""),
            "source": feeds.get(it.get("feed_id"), ""),
            "summary": strip_html(it.get("html", ""))[:500],
        })
        v["_id"] = it["id"]; v["_url"] = it.get("url", "")
        if v.get("score", 5) <= args.skip_threshold or v.get("bucket") == "skip":
            skipped.append(v)
            if not args.dry_run:
                fever(key, "mark=item", **{"as": "read", "id": it["id"]})
        else:
            kept.append(v)
        if n % 10 == 0 or n == total:
            print(f"  …{n}/{total} scored · {len(kept)} kept · {len(skipped)} junk",
                  file=sys.stderr, flush=True)

    kept.sort(key=lambda x: x.get("score", 0), reverse=True)
    icon = {"read": "🔥", "maybe": "🤔"}
    print("# InfoTriage digest — kept (still unread)\n")
    for v in kept:
        print(f"{icon.get(v.get('bucket'),'•')} **[{v.get('score')}] {v['title']}**")
        print(f"    {v.get('source','')} — {v.get('why','')}\n    {v.get('_url','')}\n")
    verb = "would mark" if args.dry_run else "marked"
    print(f"\n{len(kept)} kept · {verb} {len(skipped)} read (junk).")

if __name__ == "__main__":
    main()
