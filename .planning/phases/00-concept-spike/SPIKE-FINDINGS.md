> **NOTE (carry-forward for 00-07 closeout):** This file currently holds only the auto-generated
> divergence note below. Plan **00-07** is the owner — it rewrites this file with the full per-unknown
> R1–R5 verdicts and folds the divergence below into ADR-006 as a Phase-8 re-validation risk.

## R3/R2 Model Divergence Note

R3 embedded entities with `BAAI/bge-m3` (source: fallback-bge-m3, the R3 default — R3 ran before R2 decided).
R2-VERDICT.md records **`mE5-large` @ 0.84** as the chosen embedding model (the `similarity` string the
R3 auto-parser captured was a misparse of R2-VERDICT.md, not the real choice).
These differ — the R3 entity-link threshold (0.85) was validated on bge-m3 vectors, **not** the chosen
mE5-large. **Phase 8 must re-validate entity linking on mE5-large vectors before production.**
