# Spark model benchmark — GSD-style multistep agentic tasks (2026-07-09)

Driver: `opencode run --model gateway/spark` (Mac gateway :4000 → Spark vLLM :8000), one model hot at a time.
Tasks run in isolated copies of the InfoTriage repo; 900s timeout per task.

## Tasks

- **t1-map** — codebase mapping (gsd-codebase-mapper style): explore `libs/store`, write STORE-MAP.md with protocol methods, txn hygiene mechanism, blob test coverage, all cited.
- **t2-bugfix** — planted bug (gsd-executor style): `_inmemory.py list_items` filter matched only first source type → 2 tests failing; find root cause, minimal source fix, re-run to green.
- **t3-parity** — cross-file audit (gsd-verifier style): compare InMemoryStore/PostgresStore vs Store protocol; list protocol methods NOT exercised by `test_store_contract.py`. Ground truth: put_enrichment, get_enrichment, put_embedding, find_near_duplicate.

## Results

| | Qwen3.6-35B-A3B FP8 (MoE) | Qwen3-Coder-Next NVFP4 (80B MoE) | Qwen3.6-27B NVFP4 (dense, thinking) |
|---|---|---|---|
| t1-map | ✅ 488s — most thorough (found txn regression test, idle-timeout backstop, UAT ref) | ✅ 405s — correct, concise | ⚠️ TIMEOUT 901s — artifact written, high quality, but overran |
| t2-bugfix | ✅ 409s — minimal 1-line fix, 13/13 green | ✅ 324s — minimal 1-line fix, 13/13 green | ❌ TIMEOUT 900s — still exploring, no fix applied |
| t3-parity | ✅ 215s — exactly correct (4 methods) | ❌ 198s — WRONG: claimed only a hallucinated `cursor()` method untested, missed all 4 real gaps | ✅ 732s — exactly correct + most nuanced (flagged init_schema as partial) |
| gen tokens (t1/t2/t3) | 10922 / 4241 / 2740 | 5229 / 1140 / 1993 | 3230* / 1566* / 3652 (*truncated by timeout) |
| tool-call errors | 0 | 0 | 0 |
| score | **3/3** | 2/3 | 1/3 (2 timeouts) |

## Findings

1. **Qwen3.6-27B dense is the wrong shape for agentic work on the GB10.** The box is bandwidth-bound (~273 GB/s); a dense 27B moves ~15 GiB of weights per token vs ~2 GiB for the 3B-active MoEs. Effective wall speed was ~4–8× slower — it timed out on 2 of 3 tasks while mid-loop. Its *reasoning quality* is good (t3 was the best answer of the three; the t1 artifact it did write was well-structured and correctly cited), but a thinking + dense model on this hardware cannot finish real multistep loops in reasonable time.
2. **Qwen3.6-35B-A3B was the only 3/3** — thorough, correct, no tool errors. This partially rehabilitates it after the earlier GSD reasoning-bench loss (single-shot hard reasoning ≠ grounded multistep agentic work).
3. **Coder-Next is fastest and fine at code fixing, but made a real audit error**: on t3 it fabricated a `cursor()` protocol method and declared the 4 genuinely uncovered methods covered. For verification/audit-type GSD steps its conclusions need checking.
4. **Tool-calling was clean across all three** (0 malformed calls in opencode loops) — the parser configs (qwen3_xml/qwen3_coder/qwen3_coder + reasoning qwen3) are all healthy.

## Role recommendation

- **Agentic coding (opencode/GSD executor): keep Coder-Next** — fastest, correct on code work.
- **Audit/verify/mapping GSD steps (verifier, parity checks, codebase mapping): prefer Qwen3.6-35B** — only model with all-correct results.
- **Qwen3.6-27B: niche only** — highest per-answer quality on analysis, but only viable for non-interactive, no-deadline single questions; not for agentic loops. Do not make it a default profile.

## Infra notes (getting 27B to work at all)

- `nvidia/Qwen3.6-27B-NVFP4` (ModelOpt MIXED_PRECISION FP8+NVFP4) **does not load** on Spark's vLLM build (gemma4-0505-cu130, 0.20.2rc1.dev49): `RuntimeError: narrow start(0)+length(17408) exceeds 8704` in qwen3_5 down_proj loading. Kept on disk for a future image upgrade.
- Working checkpoint: `sakamakismile/Qwen3.6-27B-NVFP4` (compressed-tensors nvfp4-pack-quantized) — loads clean, reasoning parser splits correctly, tool calls well-formed. Profile: `vllm-qwen3.6-27b.conf`, warm load ~5.5 min.
- Download saga: HF CDN direct from Spark stalls; `hf download` falsely reported SUCCESS on an incomplete blob; sha256 mismatch after mixed resume chains. Fix: 8-way ranged curl on the Mac, sha256 verify (matched d8e5bf67…), rsync over LAN to Spark blob path + manual snapshot symlink.
