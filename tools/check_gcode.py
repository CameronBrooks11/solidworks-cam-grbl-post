#!/usr/bin/env python3
"""Check a posted G-code file before it goes to a Grbl or grblHAL machine.

usage: check_gcode.py [--controller grbl|grblhal] FILE...

Exits 1 and prints one line per problem when the file contains a code the
controller rejects, or a move this post should never make:

  unsupported   a G or M code, or a word letter, the controller does not accept
  bare-g53      G53 without G0 or G1 and an axis word on the same line: G53
                applies to its own line only, so a following "G0 Z-2" runs in
                work coordinates, below the work zero
  g53-z         a G53 Z above 0, which is above the homed position
  retract       a G53 X/Y move, a tool change (M6) or the program end (M2/M30)
                after cutting, with no G53 Z retract in between
  spindle-off   a cutting move (G1/G2/G3) while the spindle is stopped
  spindle-on    a tool change (M6) while the spindle is running
  units         a move before any G20 or G21
  dwell         G4 without P (P is seconds on both controllers)
  line-length   (grbl) more than 79 characters once spaces and comments are
                stripped, which overflows Grbl's line buffer

M6 is accepted on both: gSender turns it into a comment and runs its own tool
change unless its "passthrough" option is on, in which case Grbl 1.1 rejects it.
"""

import argparse
import re
import sys

# Grbl 1.1, gnea/grbl bfb67f0, grbl/gcode.c: the G and M cases and the word
# letters the parser accepts. M7 and M56 need build options and are left out.
GRBL = {
    "G": {"0", "1", "2", "3", "4", "10", "17", "18", "19", "20", "21", "28", "28.1", "30", "30.1",
          "38.2", "38.3", "38.4", "38.5", "40", "43.1", "49", "53", "54", "55", "56", "57", "58", "59",
          "61", "80", "90", "91", "91.1", "92", "92.1", "93", "94"},
    "M": {"0", "1", "2", "3", "4", "5", "6", "8", "9", "30"},
    "words": set("FGIJKLMNPRSTXYZ"),
    "line_max": 79,
}
# grblHAL core 3282140, gcode.c, default build: Grbl's set plus the canned
# cycles it implements and the Q word they use. Not G52, G74, G87 or G88.
GRBLHAL = {
    "G": GRBL["G"] | {"73", "81", "82", "83", "84", "85", "86", "89", "98", "99"},
    "M": GRBL["M"],
    "words": GRBL["words"] | {"Q"},
    "line_max": None,
}
CONTROLLERS = {"grbl": GRBL, "grblhal": GRBLHAL}


def strip(line):
    line = re.sub(r"\([^)]*\)?", "", line)
    return line.split(";", 1)[0].upper()


def words(text):
    return re.findall(r"([A-Z])\s*([-+]?(?:\d+\.?\d*|\.\d+))", text)


def norm(value):
    v = value.lstrip("+")
    return v.rstrip("0").rstrip(".") if "." in v else str(int(v))


def check(lines, controller):
    spec = CONTROLLERS[controller]
    problems = []
    motion = None          # modal G0/G1/G2/G3
    units = False
    spindle = False
    cut_since_retract = False

    def flag(n, rule, msg):
        problems.append((n, rule, msg))

    for n, raw in enumerate(lines, 1):
        text = strip(raw)
        compact = re.sub(r"\s", "", text)
        if not compact:
            continue
        if spec["line_max"] and len(compact) > spec["line_max"]:
            flag(n, "line-length", f"{len(compact)} characters once stripped")
        ws = words(text)
        if re.sub(r"[A-Z]\s*[-+]?(?:\d+\.?\d*|\.\d+)|\s", "", text):
            flag(n, "unsupported", f"cannot read {raw.strip()!r}")
        g = {norm(v) for k, v in ws if k == "G"}
        m = {norm(v) for k, v in ws if k == "M"}
        letters = {k for k, _ in ws}
        for k in sorted(letters - spec["words"]):
            flag(n, "unsupported", f"{k} word")
        for code in sorted(g - spec["G"], key=float):
            flag(n, "unsupported", f"G{code}")
        for code in sorted(m - spec["M"], key=float):
            flag(n, "unsupported", f"M{code}")

        if g & {"20", "21"}:
            units = True
        if g & {"0", "1", "2", "3"}:
            motion = sorted(g & {"0", "1", "2", "3"})[0]
        axes = letters & set("XYZ")
        if "4" in g and "P" not in letters:
            flag(n, "dwell", "G4 needs P (seconds)")
        if m & {"3", "4"}:
            spindle = True
        if "5" in m:
            spindle = False
        if any(k == "S" and float(v) == 0 for k, v in ws):
            spindle = False

        if "53" in g:
            if not (g & {"0", "1"}) or not axes:
                flag(n, "bare-g53", "G53 needs G0 or G1 and an axis word on its own line")
            elif axes & {"X", "Y"} and cut_since_retract:
                flag(n, "retract", "G53 X/Y move after cutting with no G53 Z retract first")
            if "Z" in axes and g & {"0", "1"}:
                cut_since_retract = False
                if any(k == "Z" and float(v) > 0 for k, v in ws):
                    flag(n, "g53-z", "G53 Z above 0 is past the top of travel on a homed machine")
        elif axes and motion is not None and not ("4" in g or g & {"10", "28", "30", "92"}):
            if not units:
                flag(n, "units", "move before any G20 or G21")
            if motion in {"1", "2", "3"} or g & {"73", "81", "82", "83", "84", "85", "86", "89"}:
                if not spindle:
                    flag(n, "spindle-off", "cutting move with the spindle stopped")
                cut_since_retract = True
        if "6" in m and spindle:
            flag(n, "spindle-on", "M6 with the spindle running: stop it with M5 first")
        if (m & {"6", "2", "30"}) and cut_since_retract:
            flag(n, "retract", f"M{sorted(m & {'6', '2', '30'})[0]} after cutting with no G53 Z retract first")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--controller", choices=sorted(CONTROLLERS), default="grbl",
                    help="grbl is the stricter of the two and the default")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    bad = 0
    for f in a.files:
        lines = open(f, encoding="latin-1").read().splitlines()
        problems = check(lines, a.controller)
        for n, rule, msg in problems:
            print(f"{f}:{n}: {rule}: {msg}")
        bad += len(problems)
        if not problems:
            print(f"{f}: ok for {a.controller} ({len(lines)} lines)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
