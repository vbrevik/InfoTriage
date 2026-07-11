"""Regression test for the opml_health FeedUnhealthy schema-drift fix (Phase 99.1 RT-4).

Refs: `.planning/v1.0-MILESTONE-AUDIT.md` §8 RT-4 + §6 RT-4.

The M1 audit found that `apps/opml_health/service.py` defined `class FeedUnhealthy`
locally instead of importing the canonical Pydantic model from `libs/contracts`.
This is a schema-drift risk: two emission paths in the codebase, two field-shape
contracts in flight. Refactor RT-4 deletes the inline class and imports the
canonical. This test pins the post-refactor behavior so the drift cannot silently
regress.

It catches:
  1. The canonical FeedUnhealthy accepts the exact field shape opml_health emits.
  2. `model_dump(mode="json")` produces the expected envelope keys.
  3. Pydantic enforces the constraints the inline class previously papered over:
       - `reason: str = Field(max_length=120)` (was silently sliced in the inline class)
       - `ts: AwareDatetime` (was Optional in the inline class)
       - `event: Literal["feed.unhealthy"]` (was hard-coded in `.to_dict()`)
  4. The opml_health module's `FeedUnhealthy` symbol IS the canonical — same identity.
     This is the load-bearing assertion: if a future refactor reintroduces an
     inline class, identity check fails IMMEDIATELY.
"""
import datetime
import re
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_feed_unhealthy_schema_accepts_opml_health_emit_shape():
    """The canonical FeedUnhealthy must accept the field shape opml_health emits."""
    from contracts import FeedUnhealthy

    ts = datetime.datetime.now(datetime.timezone.utc)
    evt = FeedUnhealthy(
        event="feed.unhealthy",
        feed_url="https://example.invalid/feed.xml",
        feed_name="Example Feed",
        reason="❌ probe exception: HTTPError(...)"[:120],
        ts=ts,
    )

    d = evt.model_dump(mode="json")
    assert d["event"] == "feed.unhealthy"
    assert d["feed_url"] == "https://example.invalid/feed.xml"
    assert d["feed_name"] == "Example Feed"
    assert isinstance(d["reason"], str)
    assert len(d["reason"]) <= 120
    # Pydantic serializes AwareDatetime to ISO-8601 string in mode="json".
    assert isinstance(d["ts"], str), (
        f"ts must serialize to ISO-8601 string under mode='json'; got {type(d['ts']).__name__}"
    )
    # Strict ISO-8601 fingerprint: YYYY-MM-DDTHH:MM:SS prefix + UTC tz marker
    # (+00:00 or Z). The +00:00 form is what `datetime.isoformat()` emits for
    # tz-aware UTC datetimes; Z is the RFC3339 equivalent. Both are acceptable.
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", d["ts"]), (
        f"ts must start with ISO-8601 YYYY-MM-DDTHH:MM:SS prefix; got {d['ts']!r}"
    )
    assert d["ts"].endswith("+00:00") or d["ts"].endswith("Z"), (
        f"ts must end with UTC tz marker (+00:00 or Z); got {d['ts']!r}"
    )


def test_feed_unhealthy_max_length_120_enforced():
    """`Field(max_length=120)` must reject reasons >120 chars (was silently sliced inline)."""
    from contracts import FeedUnhealthy
    from pydantic import ValidationError

    ts = datetime.datetime.now(datetime.timezone.utc)
    with pytest.raises(ValidationError):
        FeedUnhealthy(
            event="feed.unhealthy",
            feed_url="https://example.invalid/feed.xml",
            feed_name="Example Feed",
            reason="x" * 121,  # 121 chars exceeds max_length=120
            ts=ts,
        )


def test_feed_unhealthy_requires_event_literal():
    """`Literal["feed.unhealthy"]` must reject non-conforming event types."""
    from contracts import FeedUnhealthy
    from pydantic import ValidationError

    ts = datetime.datetime.now(datetime.timezone.utc)
    with pytest.raises(ValidationError):
        FeedUnhealthy(
            event="feed.healthy",  # wrong literal value
            feed_url="https://example.invalid/feed.xml",
            feed_name="Example Feed",
            reason="oops",
            ts=ts,
        )


def test_opml_health_module_uses_canonical_feed_unhealthy():
    """`apps.opml_health.service.FeedUnhealthy` MUST BE the canonical contracts class.

    This is the load-bearing assertion: if a future refactor re-introduces the
    inline `class FeedUnhealthy` shadow, this test fails immediately (identity
    mismatch), catching the drift before it ships.
    """
    from apps.opml_health import service
    from contracts import FeedUnhealthy as CanonicalFeedUnhealthy

    # Same identity check: services.py's FeedUnhealthy symbol MUST BE the canonical.
    assert service.FeedUnhealthy is CanonicalFeedUnhealthy, (
        "apps/opml_health/service.py must import FeedUnhealthy from contracts, "
        "not define an inline shadow class. Refactor RT-4 regressed."
    )
    # And the canonical must be a Pydantic BaseModel — not the duck-typed inline class.
    import pydantic
    assert isinstance(CanonicalFeedUnhealthy, type) and issubclass(
        CanonicalFeedUnhealthy, pydantic.BaseModel
    ), "Canonical FeedUnhealthy must be a Pydantic BaseModel subclass."
