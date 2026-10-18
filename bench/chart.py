#!/usr/bin/env python3
"""Draw the README benchmark chart (assets/benchmark.svg) from a results file.

    python bench/chart.py bench/results/final.json assets/benchmark.svg

Two dumbbell panels share the model rows: page quality (mean score) and minutes
per 3-page packet, each model without and with the skill. Light and dark colours
follow the viewer's colour scheme.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

W, ROW, TOP, LEFT = 960, 64, 118, 150
PANEL = (W - LEFT - 40) // 2 - 30
STYLE = """
  .t1 { fill: #0b0b0b; } .t2 { fill: #52514e; } .t3 { fill: #6f6e69; }
  .grid { stroke: #e4e3df; } .link { stroke: #b7b6b0; }
  .without { fill: #86b6ef; } .with { fill: #1c5cab; }
  .kw { fill: #86b6ef; } .kk { fill: #1c5cab; }
  @media (prefers-color-scheme: dark) {
    .t1 { fill: #f0efec; } .t2 { fill: #c3c2b7; } .t3 { fill: #9d9c95; }
    .grid { stroke: #33332f; } .link { stroke: #5b5a55; }
    .without { fill: #184f95; } .with { fill: #6da7ec; }
    .kw { fill: #184f95; } .kk { fill: #6da7ec; }
  }
  text { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; }
"""


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;")


def panel(x0, title, sub, rows, key, lo, hi, ticks, fmt, better, vfmt=None):
    vfmt = vfmt or fmt
    out = [f'<text x="{x0}" y="{TOP - 62}" class="t1" font-size="17" font-weight="600">{esc(title)}</text>',
           f'<text x="{x0}" y="{TOP - 40}" class="t2" font-size="13">{esc(sub)}</text>']
    sx = lambda v: x0 + (v - lo) / (hi - lo) * PANEL
    bottom = TOP + ROW * len(rows) - 20
    for t in ticks:
        out.append(f'<line x1="{sx(t):.1f}" y1="{TOP - 18}" x2="{sx(t):.1f}" y2="{bottom}" class="grid" stroke-width="1"/>')
        out.append(f'<text x="{sx(t):.1f}" y="{bottom + 18}" class="t3" font-size="12" text-anchor="middle">{fmt(t)}</text>')
    for i, r in enumerate(rows):
        y = TOP + i * ROW + 12
        a, b = r[key]
        out.append(f'<line x1="{sx(a):.1f}" y1="{y}" x2="{sx(b):.1f}" y2="{y}" class="link" stroke-width="2"/>')
        out.append(f'<circle cx="{sx(a):.1f}" cy="{y}" r="7" class="without"/>')
        out.append(f'<circle cx="{sx(b):.1f}" cy="{y}" r="7" class="with"/>')
        right = b >= a
        la, lb = ("end", "start") if right else ("start", "end")
        oa, ob = (-12, 12) if right else (12, -12)
        out.append(f'<text x="{sx(a) + oa:.1f}" y="{y + 4}" class="t2" font-size="12" text-anchor="{la}">{vfmt(a)}</text>')
        out.append(f'<text x="{sx(b) + ob:.1f}" y="{y + 4}" class="t1" font-size="12" font-weight="600" text-anchor="{lb}">{vfmt(b)}</text>')
    out.append(f'<text x="{x0 + PANEL}" y="{TOP - 40}" class="t3" font-size="12" text-anchor="end">{esc(better)}</text>')
    return out


def main() -> int:
    res = json.loads(Path(sys.argv[1]).read_text())
    rows = res["models"]
    H = TOP + ROW * len(rows) + 64
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="Benchmark: each model with and without the skill, quality and time">',
           f"<style>{STYLE}</style>"]
    for i, r in enumerate(rows):
        y = TOP + i * ROW + 12
        svg.append(f'<text x="{LEFT - 24}" y="{y + 5}" class="t1" font-size="15" font-weight="600" text-anchor="end">{esc(r["name"])}</text>')
        svg.append(f'<text x="{LEFT - 24}" y="{y + 23}" class="t3" font-size="11.5" text-anchor="end">wins {r["wins"][0]}–{r["wins"][1]}</text>')
    s_lo = min(0.90, int(min(min(r["score"]) for r in rows) * 20) / 20)      # whole 0.05 steps
    ticks = [round(s_lo + 0.05 * k, 2) for k in range(int(round((1 - s_lo) / 0.05)) + 1)]
    svg += panel(LEFT, "Page quality", f"mean score, {res['pages']} unseen pages", rows, "score", s_lo, 1.0,
                 ticks, lambda v: f"{v:.2f}" if v < 1 else "1.0", "higher is better →", vfmt=lambda v: f"{v:.3f}")
    m_hi = max(max(r["minutes"]) for r in rows)
    m_hi = (int(m_hi / 4) + 1) * 4
    svg += panel(LEFT + PANEL + 70, "Time", res.get("time_label", "minutes per 3-page packet"), rows, "minutes", 0, m_hi,
                 list(range(0, m_hi + 1, max(2, m_hi // 4))), lambda v: f"{int(v)}", "← lower is better", vfmt=lambda v: f"{v:.1f}")
    ly = H - 22
    svg += [f'<circle cx="{LEFT}" cy="{ly - 4}" r="6" class="kw"/>',
            f'<text x="{LEFT + 12}" y="{ly}" class="t2" font-size="13">without the skill</text>',
            f'<circle cx="{LEFT + 150}" cy="{ly - 4}" r="6" class="kk"/>',
            f'<text x="{LEFT + 162}" y="{ly}" class="t2" font-size="13">with the skill</text>',
            f'<text x="{W - 20}" y="{ly}" class="t3" font-size="12" text-anchor="end">{esc(res.get("note", ""))}</text>',
            "</svg>"]
    Path(sys.argv[2]).write_text("\n".join(svg) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
