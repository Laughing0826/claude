# r02_timeline - create the timeline and lay every shot on V1 at its exact frame. Tool: run_script_unsafe.
# Never touches other timelines. If TIMELINE already exists it stops unless REPLACE is True.
import os, json
B = json.load(open(BUILD, encoding="utf-8"))
E = B["shots"]
mp = project.GetMediaPool()
root = mp.GetRootFolder()
bins = {f.GetName(): f for f in root.GetSubFolderList()}
ver = {f.GetName(): f for f in bins[VERSION].GetSubFolderList()}
clips = {c.GetName(): c for c in bins["Clips"].GetClipList()}
shots = {c.GetName(): c for c in ver["Shots"].GetClipList()}
old = [project.GetTimelineByIndex(i + 1) for i in range(project.GetTimelineCount())]
old = [t for t in old if t.GetName() == TIMELINE]
if old and not REPLACE:
    result = {"error": "timeline already exists; rebuild it only with REPLACE = True", "timeline": TIMELINE}
else:
    if old:
        mp.DeleteTimelines(old)
    mp.SetCurrentFolder(bins[VERSION])
    tl = mp.CreateEmptyTimeline(TIMELINE)
    project.SetCurrentTimeline(tl)
    st = tl.GetStartFrame()
    infos, lost = [], []
    for s in E:
        n = s["frames"]
        if s["kind"] == "S":
            # straight from the source clip: frame numbers are SOURCE frames (a 50 fps clip in a 25 fps timeline uses 2 per frame)
            r = max(1, int(round((s.get("srcfps") or FPS) / FPS)))
            sf = int(round(s["i"] * FPS * r))
            sf += sf % r
            item = clips.get(os.path.basename(s["file"]))
            d = {"mediaPoolItem": item, "startFrame": sf, "endFrame": sf + r * n}
            if s.get("mute"):
                d["mediaType"] = 1
        else:
            item = shots.get(os.path.basename(s["media"]))
            d = {"mediaPoolItem": item, "startFrame": s["head"], "endFrame": s["head"] + n}
            if s["kind"] in ("A", "P", "M", "C") or s.get("mute"):
                d["mediaType"] = 1          # video only: photos and slides are silent
        if item is None:
            lost.append((s["n"], s["ref"]))
            continue
        d["trackIndex"] = 1
        d["recordFrame"] = st + s["start"]
        infos.append(d)
    if lost:
        result = {"error": "media not in the bins; run r01_import again", "lost": lost[:10]}
    else:
        res = mp.AppendToTimeline(infos)
        v = sorted(tl.GetItemListInTrack("video", 1), key=lambda x: x.GetStart())
        bad = [(s["n"], s["ref"], it.GetStart() - st, s["start"], it.GetDuration(), s["frames"])
               for s, it in zip(E, v) if it.GetStart() - st != s["start"] or it.GetDuration() != s["frames"]]
        nl = 0
        if LUT:
            try:
                project.RefreshLUTList()     # so a LUT file copied into Resolve's LUT folder just now is known
            except Exception:
                pass
            nl = sum(1 for s, it in zip(E, v) if s["kind"] == "S" and it.GetNodeGraph() and it.GetNodeGraph().SetLUT(1, LUT))
        tl.SetTrackName("video", 1, "Main")
        result = {"timeline": TIMELINE, "appended": len(res or []), "expected": len(E), "v1": len(v),
                  "a1": len(tl.GetItemListInTrack("audio", 1) or []), "end_s": (tl.GetEndFrame() - st) / float(FPS),
                  "expected_end_s": B["meta"]["frames"] / float(FPS), "nbad": len(bad), "bad": bad[:10], "luts": nl, "expected_luts": sum(1 for s in E if s["kind"] == "S") if LUT else 0,
                  "saved": resolve.GetProjectManager().SaveProject()}
