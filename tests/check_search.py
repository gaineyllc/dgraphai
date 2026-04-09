from src.dgraphai.api.inventory_search import resolve_query
queries = [
    ("hdr video",           "video-hdr"),
    ("1080p",               "video-1080p"),
    ("movies",              "video-long"),
    ("mkv files",           "video"),
    ("flac files",          "audio-lossless"),
    ("photos with faces",   "images-with-faces"),
    ("cr2 files",           "images-raw"),
    ("heic images",         "images-raw"),
    ("files with action items", "ai-action-items"),
]
for q, expected in queries:
    r = resolve_query(q)
    got = r.get("matched_category") or "SYNTH"
    kw  = r.get("matched_keyword", "")
    ok  = "OK" if got == expected else "FAIL"
    print(f"[{ok}] {q!r:35s} -> {got:25s} expected={expected} kw={kw!r}")
