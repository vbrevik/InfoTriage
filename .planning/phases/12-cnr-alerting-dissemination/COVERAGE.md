# Phase 12 — ntfy Capability Matrix

Records which parts of the ntfy publish surface this phase (CNR alerting/dissemination)
integrates and which it deliberately opts out of. One row per capability the ntfy server
exposes; every row is either `INTEGRATE` (this phase depends on it) or `OPT-OUT` (in scope
to consider, deliberately not used).

| Capability | Decision | Reason |
|---|---|---|
| publish | INTEGRATE | The phase's whole purpose — `apps/alerting/outbox.py::NtfyClient.deliver()` POSTs the 7-key JSON payload to the topic path. |
| auth/token | INTEGRATE | Bearer token required for the primary topic (read+write) and the debug/test topics (write-only), per SPEC R6. Provisioned post-boot by `make -f ops/Makefile ntfy-token` (Plan 03 Task 2), never baked into an image layer. |
| priority | INTEGRATE | Max priority (`X-Priority: 5`) on every CAT I push — `outbox.py` sets this unconditionally since only CAT I items reach the emitter. |
| tags | INTEGRATE | PMESII tags plus a flag emoji tag, carried in the `X-Tags` header (`outbox.py`). |
| click-action | INTEGRATE | The `X-Click` header carries the `obsidian://` deep link built by `apps/alerting/deep_link.py`, per SPEC R5. |
| attachment | OPT-OUT | The SAB (Situational Awareness Board) is the canonical record; an ntfy attachment would make the push itself an independent record of intel, which prohibition P5 forbids. |
| delayed delivery | OPT-OUT | CAT I alerts are immediate by definition — no scheduling. Volume is handled by the 3-tier throttle shipped in plan 12-05, not by delaying delivery. |
| email-forward | OPT-OUT | ADR-016 airgap and SPEC D2 mandate a single dissemination channel; forwarding to email would violate prohibition P1 (alerts must not leave the machine). |
| websocket/subscribe | OPT-OUT | The operator's own ntfy client (web/iOS/Android) subscribes directly to the topic. This phase ships no server-side subscriber. |
| message caching | OPT-OUT (no behavior change) | The shipped `/var/cache/ntfy` cache volume (docker-compose.yml) is left as-is; this phase does not tune retention or disable caching. |
| icon/actions buttons | OPT-OUT | Not required by any SPEC R1–R6 acceptance criterion. |

## Topic ACL matrix (SPEC R6, as of Plan 03)

| Identity | `cnr-cat-i` | `cnr-cat-i-debug` | `cnr-cat-i-test` |
|---|---|---|---|
| producer | read-write | write-only | write-only |
| reader | read-only | (no grant — deny-all) | (no grant — deny-all) |

Default access is `deny-all` (`NTFY_AUTH_DEFAULT_ACCESS=deny-all`, `apps/ntfy/Dockerfile`); the
matrix above is the complete set of explicit per-topic grants baked into the pre-built image.
