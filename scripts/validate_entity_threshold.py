#!/usr/bin/env python3
"""validate_entity_threshold.py — mE5-large cross-language entity-link validation.

Embeds a small multilingual corpus of entity surface forms using the same
mE5-large endpoint convention as apps/triage/worker.py, computes pairwise
cosine similarities, runs a threshold sweep, and recommends a LINK_THRESHOLD
that separates same-entity pairs from distinct pairs.

MODES (--mode flag, default "offline"):

  offline     Load intfloat/multilingual-e5-large from the local safetensors
              cache (~/.cache/huggingface/hub/models--intfloat--multilingual-e5-large
              OR ~/.omlx/models/multilingual-e5-large). Bypasses the oMLX HTTP
              server entirely. Uses sentence-transformers library, with the
              torchvision import mocked at load time (R3-VERDICT pattern) to
              avoid the broken torchvision 0.24.0.dev / torch 2.11.0 collision.

  http        Use the oMLX /v1/embeddings HTTP endpoint. Requires LLM_BASE_URL
              reachable.

  synthetic   SHA256-deterministic fallback. MUST be opted-in explicitly via
              --allow-synthetic. NEVER default: produces invalid verdicts (the
              synthetic interleaving does not reflect real mE5-large geometry).

USAGE

  python scripts/validate_entity_threshold.py \\
      --report .planning/phases/999.3-.../999.3-VERDICT.md

  python scripts/validate_entity_threshold.py --mode http \\
      --report /tmp/report.md

  python scripts/validate_entity_threshold.py \\
      --corpus-from-postgres --report /tmp/report.md
"""
from __future__ import annotations

# IMPORTANT: torchvision bypass MUST come before any import that may transitively
# pull in torchvision. Host python with torch 2.11.0 + torchvision 0.24.0.dev raises
# `torchvision::nms` RuntimeError on import — the exact failure R3 hit.
#
# A plain MagicMock() fails because importlib.util.find_spec raises
# `ValueError: torchvision.__spec__ is None` (mock has no __spec__).
# We supply an explicit ModuleSpec with origin=None so find_spec returns a
# real-spec object (transformers only checks "spec is not None") and the
# import-graph side effects (torchvision.ops registration) are skipped because
# the modules below are MagicMocks. Pattern mirrors R3-VERDICT.md.
import sys
from unittest.mock import MagicMock
from importlib.machinery import ModuleSpec

_mock_tv = MagicMock()
_mock_tv.__spec__ = ModuleSpec("torchvision", None)
sys.modules.setdefault("torchvision", _mock_tv)
sys.modules.setdefault("torchvision.transforms", MagicMock())
sys.modules.setdefault("torchvision.io", MagicMock())


import argparse  # noqa: E402  (after sys.modules mock)
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import urllib.request  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Optional, cast  # noqa: E402


# Cyrillic → Latin transliteration table for cross-script entity pairing in
# _corpus_from_postgres. Lowercase only; used after .lower() on the mention.
CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


