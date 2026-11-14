#!/usr/bin/env python3
"""Draw images/start_of_job.svg: the tool's path at the start of a job, seen
from the front, for the old post and for this one.

The old moves are the first tool change and first rapid in the GRBL-Post.ctl
compiled in May 2025 ("G0 G53 X0 Y0", then "G0 Z-2" in work coordinates, then
"G0 X10 Y10"). The new moves are what tests/render_post.py renders from
GRBL.SRC. The machine is homed at the back right (machine X0 Z0), with work
zero on the top of a 19 mm board whose left edge is 700 mm from home.

usage: draw_start.py OUT.svg
"""
import sys

WORK_X, WORK_Z = -700.0, -80.0          # G54 origin in machine coordinates
STOCK = (-700.0, -560.0, -80.0, -99.0)  # x0, x1, top, bottom

# The old path is drawn as far as the board: it does not get past it.
old = [(0, -1), (0, WORK_Z - 2), (STOCK[1], WORK_Z - 2)]
new = [(0, -1), (0, -2), (WORK_X + 10, -2), (WORK_X + 10, WORK_Z + 5)]
crash_x = STOCK[1]                      # the old path meets the board's right edge here

W, H, M = 760, 360, 40
X0, X1, Z0, Z1 = -760.0, 30.0, -110.0, 10.0


def px(x, z):
    return M + (x - X0) / (X1 - X0) * (W - 2 * M), M + (Z1 - z) / (Z1 - Z0) * (H - 2 * M - 40)


def path(points):
    return " ".join(f"{'M' if i == 0 else 'L'}{px(x, z)[0]:.1f},{px(x, z)[1]:.1f}" for i, (x, z) in enumerate(points))


sx0, sz0 = px(STOCK[0], STOCK[2])
sx1, sz1 = px(STOCK[1], STOCK[3])
cx, cz = px(crash_x, WORK_Z - 2)
hx, hz = px(0, 0)
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif" font-size="13">
<rect width="{W}" height="{H}" fill="#ffffff"/>
<rect x="{sx0:.1f}" y="{sz0:.1f}" width="{sx1 - sx0:.1f}" height="{sz1 - sz0:.1f}" fill="#d9b98c" stroke="#8a6a3a"/>
<text x="{(sx0 + sx1) / 2:.1f}" y="{sz1 + 18:.1f}" text-anchor="middle" fill="#333">board, work Z0 on its top</text>
<line x1="{M}" y1="{px(0, -2)[1]:.1f}" x2="{W - M}" y2="{px(0, -2)[1]:.1f}" stroke="#bbb" stroke-dasharray="4 4"/>
<text x="{(M + W) / 2:.0f}" y="{px(0, -2)[1] - 8:.1f}" text-anchor="middle" fill="#666">machine Z -2, just below the top of travel</text>
<path d="{path(old)}" fill="none" stroke="#c62828" stroke-width="3"/>
<path d="{path(new)}" fill="none" stroke="#1565c0" stroke-width="3"/>
<circle cx="{cx:.1f}" cy="{cz:.1f}" r="9" fill="none" stroke="#c62828" stroke-width="2.5"/>
<text x="{cx + 14:.1f}" y="{cz + 26:.1f}" fill="#c62828">rapid into the board, 2 mm below its top</text>
<circle cx="{hx:.1f}" cy="{hz:.1f}" r="5" fill="#333"/>
<text x="{hx + 8:.1f}" y="{hz - 10:.1f}" text-anchor="end" fill="#333">homed</text>
<rect x="{M}" y="{H - 34}" width="14" height="4" fill="#c62828"/>
<text x="{M + 20}" y="{H - 28}" fill="#333">old post: G0 G53 X0 Y0, G0 Z-2 (work), G0 X10 Y10</text>
<rect x="{M}" y="{H - 16}" width="14" height="4" fill="#1565c0"/>
<text x="{M + 20}" y="{H - 10}" fill="#333">this post: G21 G53 G0 Z-2 (machine), G0 X10 Y10, Z5</text>
</svg>
"""
open(sys.argv[1], "w").write(svg)
