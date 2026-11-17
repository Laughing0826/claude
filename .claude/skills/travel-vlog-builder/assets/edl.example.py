# Example edit list (abridged from a real 8-minute safari vlog). Copy to <project>/edl_<version>.py and rewrite.
# Run:  python -I -X utf8 <skill>/scripts/build_edl.py --project <project>
# No imports needed. One line = one shot, in screen order. See references/edl.md for every option.

# ---------------- INTRO: VHS rewind through the trip, newest first, ending on the first clip of the story ----------------
day(0, None)                                   # day 0 = not date-checked
R("rewind", 15.4, clips=[("V106", 8, "24 FEB 2026", "DAY 9"), ("V94", 3, "23 FEB 2026", "DAY 8"), ("C0044", 2, "22 FEB 2026", "DAY 7"),
                         ("C0033", 2, "21 FEB 2026", "DAY 6"), ("C0025", 1, "20 FEB 2026", "DAY 5"), ("C0016", 11, "19 FEB 2026", "DAY 4"),
                         ("V31", 3, "18 FEB 2026", "DAY 3"), ("C0011", 1, "17 FEB 2026", "DAY 2"), ("C0003", 1, "16 FEB 2026", "DAY 1"),
                         ("V1", 2, "15 FEB 2026", "HONG KONG")])
P("P335", 7.0, "in", tr="Brightness Flash", mg="vehicle",
  title=("ESCARPMENT & KRUGER", "南非 · 高地與克魯格之旅", "FRIENDS ON SAFARI · 16–24 FEB 2026", "South Africa 2026",
         "From the misty Escarpment to the wild heart of Kruger"))

# ---------------- GETTING THERE ----------------
day(0.5, "2026-02-15")
V("V1", 0.0, 9.6, tr="Cross Dissolve", loc=("HONG KONG AIRPORT", "香港國際機場"),          # selfie to camera: timed speech captions
  subs=[(0.2, 3.3, "OK — we're at the airport already.", "好，這麼快我們已經到機場了。"),
        (3.4, 6.6, "I'm pretty nervous right now…", "現在很緊張……"),
        (7.0, 9.4, "…it's my first time flying Premium Economy!", "因為人生第一次搭 Premium Economy！")])
V("V5", 1, 4.0, mute=True, tr="Slide Left", stk="CX 80th Anniversary livery 國泰80週年塗裝",
  sub=("Our plane wears the airline's 80th-anniversary retro livery!", "我們的航班：80週年紀念復古塗裝！", 1))
day(0.6, "2026-02-16")
P("P59", 2.2, "in", dark=1, tr="Cross Dissolve", mg="flight", sub=("Sunrise somewhere over Africa.", "非洲上空的日出。", 1))
V("V15", 4, 3.0, mute=True, loc=("JOHANNESBURG", "約翰尼斯堡"), sub=("13 hours later… Johannesburg!", "十三小時後……約翰尼斯堡！", 2))
V("V17", 172, 3.0, mute=True)
M(6.5, tr="Zoom In", mg="route", sub=("Our route: Dullstroom → Blyde River Canyon → Kruger. About 1,200 km.",
                                      "路線：杜爾斯特魯姆 → 布萊德河峽谷 → 克魯格，全程約1,200公里。", 1))

# ---------------- DAY 1 ----------------
day(1, "2026-02-16")
V("V12", 1, 3.6, tr="Push", card=("DAY 1 · 16 FEB · RIETVLEI — DULLSTROOM", "第一天 · 里特夫萊 — 杜爾斯特魯姆"),
  sub=("Straight from the airport to Rietvlei Nature Reserve.", "一下機就直奔里特夫萊自然保護區。", 1))
