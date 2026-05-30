"""Corpus of genuinely-slow aggregation pipelines (just the originals).

The LLM never sees a target rewrite — it must produce one. Mix of: real headroom the
optimizer won't reclaim, cases the optimizer already handles (~1x expected), and a
top-k case where the LLM must NOT over-optimize (removing the sort would change results).
"""

LOOKUP = {
    "$lookup": {
        "from": "customers",
        "localField": "customer_id",
        "foreignField": "_id",
        "as": "cust",
    }
}

SLOW_CORPUS = [
    {
        "name": "unneeded-sort-before-group",
        "collection": "orders",
        "note": "real headroom: $sort order is irrelevant to $group",
        "pipeline": [
            {"$sort": {"amount": -1}},
            {"$group": {"_id": "$status", "total": {"$sum": "$amount"}, "n": {"$sum": 1}}},
        ],
    },
    {
        "name": "unwind-then-group-sum",
        "collection": "orders",
        "note": "real headroom: per-doc array sum needs no $unwind (use $sum over items.qty)",
        "pipeline": [
            {"$unwind": "$items"},
            {"$group": {"_id": "$_id", "totalQty": {"$sum": "$items.qty"}}},
        ],
    },
    {
        "name": "lookup-then-late-match",
        "collection": "orders",
        "note": "optimizer likely already pushes $match before $lookup (~1x expected)",
        "pipeline": [
            LOOKUP,
            {"$unwind": "$cust"},
            {"$match": {"status": "cancelled"}},
            {"$group": {"_id": "$cust.region", "total": {"$sum": "$amount"}}},
        ],
    },
    {
        "name": "sort-limit-topk",
        "collection": "orders",
        "note": "semantics trap: top-10 by amount; a correct rewrite must keep sort+limit",
        "pipeline": [
            {"$sort": {"amount": -1}},
            {"$limit": 10},
            {"$project": {"_id": 0, "amount": 1}},
        ],
    },
    {
        "name": "sort-then-group-first",
        "collection": "orders",
        "note": "retry trap: $sort feeds $first, so removing it CHANGES results -> verifier must catch",
        "pipeline": [
            {"$sort": {"amount": -1}},
            {"$group": {"_id": "$customer_id", "topStatus": {"$first": "$status"}}},
        ],
    },
    # --- cheap / no-headroom pipelines: the gate should SKIP these (no LLM call) ---
    {
        "name": "cheap-id-range",
        "collection": "orders",
        "note": "cheap: indexed _id range, tiny output",
        "pipeline": [{"$match": {"_id": {"$lte": 50}}}, {"$project": {"amount": 1, "status": 1}}],
    },
    {
        "name": "cheap-small-group",
        "collection": "orders",
        "note": "cheap: 500 docs by _id then small group",
        "pipeline": [
            {"$match": {"_id": {"$lte": 500}}},
            {"$group": {"_id": "$status", "n": {"$sum": 1}}},
        ],
    },
    {
        "name": "cheap-count",
        "collection": "orders",
        "note": "cheap: indexed range count",
        "pipeline": [{"$match": {"_id": {"$lte": 1000}}}, {"$count": "c"}],
    },
]
