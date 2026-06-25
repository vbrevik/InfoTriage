# R2 Dedup Bake-off Verdict

**Verdict: PARTIAL — mechanism promising, threshold not yet calibrated**

No single (model, threshold) pair cleared both bars (`collapse_rate >= 0.8` AND `control_overmerge == 0`) on this 2026-06-25 corpus. Best achievable numbers recorded below.

**Root cause:** Same-topic / different-event control pairs (e.g. three distinct Trump articles) have embedding similarity overlapping with same-event cross-language pairs, preventing a clean threshold cut. The corpus control set is too topically narrow for a reliable calibration. Phase 5 must use a stricter evaluation protocol with genuinely off-topic controls.

## Closest Approach to Both Bars

| Field | Value |
|-------|-------|
| Model | `mE5-large` |
| Threshold | `0.84` |
| collapse_rate | `0.783` (bar: >= 0.8) |
| control_overmerge | `1` (bar: == 0) |
| Gap to pass | collapse_rate ok=False, overmerge_ok=False |

This is the operating point minimizing combined distance to both acceptance bars.
bge-m3 is disqualified entirely: max collapse_rate < 0.05 across all thresholds.

## Chosen Pair (Reported)

| Field | Value |
|-------|-------|
| Model | `mE5-large` |
| Threshold | `0.84` |
| collapse_rate | `0.783` (78%) |
| control_overmerge | `1` |
| Verdict | PARTIAL |

## Calibration Event Set

- **Corpus date:** 2026-06-25 (single day, NRK + BBC + TASS)
- **Same-story pairs (yes):** 23 pairs derived from 13 labeled rows
- **Control pairs (no):** 17 pairs derived from 11 labeled rows
- **Events covered:** Venezuela earthquake (cross-lang: RU/EN/NO), Japan earthquake,
  FIFA World Cup qualifiers, Trump/Iran deal, NATO-Ukraine European allies,
  Medvedev statements series, Norwegian school issues
- **Generalization note:** Threshold calibrated on one day's event set.
  Cross-date generalization is **unverified** (RESEARCH Open Question 3).
  Phase 5 must validate on a held-out corpus before deploying to production.

## Implications for Phase 5

- Q5 embedding model choice: **mE5-large** (locked for ADR, Phase 5 embedding infra)
- Dedup threshold starting point: `0.84` (tune on larger corpus in Phase 5)
- Input text: `title + summary[:512]` only (long-input caveat — never full body)
- For mE5-large: `passage: ` prefix required for corpus documents (query documents
  use `query: ` prefix)

## Full Sweep Table

### bge-m3

| Threshold | collapse_rate | control_overmerge | Qualifies? |
|----------:|-------------:|------------------:|:----------:|
| 0.75 | 0.043 | 0 |  |
| 0.76 | 0.043 | 0 |  |
| 0.77 | 0.043 | 0 |  |
| 0.78 | 0.043 | 0 |  |
| 0.79 | 0.043 | 0 |  |
| 0.80 | 0.043 | 0 |  |
| 0.81 | 0.043 | 0 |  |
| 0.82 | 0.043 | 0 |  |
| 0.83 | 0.000 | 0 |  |
| 0.84 | 0.000 | 0 |  |
| 0.85 | 0.000 | 0 |  |
| 0.86 | 0.000 | 0 |  |
| 0.87 | 0.000 | 0 |  |
| 0.88 | 0.000 | 0 |  |
| 0.89 | 0.000 | 0 |  |
| 0.90 | 0.000 | 0 |  |
| 0.91 | 0.000 | 0 |  |
| 0.92 | 0.000 | 0 |  |
| 0.93 | 0.000 | 0 |  |
| 0.94 | 0.000 | 0 |  |
| 0.95 | 0.000 | 0 |  |
| 0.96 | 0.000 | 0 |  |
| 0.97 | 0.000 | 0 |  |
| 0.98 | 0.000 | 0 |  |

### mE5-large

| Threshold | collapse_rate | control_overmerge | Qualifies? |
|----------:|-------------:|------------------:|:----------:|
| 0.75 | 1.000 | 14 |  |
| 0.76 | 1.000 | 13 |  |
| 0.77 | 1.000 | 11 |  |
| 0.78 | 0.957 | 10 |  |
| 0.79 | 0.957 | 10 |  |
| 0.80 | 0.870 | 5 |  |
| 0.81 | 0.826 | 5 |  |
| 0.82 | 0.783 | 5 |  |
| 0.83 | 0.783 | 3 |  |
| 0.84 | 0.783 | 1 |  |
| 0.85 | 0.739 | 1 |  |
| 0.86 | 0.609 | 1 |  |
| 0.87 | 0.391 | 1 |  |
| 0.88 | 0.304 | 1 |  |
| 0.89 | 0.174 | 1 |  |
| 0.90 | 0.130 | 1 |  |
| 0.91 | 0.087 | 0 |  |
| 0.92 | 0.087 | 0 |  |
| 0.93 | 0.000 | 0 |  |
| 0.94 | 0.000 | 0 |  |
| 0.95 | 0.000 | 0 |  |
| 0.96 | 0.000 | 0 |  |
| 0.97 | 0.000 | 0 |  |
| 0.98 | 0.000 | 0 |  |
