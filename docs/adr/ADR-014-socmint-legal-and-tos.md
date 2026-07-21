# ADR-014 — SOCMINT, Arctic Data and ACLED Legal / ToS Posture

**Status.** Proposed (2026-07-21). Decision drafted for Phase 11
(SOCMINT + Arctic collection). Continues the ADR lineage in
`docs/ARCHITECTURE.md` (ADR-001..013).

---

**Context.** InfoTriage is extending its collection surface beyond RSS, IMAP,
and YouTube to include SOCMINT (Telegram public channels) and authoritative
Arctic data (BarentsWatch AIS). A third restricted source, ACLED (Armed
Conflict Location & Event Data), is frequently requested by intelligence users
but is governed by a separate commercial/public-sector license. The project
needs a clear legal and Terms-of-Service posture before any adapter code is
merged, so operators know what they may collect, how they must attribute it,
and what is categorically off-limits.

---

**Decision.** Adopt the following source-by-source posture for Phase 11 and
any future SOCMINT/Arctic integrations.

## 1. Telegram / Telethon (SOCMINT)

- **Scope.** Only **public Telegram channels** may be ingested. Private
  channels, groups, and direct messages are out of scope.
- **Operator responsibility.** The operator must select the specific public
  channels and is responsible for ensuring that ingestion complies with
  applicable law and Telegram's Terms of Service.
- **No AI/ML training.** Telegram explicitly prohibits using data obtained from
  the platform to train, fine-tune, or develop AI/ML models. InfoTriage will
  not use Telegram-derived text to train embeddings, classifiers, or LLMs.
  Existing semantic deduplication and NER already run against InfoTriage's own
  stored items, not against Telegram corpora.
- **Read-only, non-interfering use.** The adapter must not automate user
  actions (posting, joining, voting, reactions), tamper with read/online
  status, or interfere with sponsored-message display.
- **Rate limits.** The adapter must respect Telegram API rate limits and
  implement exponential backoff. Excessive polling that could degrade the
  platform is prohibited.
- **Terms reference.** [Telegram Terms of Service](https://telegram.org/tos),
  [Telegram API Terms of Service](https://core.telegram.org/api/terms),
  [Telethon documentation](https://docs.telethon.dev/en/stable/basic/next-steps.html).

## 2. BarentsWatch AIS (Arctic / MASINT)

- **License.** BarentsWatch open AIS data is provided under the **Norwegian
  Licence for Open Government Data (NLOD)**. Use is free, including
  commercial use, subject to the conditions below.
- **Registration.** A BarentsWatch API client/user account is required before
  accessing the data.
- **Attribution.** InfoTriage must display attribution such as
  "Data delivered by BarentsWatch" to end users.
- **No misrepresentation.** Derived products must not imply they were
  produced by BarentsWatch, and the data must not be used in violation of
  Norwegian law.
- **High-traffic courtesy.** Operators planning high-volume use should contact
  BarentsWatch in advance to avoid service impact.
- **Terms reference.** [BarentsWatch API Terms and Conditions](https://www.barentswatch.no/en/articles/api-terms-and-conditions/),
  [Live AIS API documentation](https://developer.barentswatch.no/docs/AIS/live-ais-api/),
  [NCA AIS access overview](https://www.kystverket.no/en/sea-transport-and-ports/ais/access-to-ais-data/).

## 3. ACLED (Restricted / License-Gated)

- **No use without a valid license.** ACLED data may only be ingested when the
  operator holds a current ACLED corporate or public-sector license appropriate
  to their organization. Free-tier / academic access is not sufficient for
  operational or governmental use.
- **License check gate.** The `ingest-acled` adapter (if ever built) must read
  a required `ACLED_LICENSE_KEY` (or equivalent contract document) and refuse
  to start or ingest if the license is absent or expired.
- **No LLM feeding without authorization.** ACLED's EULA prohibits using its
  content to train, test, or improve LLMs/ML models in ways that create a
  substitute for ACLED products or expose raw ACLED data. InfoTriage will not
  send ACLED-derived text to the local LLM unless the license explicitly
  permits such use.
- **License expiry.** If a valid ACLED license expires, the adapter must
  refuse to start and must block new ingestion. Existing ACLED-derived items
  are not automatically deleted; the operator decides whether to retain or
  remove them under the configured retention policy.
- **Attribution and transformative use.** Any ACLED-derived output must
  clearly attribute ACLED and be presented in a transformative, analytical
  form rather than raw redistribution.
- **Terms reference.** [ACLED EULA](https://acleddata.com/eula),
  [ACLED Content Usage Terms](https://acleddata.com/contentusage),
  [ACLED Terms and Conditions](https://acleddata.com/terms-and-conditions).

## 4. Cross-cutting constraints

- **Local-only LLM / transcription (ADR-004).** Translation and transcription
  of SOCMINT or Arctic data must run on the local Qwen36/Whisper stack. Cloud
  translation or transcription APIs are prohibited.
- **Discipline + reliability tags.** Every Phase 11 adapter must populate the
  `discipline` tag (e.g. `SOCMINT`, `OSINT`, `MASINT/AIS`) and the optional
  `admiralty_reliability` rating on each emitted item. Adapter-level
  validation must reject items that omit `discipline`.
- **Data retention and personal data.** Even public Telegram and AIS data may
  contain personal data. Operators must configure retention limits and handle
  data-subject requests in accordance with applicable law (e.g. GDPR). The
  system writes a deletion timestamp into `body_ref` metadata when an item is
  removed; hard deletion is operator-initiated.
- **Audit trail.** Adapter runs must write audit rows for each ingested item
  so collection provenance is reconstructible.

---

**Consequences.**

- **Operator burden.** The operator is responsible for channel selection
  (Telegram), API registration (BarentsWatch), and license possession
  (ACLED). InfoTriage provides adapters and gates, not legal clearance.
- **Implementation gates.** Code will enforce the ACLED license check and
  populate `discipline`/`admiralty_reliability` for every Phase 11 item.
  Failure to populate these fields is a validation error.
- **No AI-training scraper.** The Telegram and ACLED adapters must not be
  used to build training corpora for LLMs/ML models; this is a policy and code
  requirement.
- **Attribution UI.** BarentsWatch attribution must appear in the SAB/brief
  and Obsidian reading surfaces when AIS-derived items are shown.

**Validation.**

- ADR-014 is referenced from `.planning/phases/11-socmint/11-PLAN.md` and
  `docs/ARCHITECTURE.md`.
- `ingest-telegram`, `ingest-barentswatch`, and any future `ingest-acled`
  adapter READMEs link to this ADR.
- ACLED license gate is tested by unit tests before the adapter can be used.

**Related notes.** See `.planning/phases/11-socmint/11-PLAN.md` for the Phase 11
execution plan and ADR-004 for the local-only LLM constraint.
