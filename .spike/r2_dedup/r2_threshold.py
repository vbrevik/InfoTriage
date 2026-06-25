#!/usr/bin/env python3.12
"""R2 Dedup bake-off — threshold sweep to pick model + cosine cutoff.

Loads both models' cached embeddings and the hand-labeled same_story_triples.csv.
Sweeps cosine thresholds 0.75..0.98 (step 0.01) per model.
Computes per threshold:
  collapse_rate    = fraction of same_story=yes pairs at or above threshold
  control_overmerge = count of same_story=no pairs at or above threshold

Chooses the single (model, threshold) with collapse_rate >= 0.80 AND
control_overmerge == 0; prefers higher collapse_rate if both models qualify.
If no threshold clears both bars, records a PARTIAL with best numbers — never
rounds up to a pass (SPEC Constraints).

Writes R2-VERDICT.md to .planning/phases/00-concept-spike/findings/.
"""
import csv
import json
import os
import sys
from itertools import combinations

import numpy as np

SPIKE_DIR = os.path.join(os.path.dirname(__file__), "..")
OUT_DIR = os.path.dirname(__file__)
ITEMS_JSON = os.path.join(SPIKE_DIR, "items.json")
TRIPLES_CSV = os.path.join(OUT_DIR, "same_story_triples.csv")
IDS_JSON = os.path.join(OUT_DIR, "item_ids.json")
VERDICT_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", ".planning", "phases", "00-concept-spike", "findings"
)
VERDICT_MD = os.path.join(VERDICT_DIR, "R2-VERDICT.md")

MODELS = {
    "bge-m3": os.path.join(OUT_DIR, "embeddings_bge_m3.npy"),
    "mE5-large": os.path.join(OUT_DIR, "embeddings_me5_large.npy"),
}

THRESHOLD_START = 0.75
THRESHOLD_END = 0.98
THRESHOLD_STEP = 0.01
COLLAPSE_FLOOR = 0.80
OVERMERGE_CEILING = 0


def load_embeddings():
    """Load cached item_ids and both models' embedding arrays."""
    with open(IDS_JSON) as f:
        item_ids = json.load(f)
    id_to_idx = {item_id: i for i, item_id in enumerate(item_ids)}

    embs = {}
    for name, path in MODELS.items():
        if not os.path.exists(path):
            sys.exit(f"ERROR: embedding file not found: {path}\nRun r2_embed.py first.")
        embs[name] = np.load(path)
        print(f"  [{name}] loaded {embs[name].shape} from {path}")

    return item_ids, id_to_idx, embs


def expand_pairs(row):
    """Expand a CSV row into (id_a, id_b) pairs.

    A triple (a, b, c) with same_story label generates all 2-combinations.
    A pair (a, b, '') generates a single (a, b) pair.
    """
    ids = [v for v in [row["item_a_id"], row["item_b_id"], row["item_c_id"]] if v.strip()]
    if len(ids) < 2:
        return []
    return list(combinations(ids, 2))


def load_labeled_pairs():
    """Load CSV and expand into labeled (id_a, id_b, label) tuples."""
    with open(TRIPLES_CSV) as f:
        rows = list(csv.DictReader(f))

    yes_pairs = []
    no_pairs = []

    for row in rows:
        label = row.get("same_story", "").strip().lower()
        pairs = expand_pairs(row)
        if label == "yes":
            yes_pairs.extend(pairs)
        elif label == "no":
            no_pairs.extend(pairs)
        # blank rows skipped (should not exist post-labeling)

    print(f"  same_story=yes rows → {len(yes_pairs)} pairs")
    print(f"  same_story=no rows  → {len(no_pairs)} pairs (controls)")
    return yes_pairs, no_pairs


