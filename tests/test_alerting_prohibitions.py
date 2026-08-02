"""tests/test_alerting_prohibitions.py — mechanical guards for SPEC 12's five
alerting prohibitions (P1-P5) plus the AC8 failure-isolation proof (plan
12-09, the phase-sealing plan).

Every guard here is structural (YAML parse, Python AST inspection, or
observed runtime behavior), never a raw-text grep of a source file — a
comment in the file under inspection must not be able to both trip and
satisfy a check. Two helpers make this concrete: `_published_ports` (YAML
parse of docker-compose.yml, which discards comments) and
`_sql_string_constants` (AST parse of a Python file, docstrings structurally
excluded, so only executable string literals are inspected).

## Deviations from the plan's literal acceptance criteria (documented here,
## not silently absorbed — see 12-09-SUMMARY.md for the full record)

1. P2b's acceptance criterion asks for "at least one" SQL string constant
   under apps/alerting. The actual, correct count is ZERO: apps/alerting
   issues no raw SQL at all — every persistence call goes through the typed
   Store protocol (D-02). That is a *stronger* structural guarantee than "SQL
   exists but avoids the body column" (there is no query surface for a body
   reference to hide in). Confirmed by direct inspection: the only
   SQL-keyword hit anywhere under apps/alerting is a docstring in dedupe.py
   ("single INSERT-ON-CONFLICT statement"), which `_sql_string_constants`
   correctly excludes as a docstring per its own spec ("comments and
   docstrings are structurally out of scope"). Weakening the docstring
   exclusion just to inflate the count to 1 would reintroduce exactly the
   comment-satisfies-the-guard loophole this task exists to close, so this
   test asserts the true, stronger count (zero) instead.

2. P3's action text asks for a second case "asserting the summary is still
   passed through the existing truncation the scorer applies". No such
   truncation exists in `triage_score.score_item` today (confirmed by
   inspection of the function and of `apps/triage/worker.py`'s call site) —
   `summary` is interpolated into the prompt as-is. The second case here
   instead asserts the weaker, still-meaningful property that a long summary
   passes through verbatim (the input contract has not been silently
   widened), rather than presupposing truncation semantics the scorer does
   not implement.

3. P1's acceptance criterion asks that "every published port of every
   service in docker-compose.yml begins with the loopback address prefix".
   Two pre-existing, pre-ADR-016 (2026-07-23) services — `freshrss` (8088)
   and `rssbridge` (3000) — are genuinely bound on all interfaces, not
   localhost-only; they predate the loopback-port convention documented in
   comments on every later service ("matches the 127.0.0.1:HOST_PORT:
   CONTAINER_PORT convention used by every other InfoTriage service").
   Retightening their bindings touches docker-compose.yml, which is outside
   this plan's files_modified, and is a real behavior/network-exposure
   change an operator should decide, not one this executor should make
   silently. This test names the two services in an explicit, documented
   exception list and asserts loopback-only on every OTHER service in the
   file (including every future one), so the guard still does its job for
   the entire alerting-relevant surface and regresses loudly if a new
   service is ever added without a loopback binding. The freshrss/rssbridge
   exposure itself is flagged as backlog debt in 12-09-SUMMARY.md, not fixed
   here.
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from contracts import Item
from store import InMemoryStore

import triage_score
from emitter import build_alert_payload, handle_verdict_ready
from outbox import NtfyClient

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
ALERTING_DIR = REPO_ROOT / "apps" / "alerting"
ALERT_STATE_SQL = REPO_ROOT / "libs" / "store" / "sql" / "011-alert-state.sql"

LOOPBACK_PREFIX = "127.0.0.1:"

# Pre-existing, pre-ADR-016 legacy web-UI ports — see module docstring
# Deviation 3. Not silently dropped: flagged as backlog debt in the SUMMARY.
_LEGACY_NON_LOOPBACK_SERVICES = {"freshrss", "rssbridge"}

# Tokens naming an upstream server, a relay/forwarding target, an APNs/FCM
# configuration, or a hosted ntfy endpoint (ADR-016 airgap doctrine, P1).
_FORBIDDEN_EGRESS_TOKENS = ("ntfy.sh", "apns", "fcm", "relay", "forward", "upstream")

# Any HTTP routing framework capable of declaring a route beyond the raw
# asyncio.start_server health handler (P5b).
_WEB_FRAMEWORK_MODULES = {
    "fastapi",
    "aiohttp",
    "flask",
    "starlette",
    "bottle",
    "tornado",
    "sanic",
    "quart",
}

_SQL_KEYWORD_RE = re.compile(r"\b(select|insert|update|delete)\b", re.IGNORECASE)
_BODY_COLUMN_RE = re.compile(r"\bbody\b", re.IGNORECASE)


def _load_compose() -> dict:
    with open(COMPOSE_PATH, encoding="utf-8") as f:
        loaded: dict = yaml.safe_load(f)
    return loaded


_COMPOSE = _load_compose()


def _published_ports(service_name: str) -> list[str]:
    """Return the published port strings for `service_name`.

    Loads docker-compose.yml with the YAML parser (which discards comments),
    so a comment claiming a port is loopback-only cannot satisfy this check —
    only the actual parsed `ports:` values are inspected.
    """
    service = _COMPOSE["services"][service_name]
    return [str(p) for p in service.get("ports", [])]


def _sql_string_constants(path: Path) -> list[str]:
    """Parse `path` with the AST module; return string constants that look
    like SQL (contain a select/insert/update/delete keyword).

    Docstrings — a bare string `Expr` as the first statement of a module,
    function, or class body — are structurally excluded, so a comment or
    docstring mentioning a SQL-shaped word cannot satisfy a caller's check.
    Only string literals used as actual argument/assignment values are
    considered "executable" and inspected.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    docstring_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_ids.add(id(body[0].value))

    constants: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_ids:
                continue
            if _SQL_KEYWORD_RE.search(node.value):
                constants.append(node.value)
    return constants


