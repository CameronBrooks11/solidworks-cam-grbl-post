"""Check GRBL.SRC and tools/check_gcode.py without UPG-2 or CAMWorks.

usage: python3 tests/test_post.py

1. GRBL.SRC is well formed the way UPG-2 writes it: CRLF line endings, every
   section closed by "*", no blank lines or stray text in a section, every
   template line ends in <EOL> (or ENDIF), and the library it names exists.
2. It uses only template tags that already compiled in an earlier post, plus
   the ones listed in NEW_TAGS.
3. A two-tool job rendered from the templates (tests/render_post.py) passes
   the checker for Grbl 1.1 and grblHAL; a canned drilling cycle passes on
   grblHAL and is rejected only for G81 on Grbl 1.1; on an inch job every G53
   retract is made in millimetres and the job's units restored on the next
   line; and a spot-drill dwell is written in seconds.
4. The checker flags each problem it names, on short programs that have it,
   including the two retracts of the post this one replaces.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tests"), os.path.join(ROOT, "tools")]
import check_gcode  # noqa: E402
import render_post  # noqa: E402

# Tags that appear in the templates of posts already compiled by UPG-2:
# msbealo/GRBL-Post (2021) and its 2025 fork, and euler357/Solidworks_Cam_Post.
PROVEN_TAGS = {
    "#:CW_DWELL", "#:POST_SHIFT", "%:((NUM_HITS-1)-SKIP_1ST_HIT)", "%:(POST_DWELL*1000)", "A", "A!", "B", "B!",
    "BLANK", "COMP_NUMBER", "CONTROLLER_TYPE", "EOL", "F", "F!", "G!:00", "G!:80", "G!:90", "G!:91",
    "G!:ENGMET", "G!:work_coord", "G:00", "G:01", "G:04", "G:40", "G:52", "G:73", "G:74", "G:76",
    "G:80", "G:81", "G:82", "G:83", "G:84", "G:85", "G:86", "G:87", "G:88", "G:89", "G:90", "G:91",
    "G:94", "G:17", "G:ABSINC", "G:ARC_DIR", "G:COMP", "G:F_TYPE", "G:GC(G_FPM)", "G:PLANE", "I", "J",
    "M!:COOLANT_TYPE", "M!:SPINDLE_DIR", "M:00", "M:01", "M:05", "M:06", "M:09", "M:30", "M:98", "M:99",
    "M:A_LOCK", "M:B_LOCK", "M:MC(M_LOCK_5OFF)", "M:MC(M_LOCK_5ON)", "M:MC(M_LOCK_OFF)", "M:MC(M_LOCK_ON)",
    "M:SPINDLE_DIR", "MACHINE_NAME", "N", "OPR_COMMENT", "PART_NAME", "R", "S", "S!", "S_MATERIAL",
    "S_PROGRAM_NUMBER", "S_THICKNESS", "SUB_PECK", "T", "TOOL_COMMENT", "W_COORD", "W_COORD!", "X", "X!",
    "X_OFFSET", "Y", "Y!", "Y_OFFSET", "Z", "Z!", "Z!:OPR_Z_RAPID_PLANE", "Z_CLEAR", "Z_DEPTH", "Z_OFFSET",
    "attributes", '"#3.3N":ROTATE_ANGLE_X', '"#3.3N":ROTATE_ANGLE_Y', '"#3.3N":ROTATE_ANGLE_Z',
    '"%4LT":(program_number+CURRENT_MACRO_NUMBER)',
}
# New here: the spot-drill dwell in seconds, in the same "#:" form as the two
# above. Confirmed only when GRBL.SRC compiles.
NEW_TAGS = {"#:POST_DWELL"}

failures = []


def report(label, ok, got=""):
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f": {got}" if got else ""))
    if not ok:
        failures.append(label)


def problems(text, controller="grbl"):
    return [(rule, msg) for _, rule, msg in check_gcode.check(text.strip().splitlines(), controller)]


def main():
    raw = open(os.path.join(ROOT, "GRBL.SRC"), "rb").read()
    src = raw.decode("latin-1")
    lines = src.split("\r\n")

    # 1. Form.
    report("GRBL.SRC has CRLF line endings throughout", b"\n" not in raw.replace(b"\r\n", b""))
    lib = re.findall(r"^:LIBRARY=\.\\(\S+)$", src.replace("\r\n", "\n"), re.M)
    report("GRBL.SRC names GRBL.LIB, which is here", lib == ["GRBL.LIB"] and os.path.exists(os.path.join(ROOT, "GRBL.LIB")),
           str(lib))
    bad, open_section = [], None
    for n, line in enumerate(lines, 1):
        if re.match(r"^:SECTION=", line):
            if open_section:
                bad.append(f"line {n}: section at line {open_section} not closed")
            open_section = n
        elif open_section:
            if line == "*":
                open_section = None
            elif line.startswith(":T:"):
                if not (line.endswith("<EOL>") or line.endswith("ENDIF")):
                    bad.append(f"line {n}: template does not end in <EOL>: {line}")
            elif not line.startswith(":C:") and not line.startswith("*"):
                bad.append(f"line {n}: {line!r} inside a section")
    report("every section is closed by '*' and holds only template or calc lines", not bad, "; ".join(bad[:3]))

    # 2. Tags.
    used = set(re.findall(r"<([^<>]+)>", "\n".join(l for l in lines if l.startswith(":T:"))))
    unknown = used - PROVEN_TAGS - NEW_TAGS
    report("every template tag compiled in an earlier post, or is listed as new", not unknown, ", ".join(sorted(unknown)))

    # 3. Rendered jobs.
    try:
        sample = render_post.sample_job(src)
        drill = render_post.drill_job(src)
    except (ValueError, KeyError) as e:
        report("the templates render", False, str(e))
        print(f"{len(failures)} failed")
        return 1
    for ctl in ("grbl", "grblhal"):
        p = check_gcode.check(sample, ctl)
        report(f"the two-tool job passes the checker for {ctl}", not p, "; ".join(f"{n}:{r}:{m}" for n, r, m in p[:3]))
    report("a canned drilling cycle passes on grblHAL", not check_gcode.check(drill, "grblhal"))
    p = [(r, m) for _, r, m in check_gcode.check(drill, "grbl")]
    report("on Grbl 1.1 it is rejected for G81 alone", p == [("unsupported", "G81")], str(p))

    inch = render_post.Post(src)
    inch.ctx["units"] = "20"
    try:
        for section in ("START_OF_TAPE", "INIT_TOOL_CHANGE_MILL", "SUB_TOOL_CHANGE_MILL", "END_OF_TAPE"):
            inch.emit(section)
    except (ValueError, KeyError) as e:
        report("the inch job renders", False, str(e))
    retracts = [i for i, l in enumerate(inch.out) if "G53" in l and "Z" in l]
    ok = retracts and all("G21" in inch.out[i] and inch.out[i + 1] == "G20" for i in retracts)
    report("on an inch job each G53 Z retract is in mm and G20 follows", bool(ok),
           " | ".join(inch.out[i] + " / " + inch.out[i + 1] for i in retracts))

    spot = render_post.Post(src)
    spot.ctx.update(post_dwell=0.5)
    try:
        spot.emit("SPOT_DRILLING_CYCLE")
    except (ValueError, KeyError) as e:
        report("the spot drill renders", False, str(e))
    dwell = re.findall(r"P([\d.]+)", " ".join(spot.out))
    report("a 0.5 s spot-drill dwell is written as P0.5", dwell == ["0.5"], " ".join(spot.out))

    # 4. The checker's rules.
    cases = [
        ("bare G53, as the replaced post wrote it", "G21\nG53\nG0 Z-2\n", "grbl", [("bare-g53", None)]),
        ("X/Y park before the retract, as its 2025 fork wrote it",
         "G21\nM3 S1000\nG1 Z-1 F100\nG0 Z5\nG0 G53 X0 Y0\nG0 Z-2\nM30\n", "grbl",
         [("retract", None), ("retract", None)]),
        ("G52, M98 and A words", "G21\nG52 X1\nM98 P1000\nG0 A10\n", "grblhal",
         [("unsupported", "G52"), ("unsupported", "M98"), ("unsupported", "A word")]),
        ("Q on Grbl 1.1", "G21\nM3\nG83 X1 Y1 R1 Z-1 Q1 F100\n", "grbl",
         [("unsupported", "Q word"), ("unsupported", "G83")]),
        ("G4 X in place of P", "G4 X1\n", "grbl", [("dwell", None)]),
        ("80 characters overflow Grbl's buffer", "G21\nG0X1.00000" + "X1.0000" * 10 + "\n", "grbl", [("line-length", None)]),
        ("79 characters fit", "G21\nG0" + "X1.0000" * 11 + "\n", "grbl", []),
        ("a G53 Z above home", "G21\nG53 G0 Z2\n", "grbl", [("g53-z", None)]),
        ("a move before units", "G0 X1\nG21\n", "grbl", [("units", None)]),
        ("cutting with the spindle off", "G21\nG1 X1 F100\n", "grbl", [("spindle-off", None)]),
        ("S0 stops the spindle", "G21\nM3 S1000\nS0\nG1 X1 F100\n", "grbl", [("spindle-off", None)]),
        ("a tool change with the spindle on", "G21\nM3 S1000\nG21 G53 G0 Z-2\nM6 T2\n", "grbl", [("spindle-on", None)]),
        ("a tool change after cutting with no retract", "G21\nM3\nG1 Z-1 F100\nM5\nM6 T2\n", "grbl", [("retract", None)]),
        ("a correct tool change and end", "G21\nM3 S1000\nG1 Z-1 F100\nG0 Z5\nG21 G53 G0 Z-2\nM5\nM6 T2\nM3\n"
         "G1 Z-1\nG53 G0 Z-2\nM5\nG53 G0 X0 Y0\nM30\n", "grbl", []),
        ("comments are ignored", "(G52 M98 A1)\nG21 ; G81\n", "grbl", []),
    ]
    for label, text, ctl, want in cases:
        got = problems(text, ctl)
        ok = len(got) == len(want) and all(r == wr and (wm is None or m == wm) for (r, m), (wr, wm) in zip(got, want))
        report(f"checker: {label}", ok, str(got) if not ok else "")

    # The command line exits 1 on a problem and 0 on a clean file.
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"check_gcode_{os.getpid()}.nc")
    try:
        open(tmp, "w").write("G21\nG53\n")
        bad_rc = check_gcode.main([tmp])
        open(tmp, "w").write("\n".join(sample) + "\n")
        good_rc = check_gcode.main(["--controller", "grblhal", tmp])
    finally:
        os.remove(tmp)
    report("check_gcode.py exits 1 on a problem and 0 on a clean file", (bad_rc, good_rc) == (1, 0), f"{bad_rc}, {good_rc}")

    print("all checks passed" if not failures else f"{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
