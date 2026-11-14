"""Render a UPG-2 post's templates into G-code, for testing without UPG-2.

This approximates what the compiled post writes: it expands the template tags
this post uses, prints a modal G or M code only when its group changes (as the
`<G:..>` form does; `<G!:..>` always prints), and drives the sections in the
order CAMWorks calls them for a simple two-tool job. It is a model of the
post's output, not the output itself: the real check is posting a part from
CAMWorks with the compiled GRBL.ctl.
"""

import re

GROUPED = re.compile(r"GC\((\w+)\)\s*=\s*(\d+)\s+GG\(\w+\)\s*=\s*(\d+)\s+GM\(\w+\)\s*=\s*(\w+)")
MGROUPED = re.compile(r"MC\((\w+)\)\s*=\s*(\d+)\s+MG\(\w+\)\s*=\s*(\d+)\s+MM\(\w+\)\s*=\s*(\w+)")


def sections(src):
    """{name: [template, ...]} for every live (not "*"-commented) section."""
    out, cur = {}, None
    for line in src.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^:SECTION=(\S+)$", line)
        if m:
            cur = out.setdefault(m.group(1), [])
        elif line.startswith(":T:") and cur is not None:
            cur.append(line[3:])
        elif not line.startswith(":C:"):
            cur = None if line.startswith("*") or line.startswith(":") else cur
    return out


def groups(src, pattern):
    """code -> (group, modal) from the post's own CALC_INIT tables."""
    table = {}
    for code, num, group, modal in pattern.findall(src):
        table.setdefault(num, (int(group), modal == "YES"))
    return table


class Post:
    def __init__(self, src):
        self.sec = sections(src)
        self.gtab = groups(src, GROUPED)
        self.mtab = groups(src, MGROUPED)
        self.state = {}
        self.ctx = {"tool": 1, "speed": 18000, "x": 0.0, "y": 0.0, "z": 0.0, "i": 0.0, "j": 0.0,
                    "f": 500.0, "arc": "2", "rapid_plane": 5.0, "cw_dwell": 0.0, "units": "21",
                    "z_clear": 2.0, "z_depth": -5.0, "post_dwell": 0.0,
                    "tool_comment": "(T1 6.35 MM FLAT END MILL)", "machine": "LongMill",
                    "controller": "Grbl 1.1 or grblHAL"}
        self.out = []

    def code(self, letter, value, forced):
        table = self.gtab if letter == "G" else self.mtab
        group, modal = table.get(value, (None, False))
        key = (letter, group)
        if modal and group is not None and not forced and self.state.get(key) == value:
            return ""
        if modal and group is not None:
            self.state[key] = value
        return f" {letter}{value}"

    def value(self, letter, v, forced, modal=True):
        text = f"{v:.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
        if text == "-0":
            text = "0"
        key = ("word", letter)
        if modal and not forced and self.state.get(key) == text:
            return ""
        self.state[key] = text
        return f" {letter}{text}"

    def tag(self, t):
        c = self.ctx
        named = {"ABSINC": "90", "ARC_DIR": c["arc"], "PLANE": "17", "ENGMET": c["units"],
                 "work_coord": "54", "SPINDLE_DIR": "3"}
        m = re.fullmatch(r"([GM])(!?):(\w+)", t)
        if m:
            letter, bang, v = m.groups()
            if v == "COMP":
                return self.code("G", "40", False)
            v = named.get(v, v)
            return self.code(letter, str(int(v)), bool(bang))
        m = re.fullmatch(r"([XYZF])(!?)", t)
        if m:
            return self.value(m.group(1), c[m.group(1).lower()], bool(m.group(2)))
        m = re.fullmatch(r"(W_COORD)(!?)", t)
        if m:
            return self.code("G", "54", bool(m.group(2)))
        simple = {
            "EOL": "\n", "BLANK": "", "N": "", "COMP_NUMBER": "",
            # A and B print nothing while USING_4TH_AXIS and USING_5TH_AXIS are NO.
            "A": "", "B": "", "A!": "", "B!": "",
            "Z_CLEAR": f" R{c['z_clear']:g}", "Z_DEPTH": f" Z{c['z_depth']:g}",
            "I": f" I{c['i']:.3f}".rstrip("0").rstrip("."), "J": f" J{c['j']:.3f}".rstrip("0").rstrip("."),
            "TOOL_COMMENT": " " + c["tool_comment"],
            "MACHINE_NAME": f" ( MACHINE={c['machine']} )", "CONTROLLER_TYPE": f" ( CONTROLLER={c['controller']} )",
        }
        if t in simple:
            return simple[t]
        if t in ("T",):
            return f" T{c['tool']}"
        if t in ("S", "S!"):
            return self.value("S", c["speed"], t == "S!")
        if t == "Z!:OPR_Z_RAPID_PLANE":
            c["z"] = c["rapid_plane"]
            return self.value("Z", c["z"], True)
        if t == "#:CW_DWELL":
            return f"{c['cw_dwell']:g}"
        if t == "#:POST_DWELL":
            return f"{c['post_dwell']:g}"
        raise ValueError(f"tag <{t}> is not modelled")

    def condition(self, text):
        """Evaluate "A AND B ..." left to right; stop at the first false term."""
        known = {"OPR_SPEED": self.ctx["speed"], "CW_DWELL": self.ctx["cw_dwell"],
                 # A 3-axis machine: no rotary locks, no reverse feedrate.
                 "USING_4TH_AXIS_LOCK": "NO", "USING_5TH_AXIS_LOCK": "NO", "USING_REVERSE_FEEDRATE": "NO"}
        for term in text.split(" AND "):
            m = re.fullmatch(r"(\w+)([=>])([\w.]+)", term.strip())
            if not m or m.group(1) not in known:
                raise ValueError(f"condition not modelled: {term}")
            name, op, want = m.groups()
            v = known[name]
            ok = (v == want) if isinstance(v, str) else ((v == float(want)) if op == "=" else (v > float(want)))
            if not ok:
                return False
        return True

    def render_line(self, template):
        m = re.fullmatch(r"IF (.*?) THEN (.*)ENDIF", template)
        if m:
            if not self.condition(m.group(1)):
                return ""
            template = m.group(2)
        return re.sub(r"<([^<>]+)>", lambda mm: self.tag(mm.group(1)), template)

    def emit(self, section, **ctx):
        self.ctx.update(ctx)
        if section not in self.sec:
            raise KeyError(f"section {section} is not defined")
        text = "".join(self.render_line(t) for t in self.sec[section])
        for line in text.split("\n"):
            line = line.strip()
            if line:
                self.out.append(re.sub(r"\s+", " ", line))