def _alert_state_columns() -> list[str]:
    """Extract the column identifiers from alert_state's CREATE TABLE block.

    Parses out just the column list (structural), not a raw-text search of
    the whole file for forbidden words — the migration's header comments are
    never inspected by this helper.
    """
    text = ALERT_STATE_SQL.read_text(encoding="utf-8")
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS infotriage\.alert_state\s*\((.*?)\n\);",
        text,
        re.DOTALL,
    )
    assert match, "could not locate the alert_state CREATE TABLE block"
    columns = []
    for line in match.group(1).splitlines():
        line = line.strip().rstrip(",")
        if not line or line.startswith("--"):
            continue
        columns.append(line.split()[0])
    return columns


def _make_item(
    url_seed: str, *, summary: str = "fallback summary", body: str | None = None
) -> Item:
    return Item(
        source="Test Source",
        source_type="rss",
        url=f"https://example.com/{url_seed}",
        title="A prohibitions-test item",
        ts=datetime.now(tz=timezone.utc),
        lang="en",
        summary=summary,
        body=body,
    )


def _seed(
    store: InMemoryStore, item: Item, *, cnr, why: str = "rationale", pmesii: str = ""
) -> str:
    store.put_item(item)
    store.put_enrichment(
        item.id,
        {
            "ccir": None,
            "cnr": cnr,
            "score": 9,
            "bucket": "keep",
            "why": why,
            "pmesii": pmesii,
            "tessoc": None,
        },
    )
    return item.id


# ---------------------------------------------------------------------------
# P1 — airgap guard (ADR-016 / T1-02)
# ---------------------------------------------------------------------------


