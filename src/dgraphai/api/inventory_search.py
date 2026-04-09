"""
Natural language category search for the Data Inventory.

Maps plain language to the correct data type / file format category.
Returns a category to navigate to, or suggestions if nothing matches.
No Cypher synthesis — that belongs in the Graph/Query surface.
"""
from __future__ import annotations
import re
from typing import Any

from fastapi import APIRouter, Depends, Query

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.inventory.taxonomy import ALL_CATEGORIES, get_category

router = APIRouter(prefix="/api/inventory/search", tags=["inventory"])


# ── Keyword → category map ────────────────────────────────────────────────────
# Format: (list_of_phrases, category_id)
# Longest phrase wins when multiple match. Put more specific phrases first.

KEYWORD_MAP: list[tuple[list[str], str]] = [

    # ── Video formats ─────────────────────────────────────────────────────────
    (["mkv files", "mkv video", "matroska"],                          "video-mkv"),
    (["mp4 files", "mp4 video", "mpeg-4 video", "m4v"],              "video-mp4"),
    (["transport stream", "ts files", "m2ts", "blu-ray video",
      "broadcast video"],                                             "video-ts"),
    (["mov files", "quicktime", "apple video"],                       "video-mov"),
    (["avi files", "avi video"],                                      "video-avi"),
    (["wmv files", "windows media video"],                            "video-wmv"),
    (["webm files", "flv files", "web video"],                        "video-webm"),
    (["mkv", "mp4", "avi", "mov", "ts", "wmv", "webm", "flv",
      "video files", "video", "videos", "movies", "films",
      "recordings", "clips"],                                         "video"),

    # ── Audio formats ─────────────────────────────────────────────────────────
    (["flac files", "flac audio", "flac music"],                      "audio-flac"),
    (["mp3 files", "mp3 music", "mp3 audio"],                         "audio-mp3"),
    (["aac files", "m4a files", "aac audio", "apple music files"],    "audio-aac"),
    (["wav files", "wav audio", "wave files", "pcm audio"],           "audio-wav"),
    (["dsd files", "sacd", "dsf files", "dff files", "hi-res dsd"],   "audio-dsd"),
    (["ogg files", "opus files", "vorbis"],                           "audio-opus"),
    (["flac", "mp3", "aac", "m4a", "wav", "ogg", "opus", "dsd",
      "audio files", "audio", "music", "songs", "tracks",
      "recordings"],                                                  "audio"),

    # ── Image formats ─────────────────────────────────────────────────────────
    (["jpeg files", "jpg files", "jpeg photos", "jpg photos"],        "images-jpeg"),
    (["png files", "png images", "portable network graphics"],        "images-png"),
    (["raw photos", "raw images", "camera raw", "cr2 files",
      "nef files", "arw files", "dng files", "raf files",
      "heic files", "heic images", "heif files",
      "cr2", "nef", "arw", "dng", "heic", "heif"],                   "images-raw"),
    (["tiff files", "tif files", "bmp files", "bitmap"],              "images-tiff"),
    (["webp files", "gif files", "animated gif", "avif"],             "images-webp"),
    (["jpeg", "jpg", "png", "tiff", "gif", "webp",
      "photos", "pictures", "images", "photos files"],               "images"),

    # ── Document formats ──────────────────────────────────────────────────────
    (["pdf files", "pdf documents", "pdfs", ".pdf"],                  "docs-pdf"),
    (["word files", "word documents", "docx files", "doc files",
      "odt files", "rtf files"],                                      "docs-word"),
    (["excel files", "spreadsheets", "xlsx files", "xls files",
      "csv files", "csv data", "tsv files", "ods files"],             "docs-excel"),
    (["powerpoint files", "presentations", "pptx files", "ppt files",
      "keynote files", "slides"],                                     "docs-powerpoint"),
    (["text files", "txt files", "markdown files", "readme files",
      "log files", "plain text"],                                     "docs-text"),
    (["json files", "xml files", "yaml files", "toml files",
      "ini files", "config data files"],                              "docs-data"),
    (["pdf", "docx", "xlsx", "pptx", "txt", "csv", "json", "xml",
      "documents", "docs", "office files"],                           "documents"),

    # ── Email formats ─────────────────────────────────────────────────────────
    (["eml files", "mbox files", "email files"],                      "emails-eml"),
    (["msg files", "outlook files", "outlook emails"],                "emails-msg"),
    (["eml", "msg", "mbox", "emails", "email", "messages"],           "emails"),

    # ── Source code languages ─────────────────────────────────────────────────
    (["python files", "python code", ".py files", "py files"],        "code-python"),
    (["javascript files", "typescript files", "js files", "ts files",
      "jsx files", "tsx files", "node files"],                        "code-javascript"),
    (["go files", "golang files", ".go files"],                       "code-go"),
    (["rust files", "rust code", ".rs files"],                        "code-rust"),
    (["java files", "kotlin files", "scala files", ".java"],          "code-java"),
    (["c# files", "csharp files", "c++ files", "cpp files",
      "c files", ".cs files", ".cpp files"],                          "code-csharp"),
    (["shell scripts", "bash scripts", "powershell scripts",
      "batch files", ".sh files", ".ps1 files", ".bat files"],        "code-shell"),
    (["config files", "configuration files", "env files",
      ".env files", "ini files", "properties files"],                 "code-config"),
    (["sql files", "database scripts", "graphql files",
      ".sql files"],                                                   "code-sql"),
    (["python", "javascript", "typescript", "go", "rust", "java",
      "kotlin", "csharp", "bash", "shell", "scripts",
      "source code", "code files", "code"],                           "code"),

    # ── Executables ───────────────────────────────────────────────────────────
    (["exe files", "dll files", "windows executables",
      "windows binaries", "pe files", "win32"],                       "exe-pe"),
    (["elf files", "linux binaries", "linux executables",
      "shared objects", ".so files"],                                 "exe-elf"),
    (["macho files", "macos binaries", "macos executables",
      "dylib files", "mach-o"],                                       "exe-macho"),
    (["msi files", "installers", "pkg files", "deb files",
      "rpm files", "dmg files", "setup files"],                       "exe-msi"),
    (["exe", "dll", "bin", "binary", "binaries",
      "executables", "applications"],                                 "executables"),

    # ── Archives ──────────────────────────────────────────────────────────────
    (["zip files", "jar files", "apk files"],                         "archives-zip"),
    (["7z files", "7-zip files", "rar files"],                        "archives-7z"),
    (["tar files", "tar.gz files", "tgz files", "gzip files",
      "bz2 files", "xz files", "tarball"],                            "archives-tar"),
    (["iso files", "disc images", "disk images", "img files"],        "archives-iso"),
    (["zip", "rar", "7z", "tar", "gz", "iso",
      "archives", "compressed files"],                                "archives"),

    # ── Certificates & keys ───────────────────────────────────────────────────
    (["pem files", "crt files", "cer files", "ssl certificates",
      "tls certificates", "x509 certificates"],                       "certs-pem"),
    (["p12 files", "pfx files", "pkcs12 files",
      "certificate bundles"],                                         "certs-pkcs12"),
    (["key files", "private key files", "der files",
      "private keys"],                                                "certs-keys"),
    (["certificates", "certs", "ssl", "tls", "x509",
      "pem", "key files"],                                            "certificates"),

    # ── 3D / CAD ──────────────────────────────────────────────────────────────
    (["stl files", "obj files", "3d mesh files"],                     "3d-stl"),
    (["dwg files", "dxf files", "step files", "cad files",
      "engineering drawings"],                                        "3d-cad"),
    (["blend files", "blender files", "fbx files", "gltf files",
      "3d scene files"],                                              "3d-blend"),
    (["3d models", "cad files", "3d files"],                          "3d-models"),

    # ── Calendar & contacts ───────────────────────────────────────────────────
    (["ics files", "calendar files", "icalendar"],                    "calendar-ics"),
    (["vcf files", "vcard files", "contact files"],                   "contacts-vcf"),
    (["calendar", "contacts", "address book"],                        "calendar-contacts"),

    # ── People / identity ─────────────────────────────────────────────────────
    (["identified people", "known people", "named people",
      "recognized faces", "identified faces"],                        "people-identified"),
    (["unknown faces", "unidentified people", "unrecognized faces",
      "face clusters"],                                               "people-unknown"),
    (["people", "persons", "faces", "individuals"],                   "people"),

    # ── Software inventory ────────────────────────────────────────────────────
    (["installed apps", "installed software", "applications",
      "software inventory"],                                          "applications"),

    # ── Storage ───────────────────────────────────────────────────────────────
    (["duplicate files", "duplicates", "identical files",
      "same files"],                                                  "duplicates"),
    (["folders", "directories", "directory structure",
      "folder structure"],                                            "directories"),
]


