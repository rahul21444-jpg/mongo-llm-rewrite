# Performance-Gated, Cost-Amortized LLM Rewriting of MongoDB Aggregation Pipelines

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20456038.svg)](https://doi.org/10.5281/zenodo.20456038)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Reference implementation and experiments for the paper *"Performance-Gated, Cost-Amortized LLM
Rewriting of MongoDB Aggregation Pipelines with Verified Equivalence"* (Rahul Sharma, 2026).

A transparent rewrite proxy that turns slow MongoDB aggregation pipelines into faster, **verified**
equivalent ones. The LLM is **gated** (only invoked on slow pipelines) and its cost is **amortized**
by a predicate-parameterized rewrite **cache**, so the per-query LLM cost approaches zero. Every
served rewrite is checked for equivalence against the engine, so an incorrect rewrite can never be
served.

## Results

On a 200,000-document synthetic workload (and MongoDB's real `sample_mflix`):

| Property | Result |
|----------|--------|
| Verified rewrite speedups | up to **2.51×** |
| Incorrect rewrites served | **0** (verifier-guarded, with counterexample-guided retry) |
| Gate vs. rewrite-everything | **100% of the benefit at half the LLM calls** |
| Cache (per-query LLM cost) | **→ 0** — the LLM is paid once per query *shape* |

**Honest negative finding:** MongoDB's aggregation optimizer already performs the textbook rewrites
(e.g. predicate pushdown), so the LLM adds value only on the *non-obvious* transformations the engine
misses — e.g. removing an unnecessary blocking `$sort`, or replacing `$unwind`+`$group` with `$sum`.

## What's here

| File | Role |
|------|------|
| `gen_data.py` | Generate the synthetic workload (5k customers, 200k orders) |
| `harness.py` | The verifier + timer: run two pipelines, check empirical equivalence, time them |
| `pipelines.py` | Hand-written (original, rewrite) pairs incl. a deliberately-wrong one |
| `rewriter.py` | LLM rewriter with counterexample-guided retry |
| `gate.py` | The gate: invoke the LLM only when a pipeline is slow; policy comparison |
| `sensitivity.py` | Gate-threshold sensitivity sweep |
| `rewrite_cache.py` | Predicate-parameterized rewrite cache (cost amortization) + developer advisory |
| `realdata.py` | Same machinery on the real `sample_mflix` dataset |
| `llm_client.py` | Minimal Anthropic-compatible LLM client (stdlib only) |
| `PHASE1-4-RESULTS.md` | Recorded results for each component |

## Requirements

- **MongoDB 8.0** (`mongod`, `mongosh`, `mongoimport`)
- **Python 3.11** (managed via [uv](https://docs.astral.sh/uv/))
- An Anthropic-compatible LLM endpoint (for `rewriter.py`, `gate.py`, `rewrite_cache.py`, `realdata.py`)

## Setup

```bash
# 1. Throwaway MongoDB on :47017 (kept separate from any real instance)
mkdir -p mongo-data
mongod --dbpath ./mongo-data --port 47017 --bind_ip localhost --fork --logpath ./mongo-data/mongod.log

# 2. Python env
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python pymongo

# 3. LLM credentials
cp .env.example .env   # then edit .env with your key/endpoint
```

## Run the experiments

```bash
# Synthetic workload
.venv/bin/python gen_data.py        # load data
.venv/bin/python harness.py         # verifier: 4/4, catches the wrong rewrite
.venv/bin/python rewriter.py        # LLM rewrites, verified (needs .env)
.venv/bin/python gate.py            # gate vs rewrite-all vs baseline
.venv/bin/python sensitivity.py     # gate-threshold sweep
.venv/bin/python rewrite_cache.py   # cache: 1 LLM call serves many queries

# Real dataset (sample_mflix)
git clone --depth 1 https://github.com/neelabalan/mongodb-sample-dataset.git sampledata
mongoimport --port 47017 --db sample_mflix --collection movies   --drop --file sampledata/sample_mflix/movies.json
mongoimport --port 47017 --db sample_mflix --collection comments --drop --file sampledata/sample_mflix/comments.json
mongosh --port 47017 --quiet --eval 'db.getSiblingDB("sample_mflix").comments.createIndex({movie_id:1})'
.venv/bin/python realdata.py
```

## Notes

- **Determinism:** LLM calls use temperature 0; data generation uses a fixed seed; latencies are
  medians of 5 runs after warm-up.
- **Equivalence is empirical** (result-set comparison over the loaded data), not a formal proof — see
  the paper's Limitations.
- **Secrets:** `.env` is git-ignored; never commit your key. Use `.env.example` as the template.
- **Teardown:** stop the throwaway `mongod` (see `mongo-data/mongod.log` for its pid) and
  `rm -rf mongo-data sampledata`.

## License

Released under the [MIT License](LICENSE).

## Citation

If you use this work, please cite the accompanying paper:

> Rahul Sharma. *[Performance-Gated, Cost-Amortized LLM Rewriting of MongoDB Aggregation Pipelines
> with Verified Equivalence](https://doi.org/10.5281/zenodo.20456038)*. 2026.
> DOI: [10.5281/zenodo.20456038](https://doi.org/10.5281/zenodo.20456038)

```bibtex
@misc{sharma2026mongollmrewrite,
  title  = {Performance-Gated, Cost-Amortized LLM Rewriting of MongoDB Aggregation Pipelines with Verified Equivalence},
  author = {Sharma, Rahul},
  year   = {2026},
  doi    = {10.5281/zenodo.20456038},
  url    = {https://doi.org/10.5281/zenodo.20456038}
}
```
