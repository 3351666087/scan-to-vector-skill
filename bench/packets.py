#!/usr/bin/env python3
"""Group benchmark pages into multi-page packets and score packet runs.

    python bench/packets.py make  --data ~/stv-bench/holdout --size 3 --out ~/stv-bench/packets/holdout
    python bench/packets.py score --packets ~/stv-bench/packets/holdout --runs ~/stv-bench/runs/final --arms baseline skill

A packet folder holds scan-1.jpg ... scan-N.jpg and packet.json (which truth page
each scan is). A run of that packet must write out/rebuilt.pdf with the pages in
the same order; each page is scored against its own ground truth, and a missing
page scores 0.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report import bootstrap  # noqa: E402
from score import score  # noqa: E402


def make(data: Path, size: int, out: Path):
    pages = sorted(p for p in data.iterdir() if (p / "truth.json").exists())
    # interleave kinds so each packet mixes page types
    by_kind = {}
    for p in pages:
        by_kind.setdefault(json.loads((p / "truth.json").read_text())["kind"], []).append(p)
    order = []
    while any(by_kind.values()):
        for k in sorted(by_kind):
            if by_kind[k]:
                order.append(by_kind[k].pop(0))
    out.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(order) - size + 1, size):
        pk = out / f"packet-{i // size + 1:02d}"
        pk.mkdir(exist_ok=True)
        members = order[i:i + size]
        for j, p in enumerate(members, 1):
            shutil.copy(p / "scan.jpg", pk / f"scan-{j}.jpg")
        (pk / "packet.json").write_text(json.dumps({"pages": [str(p) for p in members]}, indent=1))
        print(pk.name, [p.name for p in members])


def _one(args):
    truth, pdf, idx = args
    return score(Path(truth), Path(pdf), None, idx)


def score_runs(packets: Path, runs: Path, arms):
    jobs, keys = [], []
    for pk in sorted(packets.iterdir()):
        if not (pk / "packet.json").exists():
            continue
        members = json.loads((pk / "packet.json").read_text())["pages"]
        for arm in arms:
            pdf = runs / arm / pk.name / "out" / "rebuilt.pdf"
            for idx, truth in enumerate(members):
                jobs.append((truth, str(pdf), idx))
                keys.append((arm, pk.name, Path(truth).name))
    with ThreadPoolExecutor(6) as ex:
        res = dict(zip(keys, ex.map(_one, jobs)))
    pages = sorted({(k[1], k[2]) for k in keys})
    print(f"{'packet/page':28} " + " ".join(f"{a[:10]:>10}" for a in arms))
    for pk, pg in pages:
        print(f"{pk + '/' + pg:28} " + " ".join(f"{res[(a, pk, pg)]['score']:10.3f}" for a in arms))
    summary = {}
    for a in arms:
        vals = [res[(a, pk, pg)]["score"] for pk, pg in pages]
        summary[a] = {m: round(sum(res[(a, pk, pg)][m] for pk, pg in pages) / len(pages), 3)
                      for m in ("score", "text_f1", "layout_f1", "figure", "raster")}
        summary[a]["n_pages"] = len(vals)
    if len(arms) == 2:
        d = [res[(arms[1], pk, pg)]["score"] - res[(arms[0], pk, pg)]["score"] for pk, pg in pages]
        lo, hi = bootstrap(d)
        summary["gain"] = {"mean": round(sum(d) / len(d), 3), "ci95": [round(lo, 3), round(hi, 3)],
                           "b_wins": sum(x > 0.005 for x in d), "a_wins": sum(x < -0.005 for x in d)}
    print(json.dumps(summary, indent=1))
    return summary, res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--data", type=Path, required=True)
    m.add_argument("--size", type=int, default=3)
    m.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("score")
    s.add_argument("--packets", type=Path, required=True)
    s.add_argument("--runs", type=Path, required=True)
    s.add_argument("--arms", nargs="+", default=["baseline", "skill"])
    s.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.cmd == "make":
        make(args.data, args.size, args.out)
    else:
        summary, res = score_runs(args.packets, args.runs, args.arms)
        if args.out:
            args.out.write_text(json.dumps({"summary": summary,
                                            "pages": {"|".join(k): v for k, v in res.items()}}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
