# r04_stabilize - Resolve's stabilizer on every real video clip (not photos, slides or the rewind intro).
# Tool: run_script_unsafe. Stops after 40 s and returns "pending" shot numbers: run again with ONLY = [those numbers]
# until pending is empty. Each clip took 0.4-0.7 s in the original project; long clips take longer.
import json, time
B = json.load(open(BUILD, encoding="utf-8"))
E = B["shots"]
tl = project.GetCurrentTimeline()
v = sorted([i for i in tl.GetItemListInTrack("video", 1) if i.GetType() == "video"], key=lambda x: x.GetStart())
if tl.GetName() != TIMELINE or len(v) != len(E):
    result = {"error": "wrong timeline or V1 does not match the edit list", "timeline": tl.GetName(), "v1": len(v), "shots": len(E)}
else:
    t0 = time.time()
    done, fail, pending = 0, [], []
    for s, it in zip(E, v):
        if s["kind"] not in ("S", "V", "SV", "D"):
            continue
        if ONLY is not None and s["n"] not in ONLY:
            continue
        if time.time() - t0 > 40:
            pending.append(s["n"])
            continue
        if it.Stabilize():
            done += 1
        else:
            fail.append((s["n"], s["ref"]))
    result = {"stabilized": done, "fail": fail, "pending": pending, "secs": round(time.time() - t0, 1),
              "saved": resolve.GetProjectManager().SaveProject()}
