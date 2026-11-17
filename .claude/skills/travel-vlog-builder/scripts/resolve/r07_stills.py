# r07_stills - export frames from the finished timeline so they can be looked at. Tool: run_script_unsafe.
# WANT = [(shot number, frame offset inside the shot), ...]. Afterwards tile the JPEGs with sheet.py and LOOK at the sheet.
import os, json, time
B = json.load(open(BUILD, encoding="utf-8"))
E = B["shots"]
tl = project.GetCurrentTimeline()
st = tl.GetStartFrame()
def tc(fr):
    f = st + fr
    return "%02d:%02d:%02d:%02d" % (f // (3600 * FPS), f // (60 * FPS) % 60, f // FPS % 60, f % FPS)
if not os.path.isdir(STILLS):
    os.makedirs(STILLS)
t0 = time.time()
ok, todo = 0, []
for n, off in WANT:
    if time.time() - t0 > 45:
        todo.append((n, off))
        continue
    s = E[n]
    tl.SetCurrentTimecode(tc(s["start"] + min(off, s["frames"] - 1)))
    time.sleep(0.35)        # give the viewer time to draw the frame, or the export is the previous frame
    if project.ExportCurrentFrameAsStill(os.path.join(STILLS, "%03d_%s.jpg" % (n, s["ref"]))):
        ok += 1
result = {"exported": ok, "of": len(WANT), "pending": todo, "folder": STILLS}
