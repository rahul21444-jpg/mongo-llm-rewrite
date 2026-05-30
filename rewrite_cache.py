"""Phase 4 — predicate-parameterized rewrite cache (the token-cost amortization).

Core idea (the user's architecture): a transparent proxy intercepts a naive query, serves an
equivalent faster one, and the client never changes. The LLM is paid ONCE per query *shape*:
- normalize the query to a TEMPLATE by stripping literal predicate values,
- cache the structural rewrite against that template,
- future queries with the SAME shape but DIFFERENT predicate values hit the cache -> 0 LLM calls.

Only structural rewrites are cached (safe for any predicate value); each served rewrite is still
verified equivalent (defense-in-depth against the cache-reuse risk).
"""
import json

import harness
from rewriter import rewrite_one

CACHE = {}  # template-key -> rewrite template (with <<Pi>> placeholders)
STATS = {"llm_calls": 0, "cache_hits": 0}


def _param_values(node, literals):
    """Replace scalar literal *values* with placeholders; keep keys and $field refs."""
    if isinstance(node, dict):
        return {k: _param_values(v, literals) for k, v in node.items()}
    if isinstance(node, list):
        return [_param_values(x, literals) for x in node]
    if isinstance(node, str) and node.startswith("$"):
        return node
    literals.append(node)
    return f"<<P{len(literals) - 1}>>"


def template_and_literals(pipeline):
    """Parameterize literals inside $match stages -> (template_key, ordered literals)."""
    literals, tmpl = [], []
    for stage in pipeline:
        if isinstance(stage, dict) and set(stage) == {"$match"}:
            tmpl.append({"$match": _param_values(stage["$match"], literals)})
        else:
            tmpl.append(stage)
    return json.dumps(tmpl, sort_keys=True), literals


def parameterize_rewrite(rewrite, orig_literals):
    """Replace any occurrence of an original predicate literal with its placeholder."""
    val_to_ph = {json.dumps(v): f"<<P{i}>>" for i, v in enumerate(orig_literals)}

    def rec(v):
        if isinstance(v, dict):
            return {k: rec(x) for k, x in v.items()}
        if isinstance(v, list):
            return [rec(x) for x in v]
        try:
            key = json.dumps(v)
        except TypeError:
            key = None
        return val_to_ph.get(key, v)

    return rec(rewrite)


def instantiate(template_obj, literals):
    def rec(v):
        if isinstance(v, dict):
            return {k: rec(x) for k, x in v.items()}
        if isinstance(v, list):
            return [rec(x) for x in v]
        if isinstance(v, str) and v.startswith("<<P") and v.endswith(">>"):
            return literals[int(v[3:-2])]
        return v

    return rec(template_obj)


def serve(coll, pipeline):
    """Return (rewritten_pipeline, used_llm)."""
    key, lits = template_and_literals(pipeline)
    if key in CACHE:
        STATS["cache_hits"] += 1
        return instantiate(CACHE[key], lits), False
    STATS["llm_calls"] += 1
    r = rewrite_one(coll, pipeline)
    if r["status"] == "ok" and not r["unchanged"]:
        CACHE[key] = parameterize_rewrite(r["pipeline"], lits)
        return r["pipeline"], True
    return pipeline, True  # no usable rewrite; serve original


def orig(status):
    # naive client query: an unnecessary $sort before a $group, parameterized by status
    return [
        {"$match": {"status": status}},
        {"$sort": {"amount": -1}},
        {"$group": {"_id": "$order_year", "total": {"$sum": "$amount"}}},
    ]


def main():
    coll = "orders"
    print("\nRewrite-cache demo: same shape, different predicate values\n" + "=" * 78)
    for status in ["cancelled", "delivered", "shipped", "pending"]:
        q = orig(status)
        served, used_llm = serve(coll, q)
        # defense-in-depth: verify the served rewrite is still equivalent for THIS value
        eq, _ = harness.equivalent(harness.run(coll, q), harness.run(coll, served))
        changed = json.dumps(served, sort_keys=True) != json.dumps(q, sort_keys=True)
        src = "LLM" if used_llm else "CACHE"
        print(
            f"  status={status:10s} served_by={src:5s}  rewritten={'yes' if changed else 'no ':3s}  "
            f"verified_equivalent={eq}"
        )
    print("=" * 78)
    served_total = STATS["llm_calls"] + STATS["cache_hits"]
    print(
        f"served {served_total} queries with {STATS['llm_calls']} LLM call(s) "
        f"and {STATS['cache_hits']} cache hit(s) -> "
        f"{100 * STATS['cache_hits'] // served_total}% of queries served with ZERO LLM cost"
    )
    # developer advisory
    tmpl_key = next(iter(CACHE))
    print("\nDeveloper advisory (bake this in to skip the proxy entirely):")
    print(f"  shape : {tmpl_key}")
    print(f"  faster: {json.dumps(CACHE[tmpl_key])}")


if __name__ == "__main__":
    main()
