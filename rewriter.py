"""Phase 2 — LLM aggregation-pipeline rewriter with counterexample-guided retry.

For each slow pipeline:
  1. prompt the LLM (schema + indexes + explain flags) for an equivalent faster pipeline,
  2. run the candidate and verify equivalence with the Phase-1 harness,
  3. on rejection (bad JSON / execution error / not-equivalent), feed the reason back and retry,
  4. on success, time both and report the speedup.

The verifier is the safety net: a wrong rewrite can never be reported as a win.
"""
import json
import os
import re

import harness
from corpus import SLOW_CORPUS
from llm_client import call_llm

MAX_ATTEMPTS = 3
VERBOSE = bool(os.environ.get("REWRITER_VERBOSE"))

SYSTEM = (
    "You are an expert MongoDB aggregation-pipeline optimizer. You rewrite pipelines to run "
    "faster while returning the EXACT same result set (any order). You never change which "
    "results are produced. You output strict JSON only."
)


def describe(coll):
    doc = harness.DB[coll].find_one()
    schema = {k: type(v).__name__ for k, v in doc.items()} if doc else {}
    indexes = list(harness.DB[coll].index_information().keys())
    return schema, indexes


def build_prompt(coll, pipeline, schema, indexes, flags, counterexample=None):
    p = (
        f"Collection: {coll}\n"
        f"Document fields (name: type): {json.dumps(schema)}\n"
        f"Indexes: {indexes}\n"
        f"explain() access flags for the current pipeline: {flags}\n\n"
        f"Current aggregation pipeline:\n{json.dumps(pipeline, indent=2)}\n\n"
        "Rewrite it into a SEMANTICALLY EQUIVALENT pipeline that is likely faster (identical "
        "result set, order-insensitive). Favor: removing unnecessary blocking stages "
        "($sort/$unwind that don't affect the result), reducing documents early, avoiding "
        "redundant work. If the pipeline is already optimal, return it unchanged.\n\n"
        'Return ONLY strict JSON: {"pipeline": [ ...stages... ], "rationale": "<one sentence>"}'
    )
    if counterexample:
        p += (
            f"\n\nYour previous attempt was REJECTED:\n{counterexample}\n"
            "Return corrected strict JSON."
        )
    return p


def extract(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object found")
    return json.loads(m.group(0))


def rewrite_one(coll, pipeline):
    schema, indexes = describe(coll)
    flags = harness.explain(coll, pipeline)
    orig = harness.run(coll, pipeline)
    counter = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if VERBOSE and counter:
            print(f"    [retry {attempt}] previous attempt rejected -> {counter[:180]}")
        resp = call_llm(build_prompt(coll, pipeline, schema, indexes, flags, counter), system=SYSTEM)
        try:
            obj = extract(resp)
            cand = obj["pipeline"]
        except Exception as e:
            counter = f"Output was not strict JSON with a 'pipeline' array: {e}"
            continue
        try:
            cand_res = harness.run(coll, cand)
        except Exception as e:
            counter = f"Candidate raised an execution error: {str(e)[:200]}"
            continue
        eq, diff = harness.equivalent(orig, cand_res)
        if not eq:
            counter = f"NOT equivalent (results differ). Sample diff: {diff}"
            continue
        to, tr = harness.timeit(coll, pipeline), harness.timeit(coll, cand)
        unchanged = json.dumps(cand, sort_keys=True) == json.dumps(pipeline, sort_keys=True)
        return {
            "status": "ok",
            "attempts": attempt,
            "unchanged": unchanged,
            "speedup": (to / tr) if tr else None,
            "orig_ms": to,
            "rew_ms": tr,
            "rationale": obj.get("rationale", ""),
            "pipeline": cand,
        }
    return {"status": "failed", "attempts": MAX_ATTEMPTS, "last_reason": counter}


def main():
    print(f"\nLLM rewriter | DB orders={harness.DB.orders.count_documents({})}")
    print("=" * 80)
    rows = []
    for c in SLOW_CORPUS:
        print(f"\nPIPELINE: {c['name']}  ({c['note']})")
        r = rewrite_one(c["collection"], c["pipeline"])
        rows.append((c["name"], r))
        if r["status"] == "ok":
            tag = "unchanged (already optimal)" if r["unchanged"] else f"SPEEDUP {r['speedup']:.2f}x"
            print(f"  -> OK in {r['attempts']} attempt(s) | {r['orig_ms']:.1f}ms -> {r['rew_ms']:.1f}ms | {tag}")
            print(f"     rationale: {r['rationale'][:140]}")
        else:
            print(f"  -> FAILED after {r['attempts']} attempts | last: {r['last_reason'][:140]}")
    print("\n" + "=" * 80)
    ok = [r for _, r in rows if r["status"] == "ok"]
    improved = [r for r in ok if not r["unchanged"] and r["speedup"] and r["speedup"] > 1.1]
    print(
        f"summary: {len(ok)}/{len(rows)} valid rewrites, "
        f"{len(improved)} with >1.1x speedup, 0 incorrect rewrites accepted (verifier-guarded)"
    )


if __name__ == "__main__":
    main()
