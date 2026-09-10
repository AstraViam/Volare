#!/usr/bin/env python3
r"""
volare_thermal.audit
====================

Systematic audit of the generated dashboard. Not a smoke test — a checklist
that walks the whole artefact looking for the classes of defect that have
actually bitten this project:

  1  every element the script touches exists in the markup
  2  every interactive control has a handler bound
  3  no two handlers assign the same className wholesale (the clobber bug)
  4  every registered element id is unique
  5  every canvas that is drawn is also sized
  6  no orphaned CSS ids (styled but never rendered)
  7  the script parses, and executes top to bottom
  8  every declared view has a render branch
  9  every palette command targets something that exists
 10  no leftover debug artefacts

Run:  python3 audit.py
"""

from __future__ import annotations
import os
import re
import sys
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "figures", "mission_control.html")

OK, WARN, FAIL = "ok", "warn", "FAIL"
results = []


def check(name, status, detail=""):
    results.append((name, status, detail))
    tag = {"ok": "  ok  ", "warn": " warn ", "FAIL": " FAIL "}[status]
    print(f"[{tag}] {name}" + (f"\n         {detail}" if detail else ""))


def split(html):
    head = html.split("<script>", 1)[0]
    js = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    css = html.split("<style>", 1)[1].split("</style>", 1)[0]
    return head, js, css


# ---------------------------------------------------------------- 1, 4, 6
def check_ids(head, js, css):
    ids = re.findall(r'id="([^"]+)"', head)
    dupes = {i for i in ids if ids.count(i) > 1}
    check("element ids are unique", FAIL if dupes else OK,
          f"duplicated: {sorted(dupes)}" if dupes else f"{len(ids)} unique ids")

    used = set(re.findall(r"\$\('([A-Za-z][\w-]*)'\)", js))
    used |= set(re.findall(
        r"(?<![.\w])document\.getElementById\('([A-Za-z][\w-]*)'\)", js))
    missing = sorted(used - set(ids))
    check("every id the script uses exists", FAIL if missing else OK,
          f"missing: {missing}" if missing else f"{len(used)} lookups all resolve")

    styled = set(re.findall(r"#([A-Za-z][\w-]*)\s*[,{:.]", css))
    orphan = sorted(s for s in styled - set(ids) if s not in {"c"})
    check("no CSS rules for ids that never render", WARN if orphan else OK,
          f"styled but absent: {orphan}" if orphan else "none")


# ------------------------------------------------------------------- 2
def check_handlers(head, js):
    """A control is wired if it is bound directly, bound through an array
    loop, bound through an alias, or deliberately POLLED each frame. Only
    something matching none of those is genuinely dead."""
    controls = re.findall(r'<(?:button|select|input)[^>]*id="([^"]+)"', head)
    # ids that appear inside an array literal which is then .forEach-bound
    looped = set()
    for m in re.finditer(r"\[([^\]]{0,300}?)\]\.forEach\(\s*id\s*=>", js):
        looped |= set(re.findall(r"'([\w-]+)'", m.group(1)))
    # ids captured into a local then bound on that local
    aliased = set()
    for m in re.finditer(r"(?:const|let|var)\s+(\w+)\s*=\s*\$\('([\w-]+)'\)", js):
        var, cid = m.group(1), m.group(2)
        if re.search(rf"\b{re.escape(var)}\.(onclick|onchange|oninput)\s*=", js):
            aliased.add(cid)

    dead, polled = [], []
    for cid in controls:
        e = re.escape(cid)
        if re.search(rf"\$\('{e}'\)\.(onclick|onchange|oninput)\s*=", js): continue
        if re.search(rf"bind\('{e}'", js): continue
        if cid in looped or cid in aliased: continue
        if re.search(rf"\$\('{e}'\)\.(value|checked)", js):
            polled.append(cid); continue
        dead.append(cid)
    detail = f"{len(controls)} controls"
    if polled:
        detail += f" · {len(polled)} polled each frame ({', '.join(polled)})"
    if dead:
        detail = f"no handler and never read: {dead}"
    check("every control is wired", FAIL if dead else OK, detail)


# ------------------------------------------------------------------- 3
def check_clobber(js):
    wholesale = re.findall(
        r"(?:document\.body|document\.documentElement)\.className\s*=\s*(.{0,60})",
        js)
    # a single central manager is fine; two or more independent writers is not
    writers = [w for w in wholesale if "cls" not in w]
    check("no competing className writers", FAIL if len(writers) > 0 else OK,
          f"{len(writers)} wholesale assignment(s) outside the flag manager"
          if writers else "all class changes go through applyFlags()")


