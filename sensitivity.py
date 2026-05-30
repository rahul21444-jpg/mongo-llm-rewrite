"""Gate-threshold sensitivity analysis (strengthens RQ3).

Rewrite each pipeline once (cached), then analytically sweep the latency threshold to trace the
LLM-calls vs benefit-captured tradeoff. No extra LLM calls per threshold.
"""
import harness
from corpus import SLOW_CORPUS
from rewriter import rewrite_one


def main():
    data = []
    for c in SLOW_CORPUS:
        orig = harness.timeit(c["collection"], c["pipeline"])
        r = rewrite_one(c["collection"], c["pipeline"])
        adopt = r["rew_ms"] if (r["status"] == "ok" and not r["unchanged"] and r["rew_ms"] < orig) else orig
        data.append({"name": c["name"], "orig": orig, "adopt": adopt})

    base = sum(d["orig"] for d in data)
    all_saved = sum(d["orig"] - d["adopt"] for d in data)
    print(
        f"\nbaseline={base:.1f}ms | rewrite-all saves {all_saved:.1f}ms "
        f"({100 * all_saved / base:.1f}%) over {len(data)} pipelines\n"
    )
    print("Gate-threshold sensitivity (analytic sweep):")
    print(f"  {'T(ms)':>6} {'LLM_calls':>9} {'saved(ms)':>10} {'%benefit':>9} {'%calls':>7}")
    for T in [0, 5, 10, 25, 50, 100, 150, 250, 400]:
        calls = sum(1 for d in data if d["orig"] > T)
        saved = sum(d["orig"] - d["adopt"] for d in data if d["orig"] > T)
        pctb = 100 * saved / all_saved if all_saved else 0
        pctc = 100 * calls / len(data)
        print(f"  {T:6.0f} {calls:9d} {saved:10.1f} {pctb:7.0f}% {pctc:6.0f}%")
    print("\nSweet spot = lowest %calls that still keeps ~100% benefit.")


if __name__ == "__main__":
    main()
