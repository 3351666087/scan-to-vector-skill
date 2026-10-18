#!/usr/bin/env python3
"""Turn drawing ink that nothing else explains into vector shapes.

draft.py calls find_shapes() with the scan and what the draft already draws.
Every leftover piece of ink that is not text-sized becomes one of:
  line     a straight stroke                       {"points": [p0, p1], "width"}
  ellipse  an outlined ellipse or circle           {"box": [x0, y0, x1, y1], "width"}
  polygon  an outlined triangle, diamond, box ...  {"points": [...], "width"}
  outline  anything else (arrowheads, curves, markers, bent connectors): its exact
           outline as filled vector paths           {"paths": [[...], ...]}
Each fitted shape is checked against the ink before it is accepted, so a shape
is only "clean" when it really matches; otherwise the exact outline is used.
Text-sized marks are left alone (they may be letters OCR missed) and stay red
in the diff for you to look at.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi


def luminance(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def ink_mask(rgb, level=165):
    """Ink: dark marks, plus pale but clearly coloured strokes (yellow lines, light colour)."""
    lum = luminance(rgb)
    mx, mn = rgb.max(-1), rgb.min(-1)
    pale_colour = ((mx - mn) / np.maximum(mx, 1) > 0.35) & (mx - mn > 50) & (lum < 235)
    return (lum < level) | pale_colour


def chroma_clusters(px, k=4, merge=0.035, iters=12):
    """Group pixel colours by chromaticity (hue and strength, not lightness) with a small k-means."""
    c = px / np.maximum(px.sum(1, keepdims=True), 1)
    rng = np.random.default_rng(0)
    sample = c[rng.choice(len(c), min(len(c), 20000), replace=False)]
    cent = sample[rng.choice(len(sample), min(k, len(sample)), replace=False)]
    for _ in range(iters):
        lab = np.linalg.norm(sample[:, None] - cent[None], axis=-1).argmin(1)
        cent = np.array([sample[lab == j].mean(0) if (lab == j).any() else cent[j] for j in range(len(cent))])
    keep = []
    for cc in cent:                                        # merge near-identical clusters
        if all(np.linalg.norm(cc - q) > merge for q in keep):
            keep.append(cc)
    keep = np.array(keep)
    return np.linalg.norm(c[:, None] - keep[None], axis=-1).argmin(1)


def find_washes(rgb, fills, min_area=5000):
    """Light colour washes that are not rectangles (tinted areas of a map or chart, highlighter):
    traced outlines filled with the wash colour, drawn under everything else. Ink and the
    colour fringes around it are ignored; old-paper stains are too faint to count."""
    lum = luminance(rgb)
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    near_ink = ndi.binary_dilation(ink_mask(rgb), np.ones((7, 7), bool))
    cand = (ndi.uniform_filter(sat, 5) > 0.10) & (lum > 150) & (lum < 248) & ~near_ink
    if cand.sum() < min_area:
        return []
    group = np.zeros(cand.shape, np.int16)
    group[cand] = chroma_clusters(rgb[cand]) + 1
    covered = np.zeros(cand.shape, bool)
    for f in fills:
        x0, y0, x1, y1 = f["box"]
        covered[y0:y1, x0:x1] = True
    out = []
    for g in range(1, int(group.max()) + 1):
        m = ndi.binary_opening(ndi.binary_closing(group == g, np.ones((15, 15), bool)), np.ones((9, 9), bool))
        lab, n = ndi.label(m)
        for i, sl in enumerate(ndi.find_objects(lab), 1):
            comp = lab[sl] == i
            area = int(comp.sum())
            if area < min_area or area > 0.5 * m.size or (comp & covered[sl]).sum() > 0.8 * area:
                continue
            core = comp & (group[sl] == g)
            if not core.any() or np.median(sat[sl][core]) < 0.12:
                continue
            y0, x0 = sl[0].start, sl[1].start
            paths = [rdp_closed(lp, 1.5) for lp in loops(comp)]
            paths = [[[round(x + x0, 1), round(y + y0, 1)] for x, y in p] for p in paths if len(p) >= 3]
            if paths and len(paths) <= 200:
                out.append({"kind": "wash", "paths": paths, "box": [x0, y0, sl[1].stop, sl[0].stop],
                            "color": "#%02x%02x%02x" % tuple(int(v) for v in np.median(rgb[sl][core], 0))})
    return out


def rdp(pts, eps):
    """Ramer-Douglas-Peucker simplification of an open polyline (iterative)."""
    pts = np.asarray(pts, float)
    if len(pts) < 3:
        return pts.tolist()
    keep = np.zeros(len(pts), bool)
    keep[[0, -1]] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, ab = pts[i], pts[j] - pts[i]
        seg = pts[i + 1:j]
        n = np.hypot(*ab)
        d = np.hypot(*(seg - a).T) if n == 0 else np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / n
        k = int(np.argmax(d))
        if d[k] > eps:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return pts[keep].tolist()


def rdp_closed(loop, eps):
    p = np.asarray(loop, float)
    k = int(np.argmax(np.hypot(*(p - p[0]).T)))
    return rdp(p[:k + 1], eps)[:-1] + rdp(np.vstack([p[k:], p[:1]]), eps)[:-1]


def loops(mask):
    """Boundary loops of a binary mask along pixel edges, outer boundaries and holes alike,
    as lists of (x, y) corners. Filled with the even-odd rule they reproduce the mask."""
    m = np.pad(mask, 1)
    nxt: dict[tuple, list] = {}
    for edge, (dx0, dy0, dx1, dy1) in (
            (m & ~np.roll(m, 1, 0), (1, 0, 0, 0)),      # top edge, leftwards
            (m & ~np.roll(m, -1, 0), (0, 1, 1, 1)),     # bottom edge, rightwards
            (m & ~np.roll(m, 1, 1), (0, 0, 0, 1)),      # left edge, downwards
            (m & ~np.roll(m, -1, 1), (1, 1, 1, 0))):    # right edge, upwards
        ys, xs = np.nonzero(edge)
        for y, x in zip(ys.tolist(), xs.tolist()):
            nxt.setdefault((x + dx0 - 1, y + dy0 - 1), []).append((x + dx1 - 1, y + dy1 - 1))
    out = []
    while nxt:
        start = next(iter(nxt))
        cur, loop = start, [start]
        while True:
            ends = nxt[cur]
            nx = ends.pop()
            if not ends:
                del nxt[cur]
            cur = nx
            if cur == start:
                break
            loop.append(cur)
        # drop corners where the direction does not change
        p = np.array(loop)
        d0 = p - np.roll(p, 1, 0)
        d1 = np.roll(p, -1, 0) - p
        turn = (d0[:, 0] * d1[:, 1] - d0[:, 1] * d1[:, 0]) != 0
        if turn.sum() >= 3:
            out.append(p[turn].tolist())
    return out


def edt_in(comp):
    """Distance of each ink pixel to the nearest blank pixel (the crop's edge counts as blank)."""
    return ndi.distance_transform_edt(np.pad(comp, 1))[1:-1, 1:-1]


def stroke_width(comp):
    edt = edt_in(comp)
    ridge = edt[comp & (edt >= ndi.maximum_filter(edt, 3))]
    return float(np.clip(2 * np.median(ridge) - 0.7, 1.0, 40.0)) if ridge.size else 1.0


def colour_of(px):
    c = np.median(px, 0)
    lum = float(luminance(c[None])[0])
    sat = (c.max() - c.min()) / max(c.max(), 1)
    if lum < 110 and sat < 0.3:
        return "#000000"
    return "#%02x%02x%02x" % tuple(int(v) for v in np.clip(c, 0, 255))


def _check(comp, draw, sw):
    """How well a drawn centre-line matches the ink: (recall along the line, precision of the ink)."""
    h, w = comp.shape
    canvas = Image.new("L", (w, h), 0)
    draw(ImageDraw.Draw(canvas), int(round(sw + 4)), 255)
    near = np.asarray(canvas) > 0
    prec = (comp & near).sum() / max(comp.sum(), 1)
    thin = Image.new("L", (w, h), 0)
    draw(ImageDraw.Draw(thin), 1, 255)
    line = np.asarray(thin) > 0
    dist = ndi.distance_transform_edt(~np.pad(comp, 1, constant_values=True))[1:-1, 1:-1]
    rec = (dist[line] <= sw / 2 + 1.5).mean() if line.any() else 0.0
    return float(rec), float(prec)


def fit(comp, sw):
    """Try a straight line, an ellipse and a polygon (in that order) for one stroke piece."""
    ys, xs = np.nonzero(comp)
    pts = np.stack([xs, ys], 1).astype(float) + 0.5
    mean = pts.mean(0)
    u, s, vt = np.linalg.svd(pts - mean, full_matrices=False)
    t = (pts - mean) @ vt[0]
    perp = np.abs((pts - mean) @ vt[1])
    if np.percentile(perp, 95) <= sw / 2 + 1.2 and t.max() - t.min() >= 3 * sw:
        return {"kind": "line", "points": [(mean + t.min() * vt[0]).tolist(), (mean + t.max() * vt[0]).tolist()]}
    filled = ndi.binary_fill_holes(comp)
    if (filled & ~comp).sum() < 0.15 * filled.sum():
        return None                                         # not a closed outline
    h, w = comp.shape
    rx, ry = (w - sw) / 2, (h - sw) / 2
    if rx > 2 and ry > 2:
        box = [sw / 2, sw / 2, w - sw / 2, h - sw / 2]
        rec, prec = _check(comp, lambda d, wd, f: d.ellipse(box, outline=f, width=wd), sw)
        if rec > 0.93 and prec > 0.93:
            return {"kind": "ellipse", "box": box}
    outer = max(loops(filled), key=len)
    inner = loops(ndi.binary_fill_holes(comp) & ~comp)
    if not inner:
        return None
    inner = max(inner, key=len)
    po = rdp_closed(outer, max(2.0, sw))
    pi = rdp_closed(inner, max(2.0, sw))
    if not 3 <= len(po) <= 10 or len(po) != len(pi):
        return None
    pi = np.array(pi)
    mid = [((np.array(p) + pi[np.argmin(np.hypot(*(pi - p).T))]) / 2).tolist() for p in po]
    rec, prec = _check(comp, lambda d, wd, f: d.polygon([tuple(p) for p in mid], outline=f, width=wd), sw)
    if rec > 0.93 and prec > 0.93:
        return {"kind": "polygon", "points": mid}
    return None


def colour_groups(rgb, mask, palette):
    """Split ink by colour so crossing chart lines of different colours stay separate:
    0 = black/grey ink, k = the k-th palette colour. Pale fringes join the colour they border."""
    group = np.zeros(mask.shape, np.int16)
    if not palette:
        return group
    pal = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in palette], np.float32)
    mx, mn = rgb.max(-1), rgb.min(-1)
    coloured = mask & ((mx - mn) / np.maximum(mx, 1) > 0.25)
    px = rgb[coloured]
    d = np.linalg.norm(px[:, None, :] - pal[None], axis=-1)
    near = d.min(1) < 110
    g = np.zeros(len(px), np.int16)
    g[near] = d[near].argmin(1) + 1
    group[coloured] = g
    has = group > 0
    if has.any():
        dist, (iy, ix) = ndi.distance_transform_edt(~has, return_indices=True)
        fringe = mask & ~has & (dist <= 2.5)
        group[fringe] = group[iy[fringe], ix[fringe]]
    return group


