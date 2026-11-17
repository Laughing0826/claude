# r06_subtitles - put the .srt files on subtitle tracks as editable text. Tool: run_script_unsafe. Run once.
# The styled captions on V6 already show the same words, so these tracks are switched OFF (ENABLE_SUBS False) to avoid
# doubled text. Resolve drops an appended .srt with its first line at the record frame, not at its own time, so the
# items are moved until the first line starts at the first caption's frame; the last line's end is then compared.
import os, json
B = json.load(open(BUILD, encoding="utf-8"))
mp = project.GetMediaPool()
root = mp.GetRootFolder()
bins = {f.GetName(): f for f in root.GetSubFolderList()}
srt = {c.GetName(): c for c in bins["Subtitles"].GetClipList()}
tl = project.GetCurrentTimeline()
st = tl.GetStartFrame()
files = B.get("meta", {}).get("srt") or {}
order = [k for k in ("BILINGUAL", "EN") if k in files] + [k for k in files if k not in ("BILINGUAL", "EN")]
names = [os.path.splitext(os.path.basename(files[k]))[0] for k in order]
first = B["subs"][0][0] if B["subs"] else 0
log = {"first": first, "expect_last_end_s": (max(x[1] for x in B["subs"]) / float(FPS)) if B["subs"] else None}
if tl.GetName() != TIMELINE:
    result = {"error": "current timeline is not " + TIMELINE}
elif [n for n in names if n not in srt]:
    result = {"error": "srt not in the Subtitles bin; run r01_import again", "missing": [n for n in names if n not in srt]}
elif tl.GetTrackCount("subtitle") and any(tl.GetItemListInTrack("subtitle", t) for t in range(1, tl.GetTrackCount("subtitle") + 1)):
    result = {"error": "subtitle tracks already hold items; do not run r06 twice"}
else:
    for k, nm in enumerate(names, 1):
        while tl.GetTrackCount("subtitle") < k:
            tl.AddTrack("subtitle")
        before = {t: len(tl.GetItemListInTrack("subtitle", t) or []) for t in range(1, tl.GetTrackCount("subtitle") + 1)}
        mp.AppendToTimeline([{"mediaPoolItem": srt[nm], "trackIndex": k, "recordFrame": st}])
        for t in range(1, tl.GetTrackCount("subtitle") + 1):
            items = sorted(tl.GetItemListInTrack("subtitle", t) or [], key=lambda x: x.GetStart())
            new = items[before.get(t, 0):]
            if new and (t != k or new[0].GetStart() != st + first):
                log["move_%d" % k] = tl.MoveItems(new, {"trackIndex": k, "startFrame": st + first})
    for k, key in enumerate(order, 1):
        it = tl.GetItemListInTrack("subtitle", k) or []
        log["t%d" % k] = [key, len(it), (min(x.GetStart() for x in it) - st) if it else None,
                          round((max(x.GetEnd() for x in it) - st) / float(FPS), 2) if it else None]
        tl.SetTrackName("subtitle", k, "Bilingual" if key == "BILINGUAL" else ("English" if key == "EN" else key))
        log["enabled_%d" % k] = ENABLE_SUBS if tl.SetTrackEnable("subtitle", k, ENABLE_SUBS) else "failed"
    log["expected_items"] = len(B["subs"])
    log["saved"] = resolve.GetProjectManager().SaveProject()
    result = log