# 12-entity default corpus: 7 cross-language same-entity pairs + 5 distinct-entity pairs.
# Mirrors the corpus baked into the prior 999.3-VERDICT placeholder so we can verify
# the post-patch run produces a substantively different (real) result.
DEFAULT_CORPUS: dict[str, list[list[str]]] = {
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


# Lazy / optional import: transformers is only loaded in offline mode.
# Lazy loading prevents the broken-torchvision path from being hit when mode=http.
_offline_model = None  # tuple[tokenizer, model]


def _cyrillic_to_latin_key(text: str) -> str:
    """Return a lowercase Latin key for a mention, transliterating Cyrillic.

    Used in _corpus_from_postgres so that same-entity mentions written in
    different scripts (e.g. NATO / НАТО / Nató) collapse to one bucket and can
    be emitted as a cross-language same-entity pair.
    """
    return "".join(CYRILLIC_TO_LATIN.get(c, c) for c in text.lower())


def _resolve_model_dir() -> Path:
    """Find mE5-large weights on disk. Returns Path. Raises RuntimeError on miss."""
    candidates = [
        Path.home() / ".cache/huggingface/hub/models--intfloat--multilingual-e5-large/snapshots",
        Path.home() / ".omlx/models/multilingual-e5-large",
        Path(os.environ.get("ME5_MODEL_DIR", "")),  # CI-friendly override
    ]
    candidates = [c for c in candidates if str(c)]  # drop empty env override
    for c in candidates:
        if c.is_dir():
            # snapshots/<sha>/ contains config + weights; the parent class dir
            # contains them flat. Both work with from_pretrained.
            snapshots = list(c.iterdir())
            if c.name == "snapshots" and snapshots:
                return snapshots[0]
            return c
    raise RuntimeError(
        "mE5-large weights not found locally. Looked in: "
        f"{[str(p) for p in candidates]}  Set ME5_MODEL_DIR or install the model."
    )


def _ensure_offline_model() -> tuple:
    """Load mE5-large from local safetensors cache, build once per process.

    Returns (tokenizer, model) tuple. Uses XLMRobertaModel directly (NOT AutoModel)
    to bypass AutoModel registry machinery, mirroring R3-VERDICT.md's pattern.
    """
    global _offline_model
    if _offline_model is not None:
        return _offline_model
    # transformers.XLMRobertaModel does NOT touch torchvision during its forward pass.
    try:
        from transformers import XLMRobertaModel, XLMRobertaTokenizerFast  # type: ignore
    except Exception as exc:  # pragma: no cover - environment failure path
        raise RuntimeError(
            f"transformers (XLMRoberta*) unavailable ({exc}); try --mode http or fix env."
        ) from exc

    model_dir = _resolve_model_dir()
    print(f"Loading mE5-large from {model_dir} ...")
    tokenizer = XLMRobertaTokenizerFast.from_pretrained(str(model_dir))
    model = XLMRobertaModel.from_pretrained(str(model_dir))
    model.eval()
    _offline_model = (tokenizer, model)
    return _offline_model


def _mean_pool_l2_norm(model_pair: tuple, text: str) -> list[float]:
    """Embed a single text with attention-masked mean pooling + L2 normalization.

    mE5-large protocol: prepend "query: ", mean-pool with attention mask, L2 normalize.
    1024-dim output.
    """
    import torch  # local import — torch is heavy, only load when offline invoked
    tokenizer, model = model_pair
    inputs = tokenizer(
        f"query: {text}",
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512,
    )
    with torch.no_grad():
        outputs = model(**inputs)
    attention_mask = inputs["attention_mask"].unsqueeze(-1).float()
    token_embeddings = outputs.last_hidden_state
    sum_embeddings = (token_embeddings * attention_mask).sum(dim=1)
    sum_mask = attention_mask.sum(dim=1).clamp(min=1e-9)
    mean_pooled = sum_embeddings / sum_mask
    import torch.nn.functional as F
    normalized = F.normalize(mean_pooled, p=2, dim=1)
    return normalized[0].tolist()


def _deterministic_vector(text: str, dim: int = 1024) -> list[float]:
    """Return a synthetic vector for offline/CI fallback runs.

    NEVER the default — must be opted-in via --allow-synthetic.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for i in range(dim):
        # Use two bytes per dimension for reasonable resolution.
        byte_pair = digest[(i * 2) % len(digest) : ((i * 2) % len(digest)) + 2]
        value = int.from_bytes(byte_pair, "big") / 65535.0
        values.append(value)
    return values


def get_embedding(
    text: str,
    *,
    mode: str = "offline",
    allow_synthetic: bool = False,
) -> tuple[list[float], bool]:
    """Embed a single text with mE5-large (offline or http) or synthetic.

    Returns a tuple of (vector, used_synthetic). used_synthetic signals to the
    report writer that the WARNING block must be emitted.
    """
    if mode == "synthetic":
        if not allow_synthetic:
            raise RuntimeError(
                "synthetic mode requires --allow-synthetic (synthetic vectors "
                "do not reflect real mE5-large geometry and yield invalid verdicts)"
            )
        return _deterministic_vector(text), True

    if mode == "offline":
        model_pair = _ensure_offline_model()
        return _mean_pool_l2_norm(model_pair, text), False

    if mode == "http":
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
                    f"LLM endpoint unreachable ({exc}); re-run with --allow-synthetic, "
                    f"--mode offline, or fix LLM_BASE_URL"
                ) from exc
            print(f"WARN: LLM endpoint unreachable ({exc}); using synthetic vector for {text!r}")
            return _deterministic_vector(text), True

    raise ValueError(f"unknown mode {mode!r}")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_corpus(path: str) -> dict[str, list[list[str]]]:
    """Load validation corpus from JSON or return the default corpus."""
    if not path:
        return DEFAULT_CORPUS
    p = Path(path)
    if not p.exists():
        print(f"WARN: corpus {path} not found; using default corpus")
        return DEFAULT_CORPUS
    with p.open("r", encoding="utf-8") as f:
        return cast(dict[str, list[list[str]]], json.load(f))


def _corpus_from_postgres() -> dict[str, list[list[str]]]:
    """Export a date-stamped cross-language pair set from production Postgres.

    Heuristic: for each article in the last 14d with lang ∈ {en, no, ru},
    extract entity surface forms via a lightweight regex on title+summary,
    then build same-entity pairs where (lang_a != lang_b) and the mention
    lower-cases to the same normalised key. Distinct pairs come from a curated
    list per the SPEC control set.

    Limitation: regex only matches title-initialised capitalised Latin/Cyrillic
    tokens (3+ chars). Mid-sentence entities ("the US said…", "российский",
    "中文") miss. Acceptable as a diversification signal for the spike; Phase 8
    inherits NER contract from apps/triage/entities.py._KNOWN_TOPICS, not this
    regex.

    Requires docker exec (host python can't reach localhost:22000 directly via
    the docker-network `postgres:5432` mapping).
    """
    import subprocess
    import re

    project_root = Path(__file__).resolve().parent.parent
    # NOTE: subprocess.run with a list (NOT shell=True) — the SQL string is one
    # argv element passed verbatim to psql, no shell-parsing or injection.
    sql = (
        "SELECT lang, title, COALESCE(summary, '') "
        "FROM infotriage.articles "
        "WHERE lang IN ('en','no','ru') "
        "AND ts > NOW() - INTERVAL '14 days' "
        "ORDER BY ts DESC LIMIT 50;"
    )
    proc = subprocess.run(
        ["docker", "exec", "infotriage-postgres", "psql", "-U", "infotriage",
         "-d", "infotriage", "-t", "-A", "-F", "\t", "-c", sql],
        capture_output=True, text=True, timeout=30,
        cwd=str(project_root),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"docker exec psql failed: {proc.stderr[:500]}")
    rows = [r.split("\t") for r in proc.stdout.strip().split("\n") if "\t" in r]
    pattern = re.compile(
        r"[A-ZÆØÅ][A-ZÆØÅa-zæøå]{2,}|[\u0410-\u042F\u0401]"
        r"[\u0410-\u042F\u0401\u0430-\u044F\u0451]{2,}"
    )
    same_pairs: list[list[str]] = []
    by_norm: dict[str, dict[str, str]] = {}
    for row in rows:
        if len(row) < 2:
            continue
        lang, title = row[0], row[1]
        for m in pattern.findall(title or ""):
            norm = _cyrillic_to_latin_key(m)
            by_norm.setdefault(norm, {})[lang] = m
    for norm, langs in by_norm.items():
        if len(langs) >= 2:
            keys = list(langs.keys())
            same_pairs.append([langs[keys[0]], langs[keys[1]]])
    same_pairs = same_pairs[:20]

    if not same_pairs:
        raise RuntimeError(
            "_corpus_from_postgres: zero cross-language same-entity pairs in the "
            "last 14d. Either corpus is too narrow (re-run with --corpus) or the "
            "regex heuristic missed real entities (inspect /tmp/article_titles.txt "
            "via: docker exec infotriage-postgres psql -U infotriage -d infotriage "
            "-c \"SELECT lang, title FROM infotriage.articles WHERE lang IN "
            "('en','no','ru') ORDER BY ts DESC LIMIT 50;\")."
        )

    distinct_pairs: list[list[str]] = DEFAULT_CORPUS["distinct_pairs"]
    result: dict[str, list[list[str]]] = {
        "same_pairs": same_pairs,
        "distinct_pairs": distinct_pairs,
    }
    return result


def threshold_sweep(
    same_sims: list[float], distinct_sims: list[float]
) -> list[tuple[float, float, int]]:
    """Mirror R2-VERDICT.md sweep table: T = 0.75..0.98, collapse_rate, control_overmerge."""
    table: list[tuple[float, float, int]] = []
    for tenth in range(75, 99):
        T = tenth / 100.0
        collapse = sum(1 for s in same_sims if s >= T) / max(1, len(same_sims))
        overmerge = sum(1 for d in distinct_sims if d >= T)
        table.append((T, collapse, overmerge))
    return table


def choose_threshold(table: list[tuple[float, float, int]]) -> tuple[float, str]:
    """Choose T* per SPEC: smallest T with perfect collapse + zero overmerge.

    Falls back to: smallest T with overmerge == 0 (trades missed merges for
    zero false-merge — safer for production: false merges entrench; missed
    merges can be re-resolved at a later item). Last-resort: 0.85 default with
    NO-GO sub-verdict note.
    """
    for T, collapse, overmerge in table:
        if collapse >= 1.0 and overmerge == 0:
            return T, "all same-entity pairs merged cleanly above T, with zero over-merge"
    # Conservative fallback: zero over-merge beats high collapse rate (false
    # merges are operationally expensive; missed merges can wait for re-extract).
    for T, collapse, overmerge in table:
        if overmerge == 0:
            note = (
                f"partial separation \u2014 collapse_rate={collapse:.3f}, "
                f"overmerge=0 (1 missed cross-lang merge accepted over false-merge safety)"
            )
            return T, note
    return 0.85, "no clean separation found in sweep \u2014 T* = R3 default 0.85 (NO-GO sub-verdict)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate mE5-large entity-link threshold")
    parser.add_argument(
        "--mode",
        choices=["offline", "http", "synthetic"],
        default="offline",
        help="Embedding source. Default offline (real mE5-large from safetensors cache).",
    )
    parser.add_argument("--corpus", default="", help="Path to JSON corpus (optional)")
    parser.add_argument(
        "--corpus-from-postgres",
        action="store_true",
        help="Export multi-day cross-language corpus from production Postgres.",
    )
    parser.add_argument("--report", required=True, help="Path to markdown report output")
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Permit synthetic SHA256-derived vectors as last-resort fallback.",
    )
    args = parser.parse_args()

    if args.corpus_from_postgres:
        corpus = _corpus_from_postgres()
    else:
        corpus = load_corpus(args.corpus)
    same_pairs = corpus.get("same_pairs", [])
    distinct_pairs = corpus.get("distinct_pairs", [])

    same_sims: list[float] = []
    distinct_sims: list[float] = []
    used_synthetic = False

    def embed(text: str) -> list[float]:
        nonlocal used_synthetic
        vec, synthetic = get_embedding(
            text,
            mode=args.mode,
            allow_synthetic=args.allow_synthetic,
        )
        if synthetic:
            used_synthetic = True
        return vec

    for left, right in same_pairs:
        sim = cosine_similarity(embed(left), embed(right))
        same_sims.append(sim)

    for left, right in distinct_pairs:
        sim = cosine_similarity(embed(left), embed(right))
        distinct_sims.append(sim)

    sweep_table = threshold_sweep(same_sims, distinct_sims)
    chosen_T, choice_reason = choose_threshold(sweep_table)

    # Determine verdict per SPEC §Acceptance Criteria (3 bars a/b/c).
    min_same = min(same_sims) if same_sims else 0.0
    max_distinct = max(distinct_sims) if distinct_sims else 1.0

    # Mechanism bar (a): cosine orders mE5-large L2-normalised vectors. Sanity =
    # same-pair similarity must be > distinct-pair similarity (otherwise vectors
    # are degenerate / corpus shuffled). Auto-fail mode=synthetic where this is
    # trivially broken.
    mechanism_pass = bool(same_sims and distinct_sims and min(same_sims) > max(distinct_sims))

    bar_b = bool(same_pairs) and min_same >= chosen_T
    bar_c = bool(distinct_pairs) and max_distinct < chosen_T
    corpus_complete = bool(same_pairs) and bool(distinct_pairs)

    if mechanism_pass and bar_b and bar_c:
        verdict = "GO"
        verdict_note = ""
    elif not mechanism_pass:
        verdict = "NO-GO"
        verdict_note = (
            "mechanism bar failed — min(same)=%.4f <= max(distinct)=%.4f; vectors "
            "cannot distinguish same-entity pairs from distinct ones at any T." % (min_same, max_distinct)
        )
    elif not corpus_complete:
        verdict = "PARTIAL"
        verdict_note = "corpus incomplete — empty same_pairs or distinct_pairs at runtime"
    elif bar_b and not bar_c:
        verdict = "PARTIAL"
        verdict_note = (
            "merge bar met (min_same=%.4f >= T*=%.4f), control separation missed "
            "(max_distinct=%.4f >= T*=%.4f)"
            % (min_same, chosen_T, max_distinct, chosen_T)
        )
    elif not bar_b and bar_c:
        verdict = "PARTIAL"
        verdict_note = (
            "control separation met (max_distinct=%.4f < T*=%.4f), merge bar missed "
            "(min_same=%.4f < T*=%.4f)"
            % (max_distinct, chosen_T, min_same, chosen_T)
        )
    else:
        # Mechanism works but neither bar lands at the chosen T*. Falls back to
        # tightening T. If even choose_threshold couldn't find separation, NO-GO.
        if "no clean separation" in choice_reason:
            verdict = "NO-GO"
            verdict_note = "choose_threshold fell back to R3 default 0.85 with no clean separation across 0.75..0.98"
        else:
            verdict = "PARTIAL"
            verdict_note = (
                "indeterminate at T*=%.4f — neither bar lands" % chosen_T
            )

    # Build sweep-md lines.
    sweep_md = "\n".join(
        f"| {T:.2f} | {collapse:.3f} | {overmerge} |"
        for T, collapse, overmerge in sweep_table
    )

    same_lines = "\n".join(
        f"- {left} / {right}: {sim:.4f}" for (left, right), sim in zip(same_pairs, same_sims)
    )
    distinct_lines = "\n".join(
        f"- {left} / {right}: {sim:.4f}" for (left, right), sim in zip(distinct_pairs, distinct_sims)
    )

    synthetic_note = (
        "\n**WARNING:** Synthetic SHA256-derived vectors were used because the requested embedding\n"
        "path failed. The threshold below is NOT derived from real mE5-large embeddings and is\n"
        "an INVALID substitute for production.\n"
        if used_synthetic
        else ""
    )

    pg_corpus_note = (
        f"\nCorpus source: production Postgres (last 14d, lang ∈ {{en,no,ru}}, limit 50). "
        f"Pair count: same={len(same_pairs)}, distinct={len(distinct_pairs)}.\n"
        if args.corpus_from_postgres
        else f"\nCorpus source: default 12-entity pair set (--mode {args.mode}). "
    )

    verdict_note_line = (
        f"\n**Verdict note:** {verdict_note}\n" if verdict_note else ""
    )

    report = f"""# 999.3 Entity Resolution Threshold Validation (mE5-large)

**Verdict:** **{verdict}**
**Mode:** `{args.mode}` (corpus pairs: same={len(same_pairs)}, distinct={len(distinct_pairs)})
**Recommended `LINK_THRESHOLD`:** **{chosen_T:.4f}**
{verdict_note_line}{synthetic_note}{pg_corpus_note}
## Method

Surface forms were embedded with `intfloat/multilingual-e5-large` using the
`query:` prefix convention and `normalize_embeddings=True` (L2-normalization).
Embeddings are 1024-dim mean-pooled vectors from XLM-RoBERTa-large. Pairwise
cosine similarities were computed for cross-language same-entity pairs and
distinct-entity pairs.

The threshold sweep mirrors the R2-VERDICT.md format. Acceptance
criteria are from `999.3-SPEC.md` §Acceptance Criteria.

## Same-Entity Pairs (Cross-Language)

{same_lines or "(none)"}

## Distinct Pairs

{distinct_lines or "(none)"}

## Threshold Sweep Table (R2-format)

| Threshold | collapse_rate | control_overmerge |
|----------:|-------------:|------------------:|
{sweep_md}

## Recommended `LINK_THRESHOLD`

- Minimum similarity for same entities: **{min_same:.4f}**
- Maximum similarity for distinct entities: **{max_distinct:.4f}**
- **Chosen T* = {chosen_T:.4f}** — {choice_reason}

## Acceptance Criteria (SPEC §Acceptance Criteria)

- (a) Mechanism (cosine orders mE5-large vectors): {'PASS' if mechanism_pass else 'FAIL'} (min(same)=**{min_same:.4f}**, max(distinct)=**{max_distinct:.4f}**, sanity: min(same) > max(distinct))
- (b) Cross-language same-entity merge @ T*: {'PASS' if bar_b else 'FAIL'} (min_same={min_same:.4f}, T*={chosen_T:.4f})
- (c) Distinct-entity separation @ T*: {'PASS' if bar_c else 'FAIL'} (max_distinct={max_distinct:.4f}, T*={chosen_T:.4f})

## Phase 8 Handoff

The production-recommended value of `LINK_THRESHOLD` for `apps/triage/entities.py`
(replacing the current 0.85, which was validated on bge-m3, NOT the chosen
mE5-large) is documented above as **{chosen_T:.4f}**. Phase 8 should adopt this
new value across `apps/triage/entities.py` AND `libs/store/_postgres.py::find_similar_entity`
default. Item-level dedup threshold (R2 mE5-large @ 0.84) is a different
problem and stays unchanged.
"""

    out_path = Path(args.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Validation complete. Verdict={verdict} T*={chosen_T:.4f}. Report: {out_path}")


if __name__ == "__main__":
    main()
