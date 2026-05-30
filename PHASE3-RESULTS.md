# Phase 3 — The Gate: Results (2026-05-30)

**Goal (RQ3):** only spend an LLM call when a cheap signal says a pipeline is slow; show the gate
keeps the benefit while cutting LLM cost. File: `poc/gate.py`, threshold = observed latency > 50ms.

## Policy comparison over 8 pipelines
| Pipeline | orig | gate | rewrite | outcome |
|---|---|---|---|---|
| unneeded-sort-before-group | 68.0ms | FIRE | ok(1x) | adopt 68->27ms |
| unwind-then-group-sum | 301.9ms | FIRE | ok(1x) | adopt 302->191ms |
| lookup-then-late-match | 116.7ms | FIRE | ok(1x) | no gain (engine already pushes) |
| sort-then-group-first | 73.0ms | FIRE | ok(**2x**) | no gain (correct after retry) |
| sort-limit-topk | 22.0ms | skip | — | (gate skipped) |
| cheap-id-range | 0.2ms | skip | — | (gate skipped) |
| cheap-small-group | 0.5ms | skip | — | (gate skipped) |
| cheap-count | 0.3ms | skip | — | (gate skipped) |

| Policy | total latency | saved | LLM calls |
|---|---|---|---|
| baseline | 582.7ms | — | 0 |
| rewrite-all | 431.0ms | 26.0% | 8 |
| **gated** | **431.0ms** | **26.0%** | **4** |

**>>> The gate captured 100% of rewrite-all's benefit using 4/8 LLM calls (50% fewer).**

## RQ2 evidence — counterexample-guided recovery (live)
`sort-then-group-first` needed 2 attempts. Attempt 1 removed the `$sort`, but `$first` depends on
document order, so results changed; the verifier rejected it with a concrete diff
(`{_id:2032, topStatus:"delivered"}` present in original, absent in rewrite). Attempt 2 recovered,
keeping the sort with the rationale that `$first` is order-dependent. The verifier guaranteed no
incorrect rewrite was ever adopted.

## Findings
1. A cheap latency gate skips low-headroom pipelines at zero benefit loss, halving LLM cost here.
2. The benefit concentrates in a few high-headroom pipelines (the unnecessary `$sort`, the
   `$unwind`-elimination) -- consistent with Phases 1-2.
3. Threshold is a tunable knob (sensitivity analysis is future work); too-high a threshold would
   miss moderately-slow-but-improvable pipelines.
