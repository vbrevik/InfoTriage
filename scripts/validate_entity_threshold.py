#!/usr/bin/env python3
"""validate_entity_threshold.py — mE5-large cross-language entity-link validation.

Embeds a small multilingual corpus of entity surface forms using the same
mE5-large endpoint convention as apps/triage/worker.py, computes pairwise
cosine similarities, and recommends a LINK_THRESHOLD that separates
same-entity pairs from distinct pairs.

Usage:
    python scripts/validate_entity_threshold.py --corpus tests/fixtures/entity_validation_sample.json --report .planning/phases/999.3-entity-resolution-cross-language-coverage-and-mE5-large-re-validation/999.3-VERDICT.md

If LLM_BASE_URL is unreachable, the script degrades to deterministic synthetic
vectors so it still runs in CI.
"""
import argparse
import hashlib
import json
import math
import os
import urllib.request
from pathlib import Path


DEFAULT_CORPUS = {
    "same_pairs": [
        ["NATO", "НАТО"],
        ["Norway", "Norge"],
        ["Norway", "Норвегия"],
        ["United States", "США"],
        ["United States", "USA"],
        ["Ukraine", "Украина"],
        ["Zelensky", "Зеленский"],
    ],
    "distinct_pairs": [
        ["NATO", "Russia"],
        ["Norway", "Sweden"],
        ["Putin", "Zelensky"],
        ["USA", "China"],
        ["Oslo", "Beijing"],
    ],
}


def _deterministic_vector(text: str, dim: int = 1024) -> list[float]:
    """Return a deterministic synthetic vector for offline/CI runs."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for i in range(dim):
        # Use two bytes per dimension for reasonable resolution.
        byte_pair = digest[(i * 2) % len(digest) : ((i * 2) % len(digest)) + 2]
        value = int.from_bytes(byte_pair, "big") / 65535.0
        values.append(value)
    return values


def get_embedding(text: str, *, allow_synthetic: bool = False) -> tuple[list[float], bool]:
    """Embed a single text with mE5-large; fall back to synthetic vectors on failure.

    Returns a tuple of (vector, used_synthetic).
    """
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    key = os.environ.get("LLM_API_KEY", "omlx")
    body = json.dumps({
        "model": "intfloat/multilingual-e5-large",
        "input": f"query: {text}",
    }).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/embeddings",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)["data"][0]["embedding"], False
    except Exception as exc:
        if not allow_synthetic:
            raise RuntimeError(
                f"LLM endpoint unreachable ({exc}); re-run with --allow-synthetic or set LLM_BASE_URL"
            ) from exc
        print(f"WARN: LLM endpoint unreachable ({exc}); using synthetic vector for {text!r}")
        return _deterministic_vector(text), True


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_corpus(path: str) -> dict:
    """Load validation corpus from JSON or return the default corpus."""
    if not path:
        return DEFAULT_CORPUS
    p = Path(path)
    if not p.exists():
        print(f"WARN: corpus {path} not found; using default corpus")
        return DEFAULT_CORPUS
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate mE5-large entity-link threshold")
    parser.add_argument("--corpus", default="", help="Path to JSON corpus (optional)")
    parser.add_argument("--report", required=True, help="Path to markdown report output")
    parser.add_argument("--allow-synthetic", action="store_true", help="Allow synthetic vectors when LLM is unreachable")
    args = parser.parse_args()

    corpus = load_corpus(args.corpus)
    same_pairs = corpus.get("same_pairs", [])
    distinct_pairs = corpus.get("distinct_pairs", [])

    same_results: list[tuple[str, str, float]] = []
    distinct_results: list[tuple[str, str, float]] = []
    used_synthetic = False

    def embed(text: str) -> list[float]:
        nonlocal used_synthetic
        vec, synthetic = get_embedding(text, allow_synthetic=args.allow_synthetic)
        if synthetic:
            used_synthetic = True
        return vec

    for left, right in same_pairs:
        sim = cosine_similarity(embed(left), embed(right))
        same_results.append((left, right, sim))

    for left, right in distinct_pairs:
        sim = cosine_similarity(embed(left), embed(right))
        distinct_results.append((left, right, sim))

    min_same = min((sim for _, _, sim in same_results), default=0.0)
    max_distinct = max((sim for _, _, sim in distinct_results), default=0.0)

    if min_same > max_distinct:
        recommendation = (min_same + max_distinct) / 2.0
    else:
        recommendation = 0.85

    same_lines = "\n".join(
        f"- {left} / {right}: {sim:.4f}" for left, right, sim in same_results
    )
    distinct_lines = "\n".join(
        f"- {left} / {right}: {sim:.4f}" for left, right, sim in distinct_results
    )

    synthetic_note = "\n**WARNING:** Synthetic vectors were used because the LLM endpoint was unreachable. The threshold below is NOT derived from real mE5-large embeddings.\n" if used_synthetic else ""

    report = f"""# 999.3 Entity Resolution Threshold Validation (mE5-large)

## Method
Surface forms were embedded with `intfloat/multilingual-e5-large` using the
`query:` prefix convention. Pairwise cosine similarities were computed for
cross-language same-entity pairs and distinct-entity pairs.
{synthetic_note}
## Same-Entity Pairs (Cross-Language)
{same_lines}

## Distinct Pairs
{distinct_lines}

## Verdict
- Minimum similarity for same entities: **{min_same:.4f}**
- Maximum similarity for distinct entities: **{max_distinct:.4f}**
- Recommended `LINK_THRESHOLD`: **{recommendation:.4f}**

## Note
The current Phase 8 implementation uses exact normalised-name matching for
entity identity. This threshold is reserved for future similarity-based
clustering / cross-language alias merging.
"""

    out_path = Path(args.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Validation complete. Threshold {recommendation:.4f}. Report: {out_path}")


if __name__ == "__main__":
    main()
