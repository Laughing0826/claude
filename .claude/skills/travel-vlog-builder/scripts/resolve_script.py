"""resolve_script - print a ready-to-run DaVinci Resolve script for one build step.

usage:  python -I -X utf8 resolve_script.py [--project <folder>] <step> [--replace] [--only 12,15,20] [--enable-subs]
                                             [--want 0:200,1:110,...] [--test]
        python -I -X utf8 resolve_script.py list

Steps (run in this order; each prints a `result` dict that says what to do next):
  r00_check          what is open in Resolve (read-only)                          tool: run_script
  r01_import         bins + import shots, overlays, music bed, subtitles           tool: run_script_unsafe  (repeat until remaining = 0)
  r02_timeline       create the timeline, lay all shots on V1, apply the LUT       tool: run_script_unsafe  (--replace to rebuild)
  r03_transitions    add the transitions                                           tool: run_script_unsafe  (once)
  r04_stabilize      stabilise real video clips                                    tool: run_script_unsafe  (repeat with --only <pending>)
  r05_overlays_music overlay tracks V2-V6 and music on A2                          tool: run_script_unsafe  (once)
  r06_subtitles      .srt files as text tracks, switched off                       tool: run_script_unsafe  (once; --enable-subs to leave on)
  r07_stills         export check frames from the timeline                         tool: run_script_unsafe
  r08_summary        final counts for the report, and save                         tool: run_script

The printed text is: a header of constants taken from project.json and the build file, then the step's template from
the resolve/ folder. Send the WHOLE printed text, unchanged, as the `script` argument of the Resolve MCP tool named
above. Everything is plain ASCII on purpose: non-ASCII characters in a script sent to Resolve can fail, so any path or
name with other characters is written with \\u escapes. Inside Resolve scripts never type non-ASCII literals; use chr().
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vk

STEPS = ["r00_check", "r01_import", "r02_timeline", "r03_transitions", "r04_stabilize", "r05_overlays_music",
         "r06_subtitles", "r07_stills", "r08_summary"]


def auto_want(B):
    """Representative frames: first shot of each kind and of each overlay type, plus the last shot."""
    E = B["shots"]
    by_shot = {}
    for o in B["overlays"]:
        by_shot.setdefault(o.get("shot"), []).append(o)
    picks, seen = [], set()

    def take(s, tag):
        if tag in seen or len(picks) >= 18:
            return
        seen.add(tag)
        if s["n"] in [p[0] for p in picks]:
            return
        ovs = by_shot.get(s["n"], [])
        # a frame where the overlays have finished animating in but have not started to fade
        off = max([min(o["start"] - s["start"] + min(45, o["dur"] // 2), s["frames"] - 8) for o in ovs] + [min(s["frames"] // 2, 60)])
        picks.append((s["n"], max(0, off)))
    for s in E:
        take(s, "kind:" + s["kind"])
        for k in ("title", "card", "loc", "sp", "lower", "stk", "badge", "sub", "subs"):
            if s.get(k):
                take(s, k)
        if s.get("mg"):
            take(s, "mg:" + s["mg"])
    if E:
        take(E[-1], "last")
    return sorted(picks)


def main():
    args = sys.argv[1:]
    cfg = vk.load(args)
    if not args or args[0] == "list":
        print("\n".join(STEPS))
        return 0
    step = args[0]
    if step not in STEPS:
        sys.exit(f"unknown step {step}; one of {STEPS}")
    build = cfg["build"].replace(".json", ".test.json") if "--test" in args else cfg["build"]
    if not os.path.exists(build):
        sys.exit(f"{build} not found. Run prep.py all (and validate.py) first.")
    with open(build, encoding="utf-8") as f:
        B = json.load(f)
    music = None
    plan = cfg.p("music_plan.json")
    if os.path.exists(plan):
        with open(plan, encoding="utf-8") as f:
            out = json.load(f).get("out")
        if out:
            music = out if os.path.isabs(out) else cfg.p(out)
    if music and not os.path.exists(music):
        print(f"# NOTE: music bed {music} does not exist yet; run mix.py first or the timeline will have no music", file=sys.stderr)
        music = None
    lut = cfg.get("resolve_lut") or cfg.get("lut")
    if lut and not os.path.isabs(lut):
        lut = cfg.p(lut)
    only = [int(x) for x in args[args.index("--only") + 1].split(",")] if "--only" in args else None
    want = ([tuple(int(v) for v in x.split(":")) for x in args[args.index("--want") + 1].split(",")] if "--want" in args else auto_want(B))
    head = {
        "BUILD": os.path.abspath(build),
        "VERSION": cfg["version"],
        "TIMELINE": f"{cfg['name']} {cfg['version']}",
        "FPS": cfg["FPS"],
        "LUT": lut,
        "MUSIC": music,
        "REPLACE": "--replace" in args,
        "ONLY": only,
        "ENABLE_SUBS": "--enable-subs" in args,
        "STILLS": os.path.join(cfg["work"], "stills_" + cfg["version"]),
        "WANT": want,
    }
    with open(os.path.join(vk.HERE, "resolve", step + ".py"), encoding="utf-8") as f:
        body = f.read()
    lines = [f"{k} = {ascii(v)}" for k, v in head.items() if k in body]
    text = "\n".join(lines) + "\n" + body
    assert all(ord(c) < 128 for c in text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
