# r03_transitions - add the transition named in each shot's "tr" at the START of that shot. Tool: run_script_unsafe.
# Run once, right after r02 (running it twice would stack transitions). Tries centre alignment at the preferred
# length, then shorter, then one-sided, because a clip without enough spare frames refuses a centred transition.
import json
B = json.load(open(BUILD, encoding="utf-8"))
E = B["shots"]
tl = project.GetCurrentTimeline()
if tl.GetName() != TIMELINE:
    result = {"error": "current timeline is not " + TIMELINE}
else:
    v = sorted([i for i in tl.GetItemListInTrack("video", 1) if i.GetType() == "video"], key=lambda x: x.GetStart())
    had = sum(1 for i in tl.GetItemListInTrack("video", 1) if i.GetType() == "transition")
    FUS = {"Brightness Flash", "Zoom In", "Slide Left", "Slide Up", "Slide Down", "Glitch", "Film Strip", "Spin", "Camera Shake", "Foreground Wipe"}
    DUR = {"Cross Dissolve": 12, "Additive Dissolve": 16, "Dip To Color Dissolve": 20, "Brightness Flash": 8, "Glitch": 10}
    ok, fail = {}, []
    if had:
        result = {"error": "this timeline already has transitions; do not run r03 twice", "transitions": had}
    elif len(v) != len(E):
        result = {"error": "V1 item count differs from the edit list", "v1": len(v), "shots": len(E)}
    else:
        for k, (s, it) in enumerate(zip(E, v)):
            tr = s.get("tr")
            if not tr or k == 0:
                continue
            cat = "fusion" if tr in FUS else "simple"
            d = DUR.get(tr, 14)
            t = None
            for al, dd in (("center", d), ("center", 10), ("right", 10), ("left", 10)):
                t = it.AddTransition({"type": tr, "category": cat, "position": "start", "alignment": al, "duration": dd})
                if t:
                    ok[tr] = ok.get(tr, 0) + 1
                    break
            if not t:
                fail.append((s["n"], s["ref"], tr))
        result = {"transitions": ok, "total": sum(ok.values()), "expected": sum(1 for k, s in enumerate(E) if s.get("tr") and k),
                  "fail": fail, "saved": resolve.GetProjectManager().SaveProject()}