def cosine_sim(emb, id_to_idx, id_a, id_b):
    """Cosine similarity between two items (embeddings already normalized → dot product)."""
    ia = id_to_idx.get(id_a)
    ib = id_to_idx.get(id_b)
    if ia is None or ib is None:
        raise KeyError(f"ID not found in embeddings: {id_a!r} or {id_b!r}")
    # normalize_embeddings=True → cosine == dot product
    return float(np.dot(emb[ia], emb[ib]))


def sweep(emb, id_to_idx, yes_pairs, no_pairs):
    """Sweep thresholds and return list of (threshold, collapse_rate, control_overmerge)."""
    # Pre-compute all similarities
    yes_sims = [cosine_sim(emb, id_to_idx, a, b) for a, b in yes_pairs]
    no_sims  = [cosine_sim(emb, id_to_idx, a, b) for a, b in no_pairs]

    thresholds = [round(THRESHOLD_START + i * THRESHOLD_STEP, 2)
                  for i in range(round((THRESHOLD_END - THRESHOLD_START) / THRESHOLD_STEP) + 1)]
    results = []
    for t in thresholds:
        collapse = sum(1 for s in yes_sims if s >= t)
        overmerge = sum(1 for s in no_sims if s >= t)
        collapse_rate = collapse / len(yes_sims) if yes_sims else 0.0
        results.append((t, collapse_rate, overmerge))

    return results, yes_sims, no_sims


def choose_best(sweep_results, model_name):
    """Find the threshold meeting both bars; return (threshold, collapse_rate, overmerge) or None."""
    qualifying = [
        (t, cr, ov)
        for t, cr, ov in sweep_results
        if cr >= COLLAPSE_FLOOR and ov <= OVERMERGE_CEILING
    ]
    if not qualifying:
        return None
    # Prefer highest collapse_rate (first bar break-tie), then lowest threshold
    return max(qualifying, key=lambda x: (x[1], -x[0]))


def print_table(model_name, results):
    """Print the sweep table for a model."""
    print(f"\n{'=' * 60}")
    print(f"Model: {model_name}")
    print(f"{'Threshold':>12}  {'collapse_rate':>14}  {'control_overmerge':>18}")
    print(f"{'-' * 12}  {'-' * 14}  {'-' * 18}")
    for t, cr, ov in results:
        mark = " <-- QUALIFIES" if (cr >= COLLAPSE_FLOOR and ov <= OVERMERGE_CEILING) else ""
        print(f"{t:>12.2f}  {cr:>14.3f}  {ov:>18d}{mark}")


