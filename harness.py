"""Measurement + verification harness for MongoDB aggregation-pipeline rewrites.

For each (original, rewrite) pair it:
  1. runs both pipelines,
  2. checks EMPIRICAL equivalence (order-insensitive multiset compare, currency-rounded),
  3. times both (warm-up + N runs, median),
  4. pulls explain() flags (COLLSCAN / IXSCAN),
and scores the detected verdict against the case's ground truth.

LIMITATION (state in the paper): equivalence is empirical over the loaded data, not a
formal proof. A rewrite that diverges only on data absent from the corpus is not caught.
"""
import json
import os
import statistics
import time

from bson import ObjectId
from pymongo import MongoClient

from pipelines import CASES

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:47017")
DB = MongoClient(MONGO_URI)["poc_aggrewrite"]
FLOAT_DECIMALS = 4  # currency-grade rounding so FP summation order can't cause false diffs
TIMING_RUNS = 5


def _canon(v):
    if isinstance(v, float):
        return round(v, FLOAT_DECIMALS)
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, list):
        return [_canon(x) for x in v]
    if isinstance(v, dict):
        return {k: _canon(v[k]) for k in sorted(v)}
    return v


def _multiset(docs):
    return sorted(json.dumps(_canon(d), sort_keys=True, default=str) for d in docs)


def run(coll, pipeline):
    return list(DB[coll].aggregate(pipeline, allowDiskUse=True))


def equivalent(a, b):
    ca, cb = _multiset(a), _multiset(b)
    if ca == cb:
        return True, None
    only_a = list(set(ca) - set(cb))[:1]
    only_b = list(set(cb) - set(ca))[:1]
    return False, {"rows": (len(a), len(b)), "only_in_original": only_a, "only_in_rewrite": only_b}


def timeit(coll, pipeline, runs=TIMING_RUNS):
    run(coll, pipeline)  # warm-up
    lat = []
    for _ in range(runs):
        t = time.perf_counter()
        run(coll, pipeline)
        lat.append((time.perf_counter() - t) * 1000)
    return statistics.median(lat)


def explain(coll, pipeline):
    try:
        out = DB.command(
            "explain",
            {"aggregate": coll, "pipeline": pipeline, "cursor": {}},
            verbosity="executionStats",
        )
        s = json.dumps(out, default=str)
        flags = [f for f in ("COLLSCAN", "IXSCAN") if f in s]
        return "+".join(flags) or "none"
    except Exception as e:  # explain shape varies by version; never let it break the run
        return f"explain-error:{str(e)[:60]}"


def main():
    print(
        f"\nDB poc_aggrewrite | orders={DB.orders.count_documents({})} "
        f"customers={DB.customers.count_documents({})}"
    )
    print("=" * 80)
    passed = 0
    for c in CASES:
        coll = c["collection"]
        orig, rew = run(coll, c["original"]), run(coll, c["rewrite"])
        eq, diff = equivalent(orig, rew)
        ok = eq == c["expect_equivalent"]
        passed += ok
        print(f"\nCASE {c['name']}  [{c['rewrite_kind']}]")
        print(f"  {c['description']}")
        print(f"  rows: original={len(orig)} rewrite={len(rew)}")
        print(
            f"  equivalence: detected={'EQUIVALENT' if eq else 'NOT-EQUIVALENT'} "
            f"expected={'EQUIVALENT' if c['expect_equivalent'] else 'NOT-EQUIVALENT'} "
            f"-> {'PASS' if ok else 'FAIL'}"
        )
        if not eq and diff:
            print(f"  diff: {diff}")
        if eq and c["expect_equivalent"]:
            to, tr = timeit(coll, c["original"]), timeit(coll, c["rewrite"])
            speedup = to / tr if tr else float("inf")
            print(f"  original: {to:7.1f} ms  [{explain(coll, c['original'])}]")
            print(f"  rewrite : {tr:7.1f} ms  [{explain(coll, c['rewrite'])}]")
            print(f"  >>> SPEEDUP {speedup:.2f}x")
    print("\n" + "=" * 80)
    print(f"harness self-check: {passed}/{len(CASES)} cases scored as expected")


if __name__ == "__main__":
    main()
