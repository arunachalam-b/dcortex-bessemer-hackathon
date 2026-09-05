#!/usr/bin/env python3
"""Scoreboard: replay all questions and scenarios against the answer keys.

Usage:  python3 run_regression.py [-v]
"""

import sys

from crew_ops import load_world
from crew_ops.regression import run_all


def main():
    verbose = "-v" in sys.argv
    world = load_world()
    res = run_all(world)
    tier_stats = {}
    for r in res["rows"]:
        t = str(r["tier"])
        tier_stats.setdefault(t, [0, 0, 0])  # pass, auto-total, manual
        if r["status"] == "MANUAL":
            tier_stats[t][2] += 1
        else:
            tier_stats[t][1] += 1
            tier_stats[t][0] += r["status"] == "PASS"
        mark = {"PASS": "PASS ", "FAIL": "FAIL ", "ERROR": "ERROR",
                "MANUAL": "MANUAL(judged)"}[r["status"]]
        print(f"{r['id']:>4}  tier {t:>2}  {mark}")
        if r["diffs"] and (verbose or r["status"] != "PASS"):
            for d in r["diffs"][:8]:
                print(f"        - {d}")
    print()
    for t in sorted(tier_stats):
        p, n, m = tier_stats[t]
        label = f"tier {t}" if t != "S" else "scenarios"
        extra = f"  (+{m} judged manually)" if m else ""
        print(f"{label:>10}: {p} pass / {n}{extra}")
    print(f"\nTOTAL: {res['passed']}/{res['auto_total']} automated checks pass "
          f"({res['manual']} open-ended items judged manually)")
    return 0 if res["passed"] == res["auto_total"] else 1


if __name__ == "__main__":
    sys.exit(main())
