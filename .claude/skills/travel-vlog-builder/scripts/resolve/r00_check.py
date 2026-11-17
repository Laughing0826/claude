# r00_check - what is open in Resolve right now. Read-only. Tool: run_script (no imports needed).
pm = resolve.GetProjectManager()
project = pm.GetCurrentProject()
mp = project.GetMediaPool()
root = mp.GetRootFolder()
tls = [project.GetTimelineByIndex(i + 1).GetName() for i in range(project.GetTimelineCount())]
cur = project.GetCurrentTimeline()
result = {"resolve": resolve.GetVersionString(), "project": project.GetName(),
          "fps": project.GetSetting("timelineFrameRate"),
          "size": [project.GetSetting("timelineResolutionWidth"), project.GetSetting("timelineResolutionHeight")],
          "timelines": tls, "current": cur.GetName() if cur else None, "target_exists": TIMELINE in tls,
          "bins": [f.GetName() for f in root.GetSubFolderList()]}
