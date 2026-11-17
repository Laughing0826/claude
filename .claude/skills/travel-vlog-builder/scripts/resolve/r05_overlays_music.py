# r05_overlays_music - overlay tracks V2-V6 and the music bed on A2. Tool: run_script_unsafe. Run once.
import os, json
B = json.load(open(BUILD, encoding="utf-8"))
mp = project.GetMediaPool()
root = mp.GetRootFolder()
bins = {f.GetName(): f for f in root.GetSubFolderList()}
ver = {f.GetName(): f for f in bins[VERSION].GetSubFolderList()}
ov = {c.GetName(): c for c in ver["Overlays"].GetClipList()}
tl = project.GetCurrentTimeline()
st = tl.GetStartFrame()
lost = sorted({os.path.basename(o["file"]) for o in B["overlays"] if os.path.basename(o["file"]) not in ov})
already = sum(len([x for x in (tl.GetItemListInTrack("video", i) or []) if x.GetType() == "video"]) for i in range(2, tl.GetTrackCount("video") + 1))
if tl.GetName() != TIMELINE:
    result = {"error": "current timeline is not " + TIMELINE}
elif lost:
    result = {"error": "overlays not in the bin; run r01_import again", "lost": lost[:10]}
elif already:
    result = {"error": "overlay tracks already hold clips; do not run r05 twice", "clips": already}
else:
    while tl.GetTrackCount("video") < 6:
        tl.AddTrack("video")
    infos = [{"mediaPoolItem": ov[os.path.basename(o["file"])], "startFrame": 0, "endFrame": o["dur"], "trackIndex": o["track"],
              "recordFrame": st + o["start"], "mediaType": 1} for o in sorted(B["overlays"], key=lambda o: (o["track"], o["start"]))]
    r = mp.AppendToTimeline(infos)
    for i, nm in ((2, "Cinema bars"), (3, "Titles & labels"), (4, "Stickers"), (5, "Motion graphics"), (6, "Captions")):
        tl.SetTrackName("video", i, nm)
    counts = {i: len([x for x in (tl.GetItemListInTrack("video", i) or []) if x.GetType() == "video"]) for i in range(1, 7)}
    want = {}
    for o in B["overlays"]:
        want[o["track"]] = want.get(o["track"], 0) + 1
    music = None
    if MUSIC:
        mus = [c for c in ver["Music"].GetClipList() if c.GetName() == os.path.basename(MUSIC)]
        if mus:
            if tl.GetTrackCount("audio") < 2:
                tl.AddTrack("audio", "stereo")
            mp.AppendToTimeline([{"mediaPoolItem": mus[0], "startFrame": 0, "endFrame": tl.GetEndFrame() - st, "trackIndex": 2,
                                  "recordFrame": st, "mediaType": 2}])
            tl.SetTrackName("audio", 1, "Clip sound")
            tl.SetTrackName("audio", 2, "Music")
            a2 = tl.GetItemListInTrack("audio", 2) or []
            music = {"items": len(a2), "dur_s": a2[0].GetDuration() / float(FPS) if a2 else None}
        else:
            music = {"error": "music bed not in the Music bin"}
    result = {"overlays_added": len(r or []), "expected": len(infos), "tracks": counts, "expected_tracks": want, "music": music,
              "end_s": (tl.GetEndFrame() - st) / float(FPS), "saved": resolve.GetProjectManager().SaveProject()}