def sample_job(src):
    """A two-tool job: straight cuts and an arc, then a cut around the board with a speed change."""
    p = Post(src)
    p.emit("START_OF_TAPE")
    p.emit("INIT_TOOL_CHANGE_MILL", tool=1, speed=18000)
    p.emit("RAPID_FROM_TOOL_CHANGE_MILL", x=10.0, y=10.0)
    p.emit("RAPID_Z_MOVE_DOWN_MILL", z=5.0)
    p.emit("FEED_Z_MOVE_DOWN_MILL", z=-2.0, f=300.0)
    p.emit("LINE_MOVE_MILL", x=50.0, f=1000.0)
    p.emit("ARC_MOVE_MILL", arc="3", x=60.0, y=20.0, i=0.0, j=10.0)
    p.emit("LINE_MOVE_MILL", y=50.0)
    p.emit("RAPID_Z_MOVE_UP_MILL", z=5.0)
    p.emit("RAPID_MOVE_MILL", x=10.0, y=60.0)
    p.emit("RAPID_Z_MOVE_DOWN_MILL", z=1.0)
    p.emit("FEED_Z_MOVE_DOWN_MILL", z=-2.0, f=300.0)
    p.emit("LINE_MOVE_MILL", x=40.0, f=1000.0)
    p.emit("LAST_RAPID_Z_MOVE_UP_MILL", z=25.0)
    p.emit("SUB_TOOL_CHANGE_MILL", tool=2, speed=12000, tool_comment="(T2 3.175 MM FLAT END MILL)")
    p.emit("RAPID_FROM_TOOL_CHANGE_MILL", x=-5.0, y=-5.0)
    p.emit("RAPID_Z_MOVE_DOWN_MILL", z=5.0)
    p.emit("FEED_Z_MOVE_DOWN_MILL", z=-6.0, f=200.0)
    p.emit("LINE_MOVE_MILL", x=75.0, f=800.0)
    p.emit("CHANGE_MILL_SPEED", speed=15000)
    p.emit("LINE_MOVE_MILL", y=75.0)
    p.emit("OUTPUT_DWELL", cw_dwell=0.5)
    p.emit("LINE_MOVE_MILL", x=-5.0)
    p.emit("LAST_RAPID_Z_MOVE_UP_MILL", z=25.0)
    p.emit("END_OF_TAPE")
    return p.out


def drill_job(src):
    """One tool drilling two holes with a canned cycle, then the end."""
    p = Post(src)
    p.emit("START_OF_TAPE")
    p.emit("INIT_TOOL_CHANGE_MILL", tool=3, speed=10000)
    p.emit("RAPID_FROM_TOOL_CHANGE_MILL", x=20.0, y=20.0)
    p.emit("RAPID_Z_MOVE_DOWN_MILL", z=5.0)
    p.emit("DRILLING_CYCLE", z_clear=2.0, z_depth=-8.0, f=150.0)
    p.emit("CONTINUE_DRILL_CYCLE", x=40.0)
    p.emit("CANCEL_DRILL_CYCLE", rapid_plane=5.0)
    p.emit("LAST_RAPID_Z_MOVE_UP_MILL", z=25.0)
    p.emit("END_OF_TAPE")
    return p.out