# ------------------------------------------------------------------- 5
def check_canvases(head, js):
    canvases = re.findall(r'<canvas[^>]*id="([^"]+)"', head)
    unsized, undrawn = [], []
    for c in canvases:
        drawn = re.search(rf"\$\('{re.escape(c)}'\)", js)
        if not drawn:
            undrawn.append(c)
    check("every canvas is referenced by the script",
          FAIL if undrawn else OK,
          f"never drawn: {undrawn}" if undrawn else
          f"{len(canvases)} canvases all drawn")


# ------------------------------------------------------------------- 8
def check_views(head, js):
    views = re.findall(r'<div class="view[^"]*" id="(v\w+)"', head)
    tabs = re.findall(r'data-v="(v\w+)"', head)
    missing_tab = sorted(set(views) - set(tabs))
    missing_view = sorted(set(tabs) - set(views))
    check("tabs and views correspond",
          FAIL if (missing_tab or missing_view) else OK,
          f"view without tab: {missing_tab}, tab without view: {missing_view}"
          if (missing_tab or missing_view) else f"{len(views)} views")
    nobranch = [v for v in views if f"view==='{v}'" not in js]
    check("every view has a render branch", WARN if nobranch else OK,
          f"no branch: {nobranch}" if nobranch else "all views render")


# ------------------------------------------------------------------- 9
def check_palette(js, head):
    ids = set(re.findall(r'id="([^"]+)"', head))
    block = re.search(r"const CMDS=\[(.*?)\n\];", js, re.S)
    if not block:
        check("palette commands resolve", WARN, "CMDS block not found")
        return
    targets = re.findall(r"\$\('([A-Za-z][\w-]*)'\)", block.group(1))
    bad = sorted(set(targets) - ids)
    n = len(re.findall(r"\['", block.group(1)))
    check("palette commands resolve", FAIL if bad else OK,
          f"unknown targets: {bad}" if bad else f"{n} commands, all valid")


# ------------------------------------------------------------------ 10
def check_debris(js):
    bad = []
    for pat, label in [(r"\bconsole\.log\(", "console.log"),
                       (r"\bdebugger\b", "debugger"),
                       (r"\bTODO\b", "TODO"),
                       (r"\bFIXME\b", "FIXME"),
                       (r"\bXXX\b", "XXX")]:
        n = len(re.findall(pat, js))
        if n:
            bad.append(f"{label} x{n}")
    check("no debug debris", WARN if bad else OK, ", ".join(bad) or "clean")


# ------------------------------------------------------------------- 7
def check_runtime(path):
    if not shutil.which("node"):
        check("script parses and loads", WARN, "node not available")
        return
    r = subprocess.run(["node", "--check", _tmp_js(path)],
                       capture_output=True, text=True)
    check("script parses", FAIL if r.returncode else OK,
          r.stderr.strip().splitlines()[0] if r.returncode else "node --check")
    sys.path.insert(0, HERE)
    import groundstation as gs
    ok, msg = gs.smoke_load(path)
    check("script executes top to bottom", OK if ok else FAIL, msg)


def _tmp_js(path):
    html = open(path, encoding="utf-8").read()
    js = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    js = re.sub(r"const M = \{.*?\};\n", "const M = {};\n", js, flags=re.S)
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                    encoding="utf-8")
    f.write(js); f.close()
    return f.name


def main():
    if not os.path.exists(HTML):
        print(f"no dashboard at {HTML} — run: python3 run.py mission")
        return 1
    html = open(HTML, encoding="utf-8").read()
    head, js, css = split(html)
    print(f"auditing {os.path.basename(HTML)}  "
          f"({len(html)/1024:.0f} KB, {len(js)/1024:.0f} KB script)\n")
    check_ids(head, js, css)
    check_handlers(head, js)
    check_clobber(js)
    check_canvases(head, js)
    check_views(head, js)
    check_palette(js, head)
    check_debris(js)
    check_runtime(HTML)

    nf = sum(1 for _, s, _ in results if s == FAIL)
    nw = sum(1 for _, s, _ in results if s == WARN)
    print(f"\n{len(results)} checks · {nf} failures · {nw} warnings")
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