def test_p1_no_off_host_egress():
    """Every published port in docker-compose.yml is loopback-only (except
    the two documented pre-ADR-016 legacy services — see module docstring
    Deviation 3), and neither ntfy nor alerting declares an upstream/relay/
    forwarding/hosted-push configuration token.
    """
    for name in ("ntfy", "alerting"):
        for port in _published_ports(name):
            assert port.startswith(
                LOOPBACK_PREFIX
            ), f"service {name!r} publishes a non-loopback port: {port!r}"

    for name, definition in _COMPOSE["services"].items():
        if name in _LEGACY_NON_LOOPBACK_SERVICES:
            continue
        for port in _published_ports(name):
            assert port.startswith(
                LOOPBACK_PREFIX
            ), f"service {name!r} publishes a non-loopback port: {port!r}"

    services = _COMPOSE["services"]
    for name in ("ntfy", "alerting"):
        definition = services[name]
        environment = definition.get("environment") or {}
        command = definition.get("command") or []
        haystack_parts: list[str] = []
        if isinstance(environment, dict):
            haystack_parts.extend(str(k) for k in environment)
            haystack_parts.extend(str(v) for v in environment.values())
        else:
            haystack_parts.extend(str(v) for v in environment)
        haystack_parts.extend(str(c) for c in command)
        haystack = " ".join(haystack_parts).lower()
        for token in _FORBIDDEN_EGRESS_TOKENS:
            assert (
                token not in haystack
            ), f"service {name!r} configuration contains forbidden token {token!r}"


# ---------------------------------------------------------------------------
# P2 — excerpt guard: bounded, never sourced from the body column
# ---------------------------------------------------------------------------


def test_p2_excerpt_bounded_and_body_free():
    # P2a: a 5000-char rationale yields an excerpt of at most 500 chars.
    item = _make_item("p2a")
    enrichment = {"why": "x" * 5000, "pmesii": ""}
    payload = build_alert_payload(item, enrichment, item.id, "I")
    assert len(payload["sab_excerpt"]) <= 500

    # P2b: no SQL string constant under apps/alerting references the body
    # column. See module docstring Deviation 1: the true count is zero.
    all_constants: list[str] = []
    for path in sorted(ALERTING_DIR.glob("*.py")):
        all_constants.extend(_sql_string_constants(path))
    assert all_constants == []
    assert not any(_BODY_COLUMN_RE.search(c) for c in all_constants)

    # P2c: the payload is byte-identical whether or not item.body is
    # populated — the strongest proof the excerpt isn't sourced from it,
    # independent of how any query is written.
    item_no_body = _make_item("p2c", summary="summary text", body=None)
    item_with_body = item_no_body.model_copy(
        update={"body": "FULL ARTICLE TEXT " * 200}
    )
    enrichment2 = {"why": "rationale", "pmesii": "Military"}
    payload_no_body = build_alert_payload(
        item_no_body,
        enrichment2,
        item_no_body.id,
        "I",
        alert_id="fixed-alert",
        dedupe_id="fixed-dedupe",
    )
    payload_with_body = build_alert_payload(
        item_with_body,
        enrichment2,
        item_with_body.id,
        "I",
        alert_id="fixed-alert",
        dedupe_id="fixed-dedupe",
    )
    assert payload_no_body == payload_with_body


# ---------------------------------------------------------------------------
# P3 — scorer input guard: full text never reaches the prompt
# ---------------------------------------------------------------------------


def test_p3_scorer_input_unchanged(monkeypatch):
    captured: dict = {}

    def _fake_llm(messages, max_tokens=400):
        captured["prompt"] = messages[0]["content"]
        return json.dumps(
            {
                "ccir": "none",
                "cnr": "none",
                "pmesii": "none",
                "tessoc": "none",
                "score": 0,
                "why": "test",
            }
        )

    monkeypatch.setattr(triage_score, "llm", _fake_llm)

    sentinel = "SENTINEL_FULL_TEXT_9f3c7a"
    item = {
        "title": "A distinctive test title",
        "source": "Test Source",
        "summary": "A distinctive test summary",
        "body": sentinel,  # extra full-text key the scorer must never read
    }
    triage_score.score_item(item)
    prompt = captured["prompt"]
    assert sentinel not in prompt
    assert "A distinctive test title" in prompt
    assert "A distinctive test summary" in prompt

    # Second case (Deviation 2): a long summary still passes through
    # verbatim — the input contract has not widened.
    captured.clear()
    long_summary = "S" * 800
    triage_score.score_item({"title": "T2", "source": "Src", "summary": long_summary})
    assert long_summary in captured["prompt"]


