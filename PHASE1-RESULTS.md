# Phase 1 — Measurement Harness: Results (2026-05-30)

**Goal:** validate the scientific instrument (run-both → verify-equivalence → time-both) before
any LLM is involved. **Outcome: PASS, 4/4 cases behave as expected.**

## Setup
- Isolated throwaway `mongod` on `:47017`, dbpath `poc/mongo-data` (NOT the user's `l2` instance on :50251).
- Synthetic data: 5,000 customers + 200,000 orders, no secondary indexes (realistic slowness). Seed=42.
- `poc/harness.py` + `poc/pipelines.py` + `poc/gen_data.py`, Python 3.11 venv + pymongo 4.17.

## Results
| Case | Type | Equivalence verdict | Speedup |
|---|---|---|---|
| predicate-pushdown | correct | EQUIVALENT (pass) | 0.99x |
| project-before-group | correct | EQUIVALENT (pass) | 1.00x |
| drop-unneeded-sort | correct | EQUIVALENT (pass) | **2.65x** (70.0→26.4 ms) |
| wrong-rewrite-changes-filter | incorrect | NOT-EQUIVALENT (pass, caught) | — |

## Early findings (useful for the paper)
1. **MongoDB's optimizer already does textbook rewrites** (e.g. pushing `$match` before `$lookup`),
   so naive reorderings score ~1x. The LLM's value must be rewrites the engine does NOT do.
2. **Eliminating unnecessary blocking work** (a `$sort` whose order `$group` ignores) is a real,
   2.65x win the optimizer won't make on its own — a promising rewrite category.
3. The empirical verifier reliably catches a silently-incorrect rewrite (negative control).

## Validated for Phase 2
- LLM access: gateway works via **`api-key` header** (Azure APIM), model `claude-sonnet-4-5`.
  Key in `poc/.env` (git-ignored).

## Honest limitation (carry into the paper)
Equivalence is empirical over the loaded corpus, not a formal proof; a rewrite diverging only on
data absent from the corpus would not be caught.

## Teardown
`mongosh --port 47017 --eval 'db.getSiblingDB("poc_aggrewrite").dropDatabase()'` then kill pid in
`poc/mongo-data/mongod.log`, or just `rm -rf poc/mongo-data` after stopping that mongod.
