# Phase 2 — LLM Rewriter: Results (2026-05-30)

**Goal:** plug the LLM (claude-sonnet-4-5) into the Phase-1 harness and measure whether it can
produce *verified* equivalent-but-faster rewrites of slow aggregation pipelines (RQ1).
Files: `poc/rewriter.py`, `poc/corpus.py`, `poc/llm_client.py`.

## Results (verifier-guarded; 4/4 valid, 0 incorrect accepted)
| Pipeline | LLM rewrite | Attempts | Speedup |
|---|---|---|---|
| unneeded-sort-before-group | removed unnecessary `$sort` | 1 | **2.51x** (65.6->26.2 ms) |
| unwind-then-group-sum | `$unwind`+`$group` -> `$sum` over `items.qty` | 1 | **1.59x** (304->192 ms) |
| lookup-then-late-match | pushed `$match` before `$lookup` | 1 | 1.00x (optimizer already does it) |
| sort-limit-topk | left UNCHANGED (already optimal) | 1 | — (correctly not over-optimized) |

## Findings
1. The LLM independently rediscovered the 2.51x unnecessary-`$sort` win and found a non-obvious
   `$unwind`-elimination (1.59x) — both rewrites the MongoDB optimizer does NOT make on its own.
2. It correctly recognized an already-optimal top-k pipeline and returned it unchanged — it did NOT
   fall into the semantics trap of removing the result-defining `$sort`.
3. Textbook pushdown (`$match` before `$lookup`) yields ~1x because the engine already does it,
   reinforcing the Phase-1 finding: LLM value lies in non-obvious rewrites.

## Known gap (to close next)
All four succeeded on attempt 1, so the **counterexample-guided retry loop is implemented but not yet
exercised live** — we have not yet watched the LLM *recover* from a rejected rewrite. The Phase-1
negative control proves the verifier catches wrong rewrites; demonstrating recovery needs a harder /
larger corpus. RQ2 (verification + recovery rate) needs that bigger corpus.

## Config
- Model: claude-sonnet-4-5 (LLM gateway), `api-key` header, temperature=0 (greedy, reproducible).
- Verifier: empirical multiset equivalence over the loaded 200k-doc corpus (statistical, not proof).
