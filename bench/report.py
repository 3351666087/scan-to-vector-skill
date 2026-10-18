#!/usr/bin/env python3
"""Score every run of an experiment and compare two arms page by page.

Layout: <runs>/<arm>/<page>/out/rebuilt.pdf, with ground truth in <data>/<page>.

    python bench/report.py --data ~/stv-bench/dev --runs ~/stv-bench/runs/it0 \
        --a baseline --b skill --out results.json

Prints a per-page table and, for the paired comparison, the mean difference,
how many pages each arm wins, and a bootstrap 95% interval for the mean gain.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import score  # noqa: E402

METRICS = ("score", "text_f1", "text_prec", "layout_f1", "figure", "raster")


def _score(args):
    page_dir, pdf, diff = args
    return score(page_dir, pdf, diff)


def bootstrap(diffs, n=5000, seed=0):
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--a", default="baseline")
    ap.add_argument("--b", default="skill")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--jobs", type=int, default=6)
    args = ap.parse_args()

    pages = sorted(p.name for p in args.data.iterdir() if (p / "truth.json").exists())
    jobs, keys = [], []
    for arm in (args.a, args.b):
        for page in pages:
            run = args.runs / arm / page
            if not run.exists():
                continue
            jobs.append((args.data / page, run / "out" / "rebuilt.pdf", run / "diff.png"))
            keys.append((arm, page))
    with ThreadPoolExecutor(args.jobs) as ex:
        results = dict(zip(keys, ex.map(_score, jobs)))

    rows = []
    print(f"{'page':16} " + " ".join(f"{args.a[:8]:>8} {args.b[:8]:>8}" for _ in [0]) + "   gain  (text layout figure raster: a -> b)")
    for page in pages:
        a, b = results.get((args.a, page)), results.get((args.b, page))
        if not a or not b:
            continue
        rows.append({"page": page, args.a: a, args.b: b})
        detail = "  ".join(f"{m[:6]} {a[m]:.2f}->{b[m]:.2f}" for m in ("text_f1", "layout_f1", "figure", "raster"))
        print(f"{page:16} {a['score']:8.3f} {b['score']:8.3f} {b['score'] - a['score']:+6.3f}   {detail}")
    if not rows:
        print("no paired results")
        return 1
    summary = {}
    for m in METRICS:
        av = [r[args.a][m] for r in rows]
        bv = [r[args.b][m] for r in rows]
        diffs = [y - x for x, y in zip(av, bv)]
        lo, hi = bootstrap(diffs) if len(diffs) > 1 else (diffs[0], diffs[0])
        better = (lambda d: d < 0) if m == "raster" else (lambda d: d > 0)
        summary[m] = {
            args.a: round(sum(av) / len(av), 3), args.b: round(sum(bv) / len(bv), 3),
            "mean_gain": round(sum(diffs) / len(diffs), 3), "ci95": [round(lo, 3), round(hi, 3)],
            "b_wins": sum(1 for d in diffs if better(d) and abs(d) > 0.005),
            "a_wins": sum(1 for d in diffs if not better(d) and abs(d) > 0.005),
            "n": len(diffs),
        }
    print()
    for m, s in summary.items():
        print(f"{m:10} {args.a} {s[args.a]:.3f}  {args.b} {s[args.b]:.3f}  gain {s['mean_gain']:+.3f} "
              f"[{s['ci95'][0]:+.3f}, {s['ci95'][1]:+.3f}]  wins {s['b_wins']}-{s['a_wins']} of {s['n']}")
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "pages": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
