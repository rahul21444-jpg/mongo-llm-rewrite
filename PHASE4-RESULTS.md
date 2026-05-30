# Phase 4 — Predicate-Parameterized Rewrite Cache: Results (2026-05-30)

**Goal (RQ4 — cost amortization):** make the LLM cost per query approach zero by paying the LLM
once per query *shape* and serving repeats (different predicate values) from a cache.
Architecture: a transparent proxy intercepts the client's naive query, serves an equivalent faster
one; the client's query text never changes. File: `poc/rewrite_cache.py`.

## Result
Same pipeline shape, four different `status` predicate values:
| query | served by | rewritten | verified equivalent |
|---|---|---|---|
| status=cancelled | LLM | yes | True |
| status=delivered | CACHE | yes | True |
| status=shipped | CACHE | yes | True |
| status=pending | CACHE | yes | True |

**4 queries served with 1 LLM call + 3 cache hits -> 75% served with ZERO LLM cost.**
As a query shape repeats across a real workload, the LLM cost per query -> ~0.

## How it works
1. Normalize the query to a TEMPLATE by replacing literal `$match` values with placeholders (`<<P0>>`).
2. Cache key = template; cached value = the structural rewrite, also parameterized.
3. Cache hit -> instantiate the cached rewrite with the new query's literals (microseconds, no LLM).
4. Each served rewrite is STILL verified equivalent for its own predicate value (defense-in-depth).
5. The parameterized template doubles as a **developer advisory** ("send this faster query directly").

## Honest caveats (carry into the paper)
- Safe ONLY for structural/algebraic rewrites (valid for any predicate value); cost-based rewrites
  (index choice that depends on selectivity) must NOT be cached blindly.
- Caching reuses an equivalence verified on one value for other values -> amplifies the empirical-
  verification risk. Mitigation: periodic re-verification on live results -- which is exactly the
  drift-robustness problem from the Postgres/MSCN backbone (the threads connect).
