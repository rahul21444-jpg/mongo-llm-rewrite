"""Real-data evaluation on MongoDB's sample_mflix (23,539 movies, 50,304 comments).

Reuses the Phase 1-4 machinery (harness verifier/timer, LLM rewriter, gate, cache) by pointing the
shared DB handle at sample_mflix. Produces the real-data numbers reported in the paper.
"""
import json

import harness
from pymongo import MongoClient
from rewriter import rewrite_one

# point the shared harness DB at the real dataset
harness.DB = MongoClient(harness.MONGO_URI)["sample_mflix"]

THRESHOLD_MS = 50.0

REAL_CORPUS = [
    {
        "name": "unneeded-sort-by-rating",
        "coll": "movies",
        "pipeline": [
            {"$sort": {"imdb.rating": -1}},
            {"$group": {"_id": "$rated", "n": {"$sum": 1}}},
        ],
    },
    {
        "name": "unwind-genres-count",
        "coll": "movies",
        "pipeline": [
            {"$unwind": "$genres"},
            {"$group": {"_id": "$_id", "numGenres": {"$sum": 1}}},
        ],
    },
    {
        "name": "lookup-comments-late-match",
        "coll": "movies",
        "pipeline": [
            {"$lookup": {"from": "comments", "localField": "_id", "foreignField": "movie_id", "as": "c"}},
            {"$unwind": "$c"},
            {"$match": {"rated": "PG-13"}},
            {"$group": {"_id": "$rated", "comments": {"$sum": 1}}},
        ],
    },
    {
        "name": "sort-first-top-per-genre",
        "coll": "movies",
        "pipeline": [
            {"$match": {"imdb.rating": {"$type": "number"}}},
            {"$sort": {"imdb.rating": -1}},
            {"$unwind": "$genres"},
            {"$group": {"_id": "$genres", "topMovie": {"$first": "$title"}}},
        ],
    },
    {
        "name": "topk-by-rating",
        "coll": "movies",
        "pipeline": [
            {"$match": {"imdb.rating": {"$type": "number"}}},
            {"$sort": {"imdb.rating": -1}},
            {"$limit": 10},
            {"$project": {"_id": 0, "title": 1}},
        ],
    },
    {
        "name": "cheap-limit",
        "coll": "movies",
        "pipeline": [{"$match": {"rated": "G"}}, {"$limit": 5}, {"$project": {"_id": 0, "title": 1}}],
    },
    {
        "name": "cheap-head",
        "coll": "movies",
        "pipeline": [{"$limit": 1}, {"$project": {"_id": 0, "title": 1}}],
    },
]


def adopt(orig_ms, r):
    if r["status"] == "ok" and not r["unchanged"] and r["rew_ms"] < orig_ms:
        return r["rew_ms"], True
    return orig_ms, False


def gate_experiment():
    print(f"\nReal-data gate experiment | sample_mflix | threshold={THRESHOLD_MS}ms")
    print("=" * 94)
    rows = []
    for c in REAL_CORPUS:
        orig_ms = harness.timeit(c["coll"], c["pipeline"])
        r = rewrite_one(c["coll"], c["pipeline"])
        adopt_ms, adopted = adopt(orig_ms, r)
        fires = orig_ms > THRESHOLD_MS
        rows.append({"orig": orig_ms, "adopt": adopt_ms, "fires": fires})
        gain = f"adopt {orig_ms:.0f}->{adopt_ms:.0f}ms" if adopted else "no gain"
        print(
            f"  {c['name']:26s} orig={orig_ms:7.1f}ms  gate={'FIRE' if fires else 'skip':4s}  "
            f"rewrite={r['status']}({r.get('attempts')}x)  {gain}"
        )
    print("=" * 94)
    base = sum(x["orig"] for x in rows)
    all_total = sum(x["adopt"] for x in rows)
    gated_total = sum(x["adopt"] if x["fires"] else x["orig"] for x in rows)
    all_calls, gated_calls = len(rows), sum(1 for x in rows if x["fires"])

    def line(name, total, calls):
        print(f"  {name:13s} total={total:8.1f}ms  saved={base - total:8.1f}ms ({100 * (base - total) / base:5.1f}%)  LLM_calls={calls}")

    print("\nPOLICY COMPARISON:")
    line("baseline", base, 0)
    line("rewrite-all", all_total, all_calls)
    line("gated", gated_total, gated_calls)
    asv, gsv = base - all_total, base - gated_total
    if asv > 0:
        print(f"\n  >>> gate kept {100 * gsv / asv:.0f}% of benefit using {gated_calls}/{all_calls} LLM calls.")


def cache_demo():
    print("\nReal-data cache demo: same shape, different `rated` values")
    print("=" * 70)
    from rewrite_cache import serve, STATS

    def shape(rated):
        return [
            {"$match": {"rated": rated}},
            {"$sort": {"imdb.rating": -1}},
            {"$group": {"_id": None, "n": {"$sum": 1}}},
        ]

    for rated in ["PG-13", "R", "G", "PG"]:
        q = shape(rated)
        served, used_llm = serve("movies", q)
        eq, _ = harness.equivalent(harness.run("movies", q), harness.run("movies", served))
        print(f"  rated={rated:6s} served_by={'LLM' if used_llm else 'CACHE':5s}  verified_equivalent={eq}")
    total = STATS["llm_calls"] + STATS["cache_hits"]
    print(f"  -> {total} queries, {STATS['llm_calls']} LLM call(s), {100 * STATS['cache_hits'] // total}% zero-cost")


if __name__ == "__main__":
    gate_experiment()
    cache_demo()
