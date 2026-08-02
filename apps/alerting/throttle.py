#!/usr/bin/env python3
"""throttle.py — SPEC R3's two sliding-window volume caps on CAT I egress.

Two tiers, evaluated in order: at most WINDOW_60S_CAP (5) alerts fired in
any trailing 60-second window, and at most WINDOW_10MIN_CAP (10) alerts
fired in any trailing 600-second window. Both windows are sliding by
construction — the Store's `count_alerts_in_window` compares each row's
`fired_at` against an injected-or-server `now` minus the window length,
never against a truncated calendar boundary (SPEC R3 Edge R3/precision,
"no fixed-clock burst loophole"). Do NOT add any rounding, truncation, or
period-start caching here or in the Store query — that reintroduces the
burst loophole this module exists to close.

Counting rule (the likeliest off-by-one in this phase): `claim_alert` has
already written the alert-being-evaluated's row with its `fired_at` BEFORE
`check_throttle` runs (see `apps/alerting/emitter.py::_emit_if_claimed`), so
`count_alerts_in_window` always includes the alert currently under
evaluation. The pass condition is therefore a strict greater-than
comparison: the alert PASSES when the count is at most the cap, and is
THROTTLED when the count exceeds it. That yields exactly SPEC R3's
boundary — the 5th alert in a tight 60s cluster sees a count of 5 and
passes; the 6th sees 6 and is throttled.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

WINDOW_60S_CAP = 5
WINDOW_10MIN_CAP = 10

WINDOW_60S_SECONDS = 60
WINDOW_10MIN_SECONDS = 600


@dataclass(frozen=True)
class ThrottleVerdict:
    """Result of one `check_throttle` evaluation.

    `passed` is True when the alert may proceed to egress. When `passed`
    is False, `tier` names which window tripped ("60s" or "600s") so the
    emitter's log line and the eventual digest reason are specific rather
    than generic.
    """

    passed: bool
    tier: Optional[str] = None


def check_throttle(
    store, *, now: Optional[datetime.datetime] = None
) -> ThrottleVerdict:
    """Evaluate the 60-second tier, then the 600-second tier, against `store`.

    Called AFTER `claim_alert` has written the current alert's row (see the
    module docstring's counting rule) and BEFORE any egress. Returns the
    first tier that trips; a verdict with `passed=True` means neither tier
    is exceeded.
    """
    count_60s = store.count_alerts_in_window(window_seconds=WINDOW_60S_SECONDS, now=now)
    if count_60s > WINDOW_60S_CAP:
        return ThrottleVerdict(passed=False, tier="60s")

    count_600s = store.count_alerts_in_window(
        window_seconds=WINDOW_10MIN_SECONDS, now=now
    )
    if count_600s > WINDOW_10MIN_CAP:
        return ThrottleVerdict(passed=False, tier="600s")

    return ThrottleVerdict(passed=True)