# ── Resolution ────────────────────────────────────────────────────────────────

def resolve_query(query: str) -> dict[str, Any]:
    """Resolve natural language to best matching inventory category."""
    q = query.strip().lower()

    # 1. Exact category name match
    for cat in ALL_CATEGORIES:
        if cat.name.lower() == q:
            return _hit(cat, 1.0, q)

    # 2. Keyword scoring — longest matching phrase wins
    best: tuple[float, Any, str] | None = None
    for phrases, cat_id in KEYWORD_MAP:
        cat = get_category(cat_id)
        if not cat:
            continue
        for phrase in phrases:
            if phrase not in q:
                continue
            n_words = len(phrase.split())
            score   = len(phrase) + n_words * 4
            if best is None or score > best[0]:
                best = (score, cat, phrase)

    if best:
        _, cat, phrase = best
        confidence = min(0.98, 0.72 + len(phrase) / 60)
        return _hit(cat, confidence, q, matched_keyword=phrase)

    # 3. Fuzzy scoring
    candidates = _score_all(q)
    if candidates and candidates[0]["score"] >= 0.4:
        cat = get_category(candidates[0]["id"])
        return _hit(cat, candidates[0]["score"] * 0.75, q,
                    is_fuzzy=True, suggestions=candidates[:6])

    # 4. No match
    import urllib.parse
    fallback = (f"MATCH (f:File) WHERE toLower(f.name) CONTAINS toLower('{_san(q)}') "
                f"AND f.tenant_id = $tid RETURN f LIMIT 50")
    return {
        "matched_category":  None,
        "category":          None,
        "confidence":        0.0,
        "suggestions":       _score_all(q)[:6],
        "no_match_query_url":f"/query?q={urllib.parse.quote(fallback)}",
        "message":           f"No data category matches \u201c{query}\u201d.",
    }


