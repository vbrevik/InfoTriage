#!/usr/bin/env python3
"""recall.py — thematic recall over the InfoTriage corpus.

Usage:
    python recall.py --topic "Arctic security" --since 7d
    python recall.py --topic "Arctic security" --since 2026-07-01 --json
    python recall.py --topic "Arctic security" --obsidian /vault --synthesize
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "libs" / "store" / "src"))

from store import PostgresStore  # noqa: E402


EMBED_MODEL = "intfloat/multilingual-e5-large"


def _get_embedding(text: str) -> list[float]:
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key = os.environ.get("LLM_API_KEY", "omlx")
    body = json.dumps({"model": EMBED_MODEL, "input": text}).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/embeddings",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return cast(list[float], json.load(r)["data"][0]["embedding"])


def _llm(messages: list[dict], max_tokens: int = 800) -> str:
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key = os.environ.get("LLM_API_KEY", "omlx")
    model = os.environ.get("LLM_MODEL", "qwen36-ud-4bit")
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
    ).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return cast(str, json.load(r)["choices"][0]["message"]["content"])


def _parse_since(since: str | None) -> datetime.datetime | None:
    if since is None:
        return None
    try:
        if since.endswith("d") and since[:-1].isdigit():
            days = int(since[:-1])
            if days < 0:
                raise SystemExit(f"Invalid --since value: {since!r} (negative days)")
            return datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=days)
        dt = datetime.datetime.fromisoformat(since)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except (ValueError, TypeError) as exc:
        raise SystemExit(f"Invalid --since value: {since!r} ({exc})") from exc


def _synthesis_prompt(topic: str, results: list[dict], include_body: bool) -> str:
    lines = [
        "Answer the query using ONLY the provided articles. Cite every claim with [item_id].",
        "If the articles do not answer the query, say so.\n",
        f"Query: {topic}\n",
        "Articles:",
    ]
    for r in results:
        lines.append(
            f"[item_id: {r['item_id']}] Title: \"{r['title']}\" "
            f"Source: {r['source']} CCIR: {r['ccir']} Score: {r['score']}"
        )
        if r.get("summary"):
            lines.append(f"Summary: {r['summary']}")
        if include_body and r.get("body"):
            lines.append(f"Body: {r['body'][:500]}")
    return "\n".join(lines)


def _markdown_output(topic: str, since: str | None, results: list[dict]) -> str:
    if not results:
        return f"No results found for '{topic}'."
    since_str = since or "all time"
    lines = [f"## Recall: \"{topic}\" ({since_str})\n", "| # | Title | Source | CCIR | Score | Similarity |", "|---|-------|--------|------|-------|------------|"]
    for i, r in enumerate(results, 1):
        title = f"[{r['title']}]({r['url']})" if r.get("url") else r["title"]
        lines.append(
            f"| {i} | {title} | {r['source']} | {r['ccir']} | {r['score']} | {r['similarity']:.3f} |"
        )
    return "\n".join(lines)


def _obsidian_output(topic: str, since: str | None, results: list[dict], synthesis: str | None) -> str:
    front_matter = {
        "topic": topic,
        "since": since,
        "count": len(results),
        "results": results,
    }
    lines = ["---", json.dumps(front_matter, indent=2, ensure_ascii=False), "---", ""]
    lines.append(_markdown_output(topic, since, results))
    if synthesis:
        lines.append("\n## Synthesis\n\n" + synthesis)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Thematic recall over the InfoTriage corpus")
    parser.add_argument("--topic", required=True, help="Search query topic")
    parser.add_argument("--since", help="Date filter: 7d or ISO date")
    parser.add_argument("--ccir", help="Filter by CCIR ID")
    parser.add_argument("--bucket", choices=["keep", "maybe", "skip"], help="Filter by bucket")
    parser.add_argument("--limit", type=int, default=50, help="Max results")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--obsidian", help="Write Obsidian note to this path")
    parser.add_argument("--synthesize", action="store_true", help="Synthesize with local qwen36")
    parser.add_argument("--include-body", action="store_true", help="Include article body in synthesis")
    parser.add_argument("--dsn", default=os.environ.get("INFOTRIAGE_PG_DSN"), help="Postgres DSN")
    args = parser.parse_args()

    if not args.dsn:
        print("ERROR: --dsn or INFOTRIAGE_PG_DSN required", file=sys.stderr)
        sys.exit(1)

    since_dt = _parse_since(args.since)
    vec = _get_embedding(f"query: {args.topic}")

    with PostgresStore(dsn=args.dsn, blob_root=Path("/tmp/blobs")) as store:
        results = store.recall_items(
            vec,
            since=since_dt,
            ccir=args.ccir,
            bucket=args.bucket,
            limit=args.limit,
        )
        # Enrich results with article summary and optional body for synthesis.
        for r in results:
            item = store.get_item(r["item_id"])
            if item is not None:
                r["summary"] = item.summary
                if args.include_body and item.body_ref:
                    try:
                        body = store.get_blob(item.body_ref)
                        r["body"] = body.decode("utf-8", errors="ignore")
                    except Exception:
                        r["body"] = None

    if args.json:
        # JSON output should not silently leak full article bodies.
        safe_results = [
            {k: v for k, v in r.items() if k != "body"} for r in results
        ]
        print(json.dumps(safe_results, indent=2, ensure_ascii=False))
        return

    synthesis: str | None = None
    if args.synthesize:
        synthesis = _llm(
            [{"role": "user", "content": _synthesis_prompt(args.topic, results, args.include_body)}]
        )

    markdown = _markdown_output(args.topic, args.since, results)
    print(markdown)
    if synthesis:
        print("\n## Synthesis\n")
        print(synthesis)

    if args.obsidian:
        vault = Path(args.obsidian)
        vault.mkdir(parents=True, exist_ok=True)
        slug = args.topic.replace(" ", "-").replace("/", "-")[:50]
        note_path = vault / f"recall-{slug}-{datetime.datetime.now(tz=datetime.timezone.utc).strftime('%Y-%m-%d')}.md"
        note_path.write_text(_obsidian_output(args.topic, args.since, results, synthesis), encoding="utf-8")
        print(f"\nObsidian note written to {note_path}")


if __name__ == "__main__":
    main()