S("C0003", 1, 3.4, sp=("Common Ostrich", "鴕鳥"), badge="ostrich", sub=("First big bird of the trip: ostriches!", "此行第一種大鳥：鴕鳥！", 1))
A("D1-08", 2.4, "left", tr="Cross Dissolve", sub=("Zebra herds on the highveld grassland.", "高原草地上的斑馬群。", 3))
S("C0004", 2, 3.0, stk="Rhino!! 犀牛！")
A("D1-13", 2.4, "in", tr="Cross Dissolve", sp=("Plains Zebra", "平原斑馬"), badge="zebra")
A("D1-11", 2.2, "out", tr="Cross Dissolve")                                              # uncertain species: no label at all
C("slide_d1", ["D1-24", "D1-39", "D1-41"], ("Rietvlei birds", "里特夫萊的鳥"), ("16 FEB", "Day 1"),
  ("Korhaan, thick-knee and barbet — all before lunch.", "北黑鴇、斑石鴴、黑領擬啄木鳥——午餐前全部到齊。"), bg=1, tr="Push")
P("P97", 2.4, "in", tr="Cross Dissolve", loc=("ROSE COTTAGE · DULLSTROOM", "杜爾斯特魯姆"),
  sub=("Dullstroom, 2,000 m up — dinner by the fire.", "海拔二千米的杜爾斯特魯姆，壁爐旁的晚餐。", 2))
P("P117", 2.2, "out", tr="Film Strip")

# ---------------- DAY 4: a documentary sequence (wide establishing shot, slow-motion close-up, third angle) ----------------
day(4, "2026-02-19")
P("P361", 2.4, "in", dark=1, tr="Dip To Color Dissolve", card=("DAY 4 · 19 FEB · ORPEN GATE — SATARA", "第四天 · 奧本門 — 薩塔拉"))
P("P402", 2.3, "in", tr="Push", loc=("ORPEN GATE · KRUGER", "奧本門 · 克魯格"), stk="Our ride 我們的座駕",
  sub=("…then into Kruger National Park!", "……然後進入克魯格國家公園！", 1))
D("C0016", 4, 5.0, speed=1, z=(1.0, 1.06), doc="giraffe", tr="Dip To Color Dissolve", badge="giraffe",
  lower=("GIRAFFE", "Giraffa camelopardalis", "長頸鹿"),
  sub=("On the road from Orpen, two giraffes browse the treetops.", "從奧本門進來的路上，兩隻長頸鹿在樹梢覓食。", 1))
D("C0016", 22, 4.4, speed=0.5, z=(1.42, 1.5), c=(0.5, 0.4), doc="giraffe", tr="Cross Dissolve",
  sub=("A tongue almost half a metre long strips leaves from between the thorns.", "近半米長的舌頭，從尖刺之間捲走嫩葉。", 1))
D("C0017", 2, 4.0, speed=0.5, z=(1.12, 1.2), doc="giraffe", tr="Cross Dissolve")
A("D4-18", 2.3, "out", tr="Dip To Color Dissolve")                                       # dip out of the sequence
V("V64", 0.6, 4.2, tr="Slide Up", stk="YESSS!")
P("P469", 2.4, "in", dark=2, tr="Dip To Color Dissolve")                                 # sunset closes the chapter

# ---------------- OUTRO ----------------
day(8, "2026-02-23")
M(5.5, tr="Zoom In", mg="route", sub=("Eight nights, 1,202 km, countless memories.", "八晚、1,202公里、無數回憶。", 1))
day(9, "2026-02-24")
V("V101", 0.5, 3.6, tr="Slide Up", loc=("DAY 9 · 24 FEB", "回家"), sub=("Time to fly home.", "是時候回家了。", 2))
V("V106", 5, 3.4, mute=True)
day(0, None)
C("slide_end", ["P789", "P609", "P180", "P332"], ("Friends on safari", "我們"), ("16–24 FEB", "2026"),
  ("Thank you, South Africa. See you again!", "謝謝你，南非。我們會再見！"), d=6.0, bg=1, tr="Heart")
P("P541", 5.0, "in", dark=1, tr="Dip To Color Dissolve", mg="parade",
  title=("THANK YOU, SOUTH AFRICA", "謝謝你，南非 — 完", "ESCARPMENT & KRUGER 2026", "The End", "Nine days · 1,202 km · countless memories"))
