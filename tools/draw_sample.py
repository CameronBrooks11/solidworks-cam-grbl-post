#!/usr/bin/env python3
"""Draw images/sample_job.svg: the two-tool job tests/render_post.py renders
from GRBL.SRC, from above, in work coordinates. Cuts are solid, rapids dashed;
the G53 moves to the top of travel and the home corner are left out, since
they are in machine coordinates.

usage: draw_sample.py OUT.svg
"""
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import render_post  # noqa: E402

lines = render_post.sample_job(open(os.path.join(ROOT, "GRBL.SRC"), encoding="latin-1").read())

W, H, M = 520, 470, 40
X0, X1, Y0, Y1 = -15.0, 85.0, -15.0, 85.0


def px(x, y):
    return M + (x - X0) / (X1 - X0) * (W - 2 * M), M + (Y1 - y) / (Y1 - Y0) * (H - 2 * M - 50)


colours = {1: "#1565c0", 2: "#2e7d32"}
segs, pos, mode, tool, marks = [], [0.0, 0.0], "0", 1, []
for line in lines:
    w = dict(re.findall(r"([A-Z])([-\d.]+)", re.sub(r"\(.*?\)", "", line)))
    if "T" in w:
        tool = int(w["T"])
    if "G53" in line:
        continue
    for g in re.findall(r"G(\d+)", line):
        if g in ("0", "1", "2", "3"):
            mode = g
    if "X" not in w and "Y" not in w:
        continue
    end = [float(w.get("X", pos[0])), float(w.get("Y", pos[1]))]
    if mode in ("2", "3"):
        cx, cy = pos[0] + float(w.get("I", 0)), pos[1] + float(w.get("J", 0))
        a0, a1 = math.atan2(pos[1] - cy, pos[0] - cx), math.atan2(end[1] - cy, end[0] - cx)
        if mode == "3" and a1 <= a0:
            a1 += 2 * math.pi
        if mode == "2" and a1 >= a0:
            a1 -= 2 * math.pi
        r = math.hypot(pos[0] - cx, pos[1] - cy)
        pts = [(cx + r * math.cos(a0 + (a1 - a0) * k / 24), cy + r * math.sin(a0 + (a1 - a0) * k / 24)) for k in range(25)]
    else:
        pts = [tuple(pos), tuple(end)]
    if pos != end or mode in ("2", "3"):
        segs.append((pts, mode == "0", tool))
    if mode == "0" and not marks or (marks and marks[-1][1] != tool and mode == "0"):
        marks.append((tuple(end), tool))
    pos = end

out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
       'font-family="Helvetica, Arial, sans-serif" font-size="13">', f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
bx0, by0 = px(0, 70)
bx1, by1 = px(70, 0)
out.append(f'<rect x="{bx0:.1f}" y="{by0:.1f}" width="{bx1 - bx0:.1f}" height="{by1 - by0:.1f}" fill="#f1e4cf" stroke="#c9ad80"/>')
for pts, rapid, t in segs:
    d = " ".join(f"{'M' if i == 0 else 'L'}{px(*p)[0]:.1f},{px(*p)[1]:.1f}" for i, p in enumerate(pts))
    style = 'stroke="#9e9e9e" stroke-dasharray="5 4" stroke-width="1.5"' if rapid else f'stroke="{colours[t]}" stroke-width="3"'
    out.append(f'<path d="{d}" fill="none" {style}/>')
for (x, y), t in marks:
    cx, cy = px(x, y)
    out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{colours[t]}"/>')
    out.append(f'<text x="{cx + 8:.1f}" y="{cy - 8:.1f}" fill="#333">T{t} starts</text>')
ly = H - 40
out += [f'<rect x="{M}" y="{ly}" width="14" height="4" fill="{colours[1]}"/>',
        f'<text x="{M + 20}" y="{ly + 6}" fill="#333">T1: straight cuts and an arc, 2 mm deep</text>',
        f'<rect x="{M}" y="{ly + 18}" width="14" height="4" fill="{colours[2]}"/>',
        f'<text x="{M + 20}" y="{ly + 24}" fill="#333">T2: around the board, 6 mm deep, with a speed change</text>',
        f'<line x1="{W / 2 + 40}" y1="{ly + 2}" x2="{W / 2 + 54}" y2="{ly + 2}" stroke="#9e9e9e" stroke-dasharray="5 4" stroke-width="1.5"/>',
        f'<text x="{W / 2 + 60}" y="{ly + 6}" fill="#333">rapid at clearance</text>', "</svg>"]
open(sys.argv[1], "w").write("\n".join(out) + "\n")