def _score_all(q: str) -> list[dict]:
    words = [w for w in q.split() if len(w) >= 3]
    out = []
    for cat in ALL_CATEGORIES:
        s = 0.0
        nl, dl = cat.name.lower(), cat.description.lower()
        if q in nl:      s += 0.9
        elif q in dl:    s += 0.5
        for w in words:
            if w in nl:  s += 0.3
            if w in dl:  s += 0.15
        for tag in cat.tags:
            if tag in q or any(w in tag for w in words): s += 0.15
        if s > 0:
            out.append({"id": cat.id, "name": cat.name, "icon": cat.icon,
                        "color": cat.color, "description": cat.description,
                        "score": round(s, 3)})
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def _hit(cat, confidence, query, matched_keyword=None,
         is_fuzzy=False, suggestions=None):
    if not cat:
        return {"matched_category": None, "confidence": 0, "suggestions": []}
    return {
        "matched_category": cat.id,
        "category": {"id": cat.id, "name": cat.name, "description": cat.description,
                     "icon": cat.icon, "color": cat.color},
        "confidence":      round(confidence, 3),
        "matched_keyword": matched_keyword,
        "is_fuzzy":        is_fuzzy,
        "suggestions":     suggestions or _score_all(query)[:6],
        "navigate_url":    f"/inventory?cat={cat.id}",
    }


def _san(q): return re.sub(r"['\"\\\n\r;]", "", q)[:100]


# ── API ────────────────────────────────────────────────────────────────────────

@router.get("")
async def search_inventory(
    q:    str = Query(..., min_length=1, max_length=200),
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    """Resolve natural language to a data inventory category."""
    return resolve_query(q)


@router.get("/suggest")
async def suggest_categories(
    q:     str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=8, le=20),
    auth:  AuthContext = Depends(get_auth_context),
) -> list[dict[str, Any]]:
    """Typeahead suggestions as the user types."""
    ql = q.lower()
    prefix = [{"id": c.id, "name": c.name, "icon": c.icon,
               "color": c.color, "description": c.description, "score": 1.0}
              for c in ALL_CATEGORIES if c.name.lower().startswith(ql)]
    seen = {h["id"] for h in prefix}
    merged = prefix + [s for s in _score_all(ql) if s["id"] not in seen]
    return merged[:limit]