def find_shapes(rgb, drawn_ink, word_boxes, text_size, palette=(), ink_level=165, max_points=40000):
    """Leftover drawing ink -> vector shapes. `drawn_ink` is what the draft already draws
    (rendered at scan resolution), `word_boxes` the OCR words kept as text, `palette` the
    page's ink colours (probe colour_regions)."""
    scan = ndi.binary_opening(ink_mask(rgb, ink_level), np.ones((2, 2), bool))
    disk = ndi.iterate_structure(ndi.generate_binary_structure(2, 1), 3)
    explained = ndi.binary_dilation(drawn_ink, disk)
    words = np.zeros(scan.shape, bool)
    for x0, y0, x1, y1 in word_boxes:
        words[max(y0 - 3, 0):y1 + 3, max(x0 - 3, 0):x1 + 3] = True
    rest = scan & ~explained & ~words
    # take back the ink right around each leftover piece, so an arrowhead split by the shaft
    # drawn through it is traced whole, and note which pieces touch something already drawn
    near = ndi.binary_dilation(rest, ndi.iterate_structure(ndi.generate_binary_structure(2, 1), 4))
    attached = near & drawn_ink
    rest = (rest | (near & scan)) & ~words
    group = colour_groups(rgb, rest, list(dict.fromkeys(palette)))
    lab = np.zeros(rest.shape, np.int32)
    n = 0
    for g in np.unique(group[rest]):
        lg, k = ndi.label(rest & (group == g), np.ones((3, 3), bool))
        lab[lg > 0] = lg[lg > 0] + n
        n += k
    H, W = rest.shape
    shapes, left, budget = [], [], max_points
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        if sl is None:
            continue
        comp = lab[sl] == i
        area = int(comp.sum())
        y0, x0, y1, x1 = sl[0].start, sl[1].start, sl[0].stop, sl[1].stop
        if area < 25:
            continue
        if x0 <= 2 or y0 <= 2 or x1 >= W - 2 or y1 >= H - 2:
            continue                                        # page edge: shadow or background, not content
        h, w = y1 - y0, x1 - x0
        edt_max = float(edt_in(comp).max())
        solid = min(h, w) >= 4 and edt_max >= 0.3 * min(h, w) / 2 + 1
        sw = stroke_width(comp)
        if max(h, w) < 1.5 * text_size and not solid and not attached[sl][comp].any():
            left.append([x0, y0, x1, y1])                  # text-sized and on its own: maybe a letter OCR missed
            continue
        colour = colour_of(rgb[sl][comp])
        shape = None if solid else fit(comp, sw)
        if shape:
            if "points" in shape:
                shape["points"] = [[round(x + x0, 1), round(y + y0, 1)] for x, y in shape["points"]]
            if "box" in shape:
                b = shape["box"]
                shape["box"] = [round(b[0] + x0, 1), round(b[1] + y0, 1), round(b[2] + x0, 1), round(b[3] + y0, 1)]
            shape.update(width=round(sw, 1), color=colour)
            if shape["kind"] == "polygon":
                shape["closed"] = True
            shapes.append(shape)
            continue
        paths = [rdp_closed(lp, 0.8) for lp in loops(comp)]
        paths = [[[round(x + x0, 1), round(y + y0, 1)] for x, y in p] for p in paths if len(p) >= 3]
        npts = sum(len(p) for p in paths)
        if not paths or len(paths) > 60 or npts > budget:
            left.append([x0, y0, x1, y1])                  # texture (photo, engraving): leave for a crop
            continue
        budget -= npts
        shapes.append({"kind": "outline", "paths": paths, "color": colour, "box": [x0, y0, x1, y1]})
    return shapes, left
