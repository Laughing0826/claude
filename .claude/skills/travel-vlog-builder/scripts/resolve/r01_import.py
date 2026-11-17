# r01_import - bins and media import. Tool: run_script_unsafe. Re-run until "remaining" is 0 for every group.
# Imports in chunks and stops after 40 s so the call never hits the 60 s tool limit.
import os, json, time
t0 = time.time()
B = json.load(open(BUILD, encoding="utf-8"))
mp = project.GetMediaPool()
root = mp.GetRootFolder()
def sub(parent, name):
    for f in parent.GetSubFolderList():
        if f.GetName() == name:
            return f
    return mp.AddSubFolder(parent, name)
ver = sub(root, VERSION)
bins = {"Shots": sub(ver, "Shots"), "Overlays": sub(ver, "Overlays"), "Music": sub(ver, "Music"),
        "Clips": sub(root, "Clips"), "Subtitles": sub(root, "Subtitles")}
want = {"Shots": sorted({s["media"] for s in B["shots"] if s.get("media")}),
        "Overlays": sorted({o["file"] for o in B["overlays"]}),
        "Clips": sorted({s["file"] for s in B["shots"] if s["kind"] == "S"}),
        "Music": [MUSIC] if MUSIC else [],
        "Subtitles": sorted((B.get("meta", {}).get("srt") or {}).values())}
log = {}
for name in ("Clips", "Shots", "Music", "Subtitles", "Overlays"):
    b = bins[name]
    have = {c.GetName() for c in b.GetClipList()}
    stem = name == "Subtitles"      # Resolve lists an imported .srt without its extension
    todo = [f for f in want[name] if (os.path.splitext(os.path.basename(f))[0] if stem else os.path.basename(f)) not in have]
    missing = [f for f in todo if not os.path.exists(f)]
    todo = [f for f in todo if os.path.exists(f)]
    n = 0
    mp.SetCurrentFolder(b)
    for k in range(0, len(todo), 40):
        if time.time() - t0 > 40:
            break
        n += len(mp.ImportMedia(todo[k:k + 40]) or [])
    log[name] = {"in_bin": len(b.GetClipList()), "imported": n, "remaining": len(todo) - n, "missing_files": missing[:5]}
log["secs"] = round(time.time() - t0, 1)
result = log
