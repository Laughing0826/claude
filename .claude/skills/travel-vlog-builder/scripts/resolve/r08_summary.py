# r08_summary - final state of the timeline, for the report. Tool: run_script (no imports needed). Read-only apart from Save.
tl = project.GetCurrentTimeline()
st = tl.GetStartFrame()
tl.SetCurrentTimecode(tl.GetStartTimecode())
v1 = tl.GetItemListInTrack("video", 1) or []
nv, na, ns = tl.GetTrackCount("video"), tl.GetTrackCount("audio"), tl.GetTrackCount("subtitle")
result = {"timeline": tl.GetName(), "dur_s": (tl.GetEndFrame() - st) / float(FPS),
          "shots": sum(1 for i in v1 if i.GetType() == "video"), "transitions": sum(1 for i in v1 if i.GetType() == "transition"),
          "video_tracks": {i: len([x for x in (tl.GetItemListInTrack("video", i) or []) if x.GetType() == "video"]) for i in range(2, nv + 1)},
          "audio_tracks": {i: len(tl.GetItemListInTrack("audio", i) or []) for i in range(1, na + 1)},
          "subtitle_tracks": {i: len(tl.GetItemListInTrack("subtitle", i) or []) for i in range(1, ns + 1)},
          "timelines": [project.GetTimelineByIndex(i + 1).GetName() for i in range(project.GetTimelineCount())],
          "saved": resolve.GetProjectManager().SaveProject()}
