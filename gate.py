"""Phase 3 — the gate: only spend an LLM call when a cheap signal says a pipeline is slow.

Compares three policies over the corpus:
  baseline     : never rewrite
  rewrite-all  : invoke the LLM on every pipeline
  gated        : invoke the LLM only when observed latency > THRESHOLD_MS

Each pipeline is rewritten once (cached); policy outcomes are computed as counterfactuals.
The gate's bet: cheap pipelines have little headroom, so skipping them loses ~no benefit while
saving the LLM call. The verifier still guards correctness for every rewrite that IS adopted.
"""
import harness
from corpus import SLOW_CORPUS
from rewriter import rewrite_one

THRESHOLD_MS = 50.0  # gate fires above this observed latency


def adopt(orig_ms, r):
    """Adopt a rewrite only if it verified equivalent AND is actually faster."""
    if r["status"] == "ok" and not r["unchanged"] and r["rew_ms"] < orig_ms:
        return r["rew_ms"], True
    return orig_ms, False


def main():
    print(f"\nGate experiment | threshold={THRESHOLD_MS}ms | corpus={len(SLOW_CORPUS)} pipelines")
    print("=" * 92)
    rows = []
    for c in SLOW_CORPUS:
        orig_ms = harness.timeit(c["collection"], c["pipeline"])
        r = rewrite_one(c["collection"], c["pipeline"])
        adopt_ms, adopted = adopt(orig_ms, r)
        fires = orig_ms > THRESHOLD_MS
        rows.append({"orig": orig_ms, "adopt": adopt_ms, "adopted": adopted, "fires": fires})
        gain = f"adopt {orig_ms:.0f}->{adopt_ms:.0f}ms" if adopted else "no gain"
        print(
            f"  {c['name']:24s} orig={orig_ms:6.1f}ms  gate={'FIRE' if fires else 'skip':4s}  "
            f"rewrite={r['status']}({r.get('attempts')}x)  {gain}"
        )
    print("=" * 92)

    base = sum(x["orig"] for x in rows)
    all_total = sum(x["adopt"] for x in rows)
    all_calls = len(rows)
    gated_total = sum(x["adopt"] if x["fires"] else x["orig"] for x in rows)
    gated_calls = sum(1 for x in rows if x["fires"])

    def line(name, total, calls):
        saved = base - total
        pct = 100 * saved / base if base else 0
        print(f"  {name:13s} total={total:7.1f}ms  saved={saved:7.1f}ms ({pct:5.1f}%)  LLM_calls={calls}")

    print("\nPOLICY COMPARISON (lower total = better; fewer LLM calls = cheaper):")
    line("baseline", base, 0)
    line("rewrite-all", all_total, all_calls)
    line("gated", gated_total, gated_calls)

    all_saved, gated_saved = base - all_total, base - gated_total
    if all_saved > 0:
        print(
            f"\n  >>> gate captured {100 * gated_saved / all_saved:.0f}% of rewrite-all's benefit "
            f"using {gated_calls}/{all_calls} LLM calls "
            f"({100 * (all_calls - gated_calls) / all_calls:.0f}% fewer)."
        )


if __name__ == "__main__":
    main()
