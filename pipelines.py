"""Corpus of (original, rewrite) aggregation-pipeline pairs for the harness.

Each case carries the ground-truth `expect_equivalent` so the harness can be scored:
- a CORRECT rewrite must be detected EQUIVALENT and (ideally) be faster
- an INCORRECT rewrite must be detected NOT-equivalent (proves the verifier works)

In the real paper, `rewrite` is produced by the LLM. Here we hand-write rewrites
to validate the instrument before any LLM is involved.
"""

LOOKUP = {
    "$lookup": {
        "from": "customers",
        "localField": "customer_id",
        "foreignField": "_id",
        "as": "cust",
    }
}

CASES = [
    {
        "name": "predicate-pushdown",
        "collection": "orders",
        "rewrite_kind": "correct",
        "expect_equivalent": True,
        "description": "Move $match(status) before the $lookup so the join runs on ~8% of docs.",
        "original": [
            LOOKUP,
            {"$unwind": "$cust"},
            {"$match": {"status": "cancelled"}},
            {"$group": {"_id": "$cust.region", "total": {"$sum": "$amount"}, "n": {"$sum": 1}}},
        ],
        "rewrite": [
            {"$match": {"status": "cancelled"}},
            LOOKUP,
            {"$unwind": "$cust"},
            {"$group": {"_id": "$cust.region", "total": {"$sum": "$amount"}, "n": {"$sum": 1}}},
        ],
    },
    {
        "name": "project-before-group",
        "collection": "orders",
        "rewrite_kind": "correct",
        "expect_equivalent": True,
        "description": "Drop the heavy items[] array before $group; output unchanged.",
        "original": [
            {"$match": {"status": "delivered"}},
            {"$group": {"_id": "$order_year", "total": {"$sum": "$amount"}, "n": {"$sum": 1}}},
        ],
        "rewrite": [
            {"$match": {"status": "delivered"}},
            {"$project": {"order_year": 1, "amount": 1}},
            {"$group": {"_id": "$order_year", "total": {"$sum": "$amount"}, "n": {"$sum": 1}}},
        ],
    },
    {
        "name": "drop-unneeded-sort",
        "collection": "orders",
        "rewrite_kind": "correct",
        "expect_equivalent": True,
        "description": "Remove a blocking $sort whose order $group does not depend on (optimizer won't).",
        "original": [
            {"$sort": {"amount": -1}},
            {"$group": {"_id": "$status", "total": {"$sum": "$amount"}, "n": {"$sum": 1}}},
        ],
        "rewrite": [
            {"$group": {"_id": "$status", "total": {"$sum": "$amount"}, "n": {"$sum": 1}}},
        ],
    },
    {
        "name": "wrong-rewrite-changes-filter",
        "collection": "orders",
        "rewrite_kind": "incorrect",
        "expect_equivalent": False,
        "description": "NEGATIVE CONTROL: rewrite silently changes the status value -> must be caught.",
        "original": [
            {"$match": {"status": "cancelled"}},
            {"$group": {"_id": "$order_year", "total": {"$sum": "$amount"}}},
        ],
        "rewrite": [
            {"$match": {"status": "delivered"}},  # WRONG: different subset
            {"$group": {"_id": "$order_year", "total": {"$sum": "$amount"}}},
        ],
    },
]