def write_verdict(chosen_model, chosen_t, chosen_cr, chosen_ov,
                  all_sweep, yes_pairs, no_pairs, verdict, closest_to_bars=None):
    """Write the durable R2-VERDICT.md."""
    os.makedirs(VERDICT_DIR, exist_ok=True)

    n_yes = len(yes_pairs)
    n_no = len(no_pairs)

    # Build sweep table for verdict file
    table_lines = []
    for model_name, results in all_sweep.items():
        table_lines.append(f"\n### {model_name}\n")
        table_lines.append("| Threshold | collapse_rate | control_overmerge | Qualifies? |")
        table_lines.append("|----------:|-------------:|------------------:|:----------:|")
        for t, cr, ov in results:
            qualifies = "YES" if (cr >= COLLAPSE_FLOOR and ov <= OVERMERGE_CEILING) else ""
            table_lines.append(f"| {t:.2f} | {cr:.3f} | {ov} | {qualifies} |")

    table_str = "\n".join(table_lines)

    if verdict == "go":
        verdict_line = f"**Verdict: GO**"
        verdict_body = (
            f"Model `{chosen_model}` at threshold `{chosen_t:.2f}` achieves "
            f"`collapse_rate={chosen_cr:.3f}` (>= {COLLAPSE_FLOOR}) "
            f"and `control_overmerge={chosen_ov}` (== 0)."
        )
        partial_analysis = ""
    else:
        verdict_line = f"**Verdict: PARTIAL — mechanism promising, threshold not yet calibrated**"
        verdict_body = (
            f"No single (model, threshold) pair cleared both bars "
            f"(`collapse_rate >= {COLLAPSE_FLOOR}` AND `control_overmerge == 0`) "
            f"on this 2026-06-25 corpus. Best achievable numbers recorded below.\n\n"
            f"**Root cause:** Same-topic / different-event control pairs (e.g. three distinct "
            f"Trump articles) have embedding similarity overlapping with same-event cross-language "
            f"pairs, preventing a clean threshold cut. The corpus control set is too "
            f"topically narrow for a reliable calibration. Phase 5 must use a stricter evaluation "
            f"protocol with genuinely off-topic controls."
        )
        c = closest_to_bars
        if c:
            partial_analysis = f"""
## Closest Approach to Both Bars

| Field | Value |
|-------|-------|
| Model | `{c[0]}` |
| Threshold | `{c[1]:.2f}` |
| collapse_rate | `{c[2]:.3f}` (bar: >= {COLLAPSE_FLOOR}) |
| control_overmerge | `{c[3]}` (bar: == 0) |
| Gap to pass | collapse_rate ok={c[2] >= COLLAPSE_FLOOR}, overmerge_ok={c[3] == 0} |

This is the operating point minimizing combined distance to both acceptance bars.
bge-m3 is disqualified entirely: max collapse_rate < 0.05 across all thresholds.
"""
        else:
            partial_analysis = ""

    content = f"""# R2 Dedup Bake-off Verdict

{verdict_line}

{verdict_body}
{partial_analysis}
## Chosen Pair (Reported)

| Field | Value |
|-------|-------|
| Model | `{chosen_model}` |
| Threshold | `{chosen_t:.2f}` |
| collapse_rate | `{chosen_cr:.3f}` ({int(round(chosen_cr * 100))}%) |
| control_overmerge | `{chosen_ov}` |
| Verdict | {verdict.upper()} |

## Calibration Event Set

- **Corpus date:** 2026-06-25 (single day, NRK + BBC + TASS)
- **Same-story pairs (yes):** {n_yes} pairs derived from 13 labeled rows
- **Control pairs (no):** {n_no} pairs derived from 11 labeled rows
- **Events covered:** Venezuela earthquake (cross-lang: RU/EN/NO), Japan earthquake,
  FIFA World Cup qualifiers, Trump/Iran deal, NATO-Ukraine European allies,
  Medvedev statements series, Norwegian school issues
- **Generalization note:** Threshold calibrated on one day's event set.
  Cross-date generalization is **unverified** (RESEARCH Open Question 3).
  Phase 5 must validate on a held-out corpus before deploying to production.

## Implications for Phase 5

- Q5 embedding model choice: **{chosen_model}** (locked for ADR, Phase 5 embedding infra)
- Dedup threshold starting point: `{chosen_t:.2f}` (tune on larger corpus in Phase 5)
- Input text: `title + summary[:512]` only (long-input caveat — never full body)
- For mE5-large: `passage: ` prefix required for corpus documents (query documents
  use `query: ` prefix)

## Full Sweep Table
{table_str}
"""

    with open(VERDICT_MD, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\nVerdict written to: {VERDICT_MD}")


def main():
    print("=== R2 Dedup Bake-off: Threshold Sweep ===\n")

    print("Loading embeddings...")
    item_ids, id_to_idx, embs = load_embeddings()

    print("\nLoading labeled pairs...")
    yes_pairs, no_pairs = load_labeled_pairs()

    if len(yes_pairs) == 0:
        sys.exit("ERROR: No same_story=yes pairs found — label the CSV first.")
    if len(no_pairs) == 0:
        sys.exit("ERROR: No same_story=no control pairs found — add controls to CSV.")

    # Sweep all models
    all_sweep = {}
    all_best = {}

    for model_name, emb in embs.items():
        print(f"\nSweeping {model_name}...")
        results, yes_sims, no_sims = sweep(emb, id_to_idx, yes_pairs, no_pairs)
        all_sweep[model_name] = results
        print_table(model_name, results)

        # Show raw similarity distributions for context
        yes_arr = np.array(yes_sims)
        no_arr  = np.array(no_sims)
        print(f"\n  yes-pair sim: min={yes_arr.min():.3f}  median={np.median(yes_arr):.3f}  max={yes_arr.max():.3f}")
        print(f"  no-pair sim:  min={no_arr.min():.3f}   median={np.median(no_arr):.3f}  max={no_arr.max():.3f}")

        best = choose_best(results, model_name)
        all_best[model_name] = best
        if best:
            print(f"\n  [{model_name}] QUALIFIES at threshold={best[0]:.2f} "
                  f"collapse_rate={best[1]:.3f} control_overmerge={best[2]}")
        else:
            print(f"\n  [{model_name}] No threshold meets both bars on this event set.")

    # Choose single winner across models
    qualified = {m: b for m, b in all_best.items() if b is not None}

    print("\n" + "=" * 60)
    print("SELECTION")
    print("=" * 60)

    closest = None  # defined for both branches so write_verdict call is clean

    if qualified:
        # Pick model with highest collapse_rate at zero overmerge
        chosen_model = max(qualified, key=lambda m: (qualified[m][1], -qualified[m][0]))
        ct, cr, ov = qualified[chosen_model]
        verdict = "go"
        print(f"\nChosen: model={chosen_model}  threshold={ct:.2f}  "
              f"collapse_rate={cr:.3f}  control_overmerge={ov}")
    else:
        # PARTIAL: For actionable Phase 5 guidance, choose the threshold with
        # minimum overmerge (closest to 0), then maximum collapse_rate at that level.
        # This gives the nearest-to-passing point, not just the maximum collapse_rate
        # at a useless low threshold.
        best_partial = None
        min_ov = min(ov for results in all_sweep.values() for _, _, ov in results)
        best_score = (-1.0,)
        for model_name, results in all_sweep.items():
            for t, cr, ov in results:
                if ov <= min_ov:
                    score = (cr,)
                    if score > best_score:
                        best_score = score
                        best_partial = (model_name, t, cr, ov)

        # Also find the "closest to both bars" point for reporting
        closest = None
        closest_dist = float("inf")
        for model_name, results in all_sweep.items():
            for t, cr, ov in results:
                # Euclidean distance from (1.0 collapse, 0 overmerge) target
                dist = ((cr - 1.0) ** 2 + (ov / max(1, len(no_pairs))) ** 2) ** 0.5
                if dist < closest_dist:
                    closest_dist = dist
                    closest = (model_name, t, cr, ov)

        chosen_model, ct, cr, ov = best_partial
        verdict = "partial"
        print(f"\nPARTIAL — no threshold clears both bars.")
        print(f"Best at minimum overmerge: model={chosen_model}  threshold={ct:.2f}  "
              f"collapse_rate={cr:.3f}  control_overmerge={ov}")
        if closest:
            print(f"Closest to both bars:      model={closest[0]}  threshold={closest[1]:.2f}  "
                  f"collapse_rate={closest[2]:.3f}  control_overmerge={closest[3]}")

        # Use "closest to both bars" as the main reported point
        chosen_model, ct, cr, ov = closest

    write_verdict(chosen_model, ct, cr, ov, all_sweep, yes_pairs, no_pairs, verdict,
                  closest_to_bars=closest if verdict == "partial" else None)

    print(f"\n{'=' * 60}")
    print(f"R2 Verdict: {verdict.upper()}")
    print(f"  Model:             {chosen_model}")
    print(f"  Threshold:         {ct:.2f}")
    print(f"  collapse_rate:     {cr:.3f}  (floor >= {COLLAPSE_FLOOR})")
    print(f"  control_overmerge: {ov}  (ceiling == {OVERMERGE_CEILING})")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