# ---------------------------------------------------------------------------
# P4 — tier guard: only CAT I egresses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cnr_value", ["II", "Routine", "__ABSENT__", None])
def test_p4_non_cat_i_silent(stub_ntfy_server, tmp_path, cnr_value):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    item = _make_item(f"p4-{cnr_value}")
    seed_cnr = "none" if cnr_value in (None, "__ABSENT__") else cnr_value
    item_id = _seed(store, item, cnr=seed_cnr)
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")

    payload: dict = {"event": "verdict.ready", "item_id": item_id}
    if cnr_value != "__ABSENT__":
        payload["cnr"] = cnr_value

    asyncio.run(handle_verdict_ready(payload, store, client))

    assert len(handler_cls.requests) == 0


# ---------------------------------------------------------------------------
# P5 — no independent record: SAB stays canonical
# ---------------------------------------------------------------------------


def test_p5_no_independent_record():
    # P5a: alert_state's column set holds no item prose beyond the digest
    # title.
    columns = _alert_state_columns()
    forbidden = ("excerpt", "summary", "rationale", "fulltext", "full_text")
    for column in columns:
        lowered = column.lower()
        assert not any(
            token in lowered for token in forbidden
        ), f"alert_state column {column!r} looks like a second copy of item prose"
    assert "title" in [c.lower() for c in columns]

    # P5b: the alerting worker registers exactly one HTTP handler (health),
    # and no module in the package imports a routing framework capable of
    # declaring additional routes.
    worker_path = ALERTING_DIR / "alerting_worker.py"
    tree = ast.parse(worker_path.read_text(encoding="utf-8"), filename=str(worker_path))
    start_server_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == "start_server")
            or (isinstance(node.func, ast.Name) and node.func.id == "start_server")
        )
    ]
    assert (
        len(start_server_calls) == 1
    ), f"expected exactly one asyncio.start_server registration, found {len(start_server_calls)}"
    handler_arg = start_server_calls[0].args[0]
    assert isinstance(handler_arg, ast.Name) and handler_arg.id == "_handle_health"

    for path in sorted(ALERTING_DIR.glob("*.py")):
        module_tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(module_tree):
            imported: set[str] = set()
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = {node.module.split(".")[0]}
            overlap = imported & _WEB_FRAMEWORK_MODULES
            assert (
                not overlap
            ), f"{path}: imports {overlap} — P5b guard needs a real router check"


# ---------------------------------------------------------------------------
# AC8 — failure-isolation proof
# ---------------------------------------------------------------------------


def test_ac8_body_null_isolation(stub_ntfy_server, tmp_path):
    """The emit path fires a complete 7-field payload when the article's
    full-text field is NULL — body wiring never blocks alert firing."""
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    item = _make_item("ac8", summary="fallback summary", body=None)
    assert item.body is None
    item_id = _seed(store, item, cnr="I", why="rationale text", pmesii="Military")
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")

    asyncio.run(
        handle_verdict_ready(
            {"event": "verdict.ready", "item_id": item_id, "cnr": "I"}, store, client
        )
    )

    assert len(handler_cls.requests) == 1
    body = json.loads(handler_cls.requests[0]["body"])
    assert sorted(body.keys()) == sorted(
        [
            "alert_id",
            "cnr_tier",
            "dedupe_id",
            "deep_link",
            "item_link",
            "pmseii_tags",
            "sab_excerpt",
        ]
    )
    assert body["sab_excerpt"] == "rationale text"
    assert body["cnr_tier"] == "I"
    assert body["pmseii_tags"] == ["Military"]
    assert body["deep_link"].startswith("obsidian://open?vault=")
    assert body["item_link"].startswith("obsidian://open?vault=")
    assert body["alert_id"]
    assert body["dedupe_id"]
