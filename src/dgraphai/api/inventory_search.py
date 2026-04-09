"""
Natural language category search for the Data Inventory.

The Data Inventory is a normalized taxonomy of data types — not a query engine.
This endpoint maps natural language to the best matching CATEGORY only.

If the query maps to a category → return that category (navigate to it).
If the query doesn't match any category → suggest the closest ones + offer
  "View in Graph" as an escape hatch (separate concern, separate surface).

No Cypher synthesis here. No attribute filters. Just: what type of data is this?
"""
from __future__ import annotations
import re
from typing import Any

from fastapi import APIRouter, Depends, Query

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.inventory.taxonomy import ALL_CATEGORIES, get_category, CATEGORY_INDEX

router = APIRouter(prefix="/api/inventory/search", tags=["inventory"])


# ── Keyword → category map ────────────────────────────────────────────────────
# Each tuple: (list of phrases that should resolve to this category).
# Order within a phrase list: longest/most-specific phrases first — they
# get higher scores and beat shorter generic phrases.

KEYWORD_MAP: list[tuple[list[str], str]] = [

    # ── Video ──────────────────────────────────────────────────────────────────
    (["4k hdr", "4k dolby", "uhd hdr", "dolby vision 4k", "4k dolby vision"],  "video-4k-hdr"),
    (["4k av1", "av1 4k"],                                                      "video-4k-av1"),
    (["4k", "uhd", "2160p", "4k video", "4k movies", "4k films"],              "video-4k"),
    (["hdr video", "hdr10 video", "dolby vision", "hdr10", "hlg", "hdr"],      "video-hdr"),
    (["1080p", "full hd", "1080p video", "full hd video"],                     "video-1080p"),
    (["long video", "feature film", "feature films", "movies", "films"],       "video-long"),
    (["video matched", "tmdb video", "imdb video"],                            "video-matched-media"),
    (["24fps", "24p", "cinema fps", "cinematic framerate"],                    "video-24fps"),
    (["60fps", "60p", "high frame rate", "hfr video"],                         "video-60fps"),
    (["wide color gamut", "bt2020", "bt.2020", "wcg"],                         "video-wide-color"),
    (["10-bit video", "10 bit video", "hdr bit depth"],                        "video-bit-depth"),
    (["subtitled video", "subtitles", "closed captions", "captioned"],         "video-subtitles"),
    (["video", "videos", "mkv", "mp4", "movie file", "movie files"],           "video"),

    # ── Audio ──────────────────────────────────────────────────────────────────
    (["lossless audio", "lossless music", "flac music", "wav music"],          "audio-lossless"),
    (["flac", "wav files", "alac", "dsd"],                                     "audio-lossless"),
    (["hi-res audio", "hires audio", "96khz", "high resolution audio"],        "audio-hires"),
    (["untagged music", "untagged audio", "missing tags", "no artist tag"],    "audio-untagged"),
    (["fully tagged", "tagged music", "complete tags"],                        "audio-tagged"),
    (["musicbrainz", "acoustid", "fingerprinted audio"],                       "audio-musicbrainz"),
    (["slow bpm", "slow music", "ambient music", "chill music"],               "audio-slow"),
    (["high bpm", "fast bpm", "fast music", "edm", "dance music"],             "audio-fast"),
    (["bpm", "beats per minute", "tempo"],                                     "audio-bpm"),
    (["audio", "music", "songs", "tracks", "mp3", "aac"],                      "audio"),

    # ── Images ─────────────────────────────────────────────────────────────────
    (["photos with faces", "images with faces", "photos of people",
      "pictures with faces", "portraits with faces"],                          "images-with-faces"),
    (["identified faces", "named faces", "known people in photos",
      "recognized faces", "photos of identified people"],                     "images-identified-people"),
    (["group photos", "group shots", "crowd photos", "multiple people"],       "images-group-shots"),
    (["geotagged photos", "photos with gps", "location tagged photos",
      "gps photos"],                                                           "images-geotagged"),
    (["linked to location", "photos near", "location photos"],                 "images-located"),
    (["raw photos", "raw images", "cr2 files", "nef files", "arw files",
      "heic files", "heic images", "cr2", "nef", "arw", "heic", "raw format"],"images-raw"),
    (["ai vision analyzed", "vision analyzed", "llava analyzed"],              "images-ai-analyzed"),
    (["screenshots", "screen captures", "screen shots"],                       "images-screenshots"),
    (["telephoto photos", "zoom photos", "long lens photos"],                  "images-telephoto"),
    (["wide angle photos", "landscape photos", "wide lens"],                   "images-wide-angle"),
    (["high iso", "noisy photos", "low light photos", "night photos"],         "images-high-iso"),
    (["long exposure", "slow shutter photos", "light trails"],                 "images-long-exposure"),
    (["duplicate images", "duplicate photos"],                                 "images-duplicates"),
    (["faces", "face detected"],                                               "images-with-faces"),
    (["photos", "pictures", "images", "jpg", "jpeg", "png", "tiff"],          "images"),

    # ── Documents ──────────────────────────────────────────────────────────────
    (["pii documents", "documents with pii", "personal data documents",
      "gdpr documents"],                                                       "docs-pii"),
    (["high sensitivity documents", "confidential documents",
      "sensitive documents"],                                                  "docs-pii-high"),
    (["contracts", "legal agreements", "nda", "legal documents"],              "docs-contracts"),
    (["invoices", "billing documents", "receipts"],                            "docs-invoices"),
    (["reports", "business reports", "quarterly reports"],                     "docs-reports"),
    (["manuals", "user guides", "documentation files"],                        "docs-manuals"),
    (["pdf files", "pdf documents", "pdfs"],                                   "docs-pdf"),
    (["spreadsheets", "excel files", "xlsx files", "csv files",
      "excel spreadsheets", "csv data"],                                     "docs-spreadsheet"),
    (["office documents", "word documents", "docx", "powerpoint"],             "docs-office"),
    (["encrypted documents", "password protected docs", "locked documents"],   "docs-encrypted"),
    (["documents with macros", "macro files", "vba files", "office macros"],   "docs-with-macros"),
    (["digitally signed documents", "signed documents"],                       "docs-digitally-signed"),
    (["documents mentioning people", "docs with people"],                      "docs-mentions-person"),
    (["documents mentioning companies", "docs with organizations"],            "docs-mentions-org"),
    (["non-english documents", "foreign language documents", "multilingual"],  "docs-multilingual"),
    (["documents with action items", "docs with tasks", "action item docs"],   "docs-has-action-items"),
    (["documents", "docs"],                                                     "documents"),

    # ── Email ──────────────────────────────────────────────────────────────────
    (["emails with pii", "personal emails", "pii in emails"],                  "emails-pii"),
    (["emails with action items", "email tasks"],                              "emails-action-items"),
    (["emails with people", "emails mentioning people"],                       "emails-mentions-people"),
    (["emails", "email files", "eml", "msg", "mbox"],                          "emails"),

    # ── Source code ────────────────────────────────────────────────────────────
    (["source code with secrets", "code with secrets", "code with api keys",
      "secrets in code", "hardcoded secrets", "exposed secrets in code"],      "code-secrets"),
    (["code with security issues", "vulnerable code", "insecure source code"], "code-security-concerns"),
    (["poor quality code", "bad code", "low quality code"],                    "code-poor-quality"),
    (["config files", "configuration files", "env files", "yaml configs"],     "code-config"),
    (["test files", "unit tests", "test suites"],                              "code-tests"),
    (["licensed source code", "open source code"],                             "code-licensed"),
    (["similar code files", "related code"],                                   "code-similar"),
    (["source code", "code files", "scripts", "python files",
      "javascript files"],                                                     "code"),

    # ── Executables / binaries ─────────────────────────────────────────────────
    (["end of life software", "eol software", "unsupported software",
      "expired software"],                                                     "exe-eol"),
    (["unsigned executables", "unsigned binaries", "unsigned apps"],           "exe-unsigned"),
    (["high risk binaries", "risky executables", "suspicious binaries"],       "exe-high-risk"),
    (["packed executables", "packed binaries", "obfuscated binaries",
      "high entropy binaries"],                                                "exe-packed"),
    (["kernel drivers", "sys files", "device drivers"],                        "exe-drivers"),
    (["outdated software", "old versions", "versions behind", "behind latest"],"exe-versions-behind"),
    (["universal binaries", "fat binaries", "multi-arch binaries"],            "exe-universal"),
    (["executables with cve", "software with vulnerabilities",
      "vulnerable software"],                                                  "exe-with-vulnerabilities"),
    (["executables", "binaries", "exe files", "dll files", "applications"],    "executables"),
    (["archives with executables", "zips with exe", "archives containing exe"],"archives-with-exe"),
    (["archives", "zip files", "rar files", "compressed files", "7z"],         "archives"),

    # ── Security — certificates ────────────────────────────────────────────────
    (["expired certificates", "expired certs", "expired ssl", "expired tls"],  "certs-expired"),
    (["expiring certificates", "certs expiring soon", "ssl expiring"],         "certs-expiring-30"),
    (["self-signed certificates", "self signed certs"],                        "certs-self-signed"),
    (["weak key certificates", "weak rsa certs", "small key certs"],           "certs-weak-keys"),
    (["certificate authorities", "ca certificates", "root certs"],             "certs-ca"),
    (["ec certificates", "elliptic curve certs", "ecdsa", "ed25519 certs"],    "certs-ec"),
    (["certificates used by software", "signing certs"],                       "certs-used-by"),
    (["private keys", "key files", "pem keys", "rsa keys"],                    "private-keys"),
    (["certificates", "ssl certs", "tls certs", "x509"],                       "certificates"),

    # ── Security — secrets ─────────────────────────────────────────────────────
    (["api keys in files", "exposed api keys", "leaked api keys"],             "secrets-api-keys"),
    (["passwords in files", "exposed passwords", "leaked passwords",
      "hardcoded passwords"],                                                  "secrets-passwords"),
    (["auth tokens", "bearer tokens", "access tokens in files"],               "secrets-tokens"),
    (["private keys in code", "embedded private keys"],                        "secrets-private-keys-in-code"),
    (["api keys", "api key"],                                                  "secrets-api-keys"),
    (["passwords", "credentials", "hardcoded credentials"],                    "secrets-passwords"),
    (["secrets", "exposed secrets", "leaked secrets"],                         "secrets"),

    # ── Security — PII ─────────────────────────────────────────────────────────
    (["high sensitivity pii", "critical pii", "sensitive personal data"],      "pii-high"),
    (["ssn", "social security numbers", "national id numbers"],                "pii-ssn"),
    (["email addresses in files", "phone numbers in files"],                   "pii-emails-phones"),
    (["pii", "personal data", "personal information", "gdpr data"],            "pii"),

    # ── Vulnerabilities ────────────────────────────────────────────────────────
    (["critical cve", "critical vulnerabilities", "critical cvss"],            "cve-critical"),
    (["actively exploited cve", "exploited vulnerabilities", "zero day"],      "cve-exploited"),
    (["cve with exploit", "exploit available"],                                "cve-with-exploit"),
    (["vulnerable dependencies", "dependency vulnerabilities"],                "cve-dep-chain"),
    (["cve", "cves", "vulnerabilities", "known vulnerabilities"],              "vulnerabilities"),

    # ── People & identity ──────────────────────────────────────────────────────
    (["identified people", "known people", "named people",
      "recognized people", "people identified"],                              "people-identified"),
    (["unknown faces", "unidentified faces", "unrecognized people"],           "people-unknown-clusters"),
    (["people mentioned in documents", "entity people"],                       "people-entity-extracted"),
    (["people depicted in images", "people in photos"],                        "people-depicts"),
    (["people", "persons", "individuals", "faces"],                            "people"),
    (["organizations", "companies", "firms"],                                  "orgs-mentioned-in-docs"),

    # ── Knowledge graph nodes ──────────────────────────────────────────────────
    (["locations", "places", "geographic data"],                               "locations"),
    (["topics", "subjects", "themes"],                                         "topics"),
    (["events", "calendar events", "occasions"],                               "events"),
    (["collections", "file groups", "named groups"],                           "collections"),
    (["matched movies", "tmdb movies", "imdb movies", "movies in tmdb"],        "media-movies"),
    (["movies", "films", "feature films", "long videos"],                        "video-long"),
    (["matched tv shows", "tv series in db"],                                  "media-tv"),
    (["media items", "matched media"],                                         "media-items"),

    # ── Software graph ─────────────────────────────────────────────────────────
    (["applications", "installed apps", "installed software"],                 "applications"),
    (["software vendors", "app vendors"],                                      "vendors"),
    (["software licenses", "license files"],                                   "licenses"),
    (["copyleft licenses", "gpl", "agpl", "lgpl"],                             "licenses-copyleft"),
    (["software dependencies", "package dependencies", "npm packages"],        "dependencies"),
    (["vulnerable dependencies", "packages with cve"],                         "deps-vulnerable"),

    # ── Storage & duplication ──────────────────────────────────────────────────
    (["duplicate files", "duplicates", "identical files"],                     "duplicates"),
    (["large files", "big files", "huge files"],                               "large-files"),
    (["directories", "folders", "folder structure"],                           "directories"),

    # ── AI analysis ────────────────────────────────────────────────────────────
    (["ai enriched files", "ai analyzed files", "ai processed"],               "ai-enriched"),
    (["negative sentiment", "negative tone files"],                            "ai-negative-sentiment"),
    (["semantically related", "similar files"],                                "ai-inferred-relationships"),
    (["files with action items", "action item files"],                         "ai-action-items"),
    (["pending enrichment", "unenriched files", "not yet analyzed"],           "ai-pending-enrichment"),

    # ── Media detail ───────────────────────────────────────────────────────────
    (["3d models", "cad files", "stl files", "obj files"],                     "3d-models"),
    (["calendar files", "contact files", "ics files", "vcf files"],            "calendar-contacts"),
]


# ── Resolution logic ──────────────────────────────────────────────────────────

def resolve_query(query: str) -> dict[str, Any]:
    """
    Resolve a natural language query to the best matching inventory category.

    Returns:
      matched_category: str | None   — category id if a match found
      category: dict | None          — full category details
      confidence: float              — 0..1
      suggestions: list[dict]        — top related categories
      no_match_query_url: str | None — escape hatch to graph query view
    """
    q = query.strip().lower()

    # 1. Exact category name match (highest confidence)
    for cat in ALL_CATEGORIES:
        if cat.name.lower() == q:
            return _hit(cat, 1.0, q)

    # 2. Multi-word keyword scoring
    #    For every keyword that appears in the query, score:
    #      - length of the keyword (longer = more specific)
    #      - +3 per word in the keyword (multi-word beats single-word)
    #    Pick the highest-scoring match.
    best: tuple[float, Any, str] | None = None   # (score, cat, keyword)

    for phrases, cat_id in KEYWORD_MAP:
        cat = get_category(cat_id)
        if not cat:
            continue
        for phrase in phrases:
            if phrase not in q:
                continue
            n_words = len(phrase.split())
            score   = len(phrase) + n_words * 4   # multi-word bonus
            if best is None or score > best[0]:
                best = (score, cat, phrase)

    if best:
        score, cat, phrase = best
        confidence = min(0.98, 0.70 + (score / 80))
        return _hit(cat, confidence, q, matched_keyword=phrase)

    # 3. Fuzzy: score all categories by name/description/tag similarity
    candidates = _score_all(q)
    if candidates:
        top = candidates[0]
        if top["score"] >= 0.5:
            cat = get_category(top["id"])
            return _hit(cat, top["score"] * 0.8, q,
                       is_fuzzy=True, suggestions=candidates[:6])

    # 4. No match — return suggestions and an escape hatch to the graph
    import urllib.parse
    fallback_q = (
        f"MATCH (f:File) WHERE toLower(f.name) CONTAINS toLower('{_sanitize(q)}') "
        f"AND f.tenant_id = $tid RETURN f LIMIT 50"
    )
    return {
        "matched_category":  None,
        "category":          None,
        "confidence":        0.0,
        "suggestions":       _score_all(q)[:6],
        "no_match_query_url":f"/query?q={urllib.parse.quote(fallback_q)}",
        "message":           f"No data category matches \u201c{query}\u201d. Try the Graph for custom queries.",
    }


def _score_all(q: str) -> list[dict]:
    """Score all categories by relevance to query, return ranked list."""
    words = [w for w in q.split() if len(w) >= 3]
    results = []
    for cat in ALL_CATEGORIES:
        score = 0.0
        nl = cat.name.lower()
        dl = cat.description.lower()
        if q in nl:              score += 0.9
        elif q in dl:            score += 0.5
        for w in words:
            if w in nl:          score += 0.3
            if w in dl:          score += 0.15
        for tag in cat.tags:
            if tag in q or q in tag: score += 0.25
            if any(w in tag for w in words): score += 0.1
        if score > 0:
            results.append({
                "id": cat.id, "name": cat.name, "icon": cat.icon,
                "color": cat.color, "description": cat.description,
                "score": round(score, 3),
            })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _hit(cat, confidence: float, query: str,
         matched_keyword: str = None, is_fuzzy: bool = False,
         suggestions: list = None) -> dict:
    if cat is None:
        return {"matched_category": None, "confidence": 0, "suggestions": []}
    return {
        "matched_category": cat.id,
        "category": {
            "id": cat.id, "name": cat.name, "description": cat.description,
            "icon": cat.icon, "color": cat.color,
        },
        "confidence":      round(confidence, 3),
        "matched_keyword": matched_keyword,
        "is_fuzzy":        is_fuzzy,
        "suggestions":     suggestions or _score_all(query)[:6],
        "navigate_url":    f"/inventory?cat={cat.id}",
    }


def _sanitize(q: str) -> str:
    return re.sub(r"['\"\\\n\r;]", "", q)[:100]


# ── API routes ─────────────────────────────────────────────────────────────────

@router.get("")
async def search_inventory(
    q:    str = Query(..., min_length=1, max_length=200),
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    """
    Resolve a natural language query to the best matching data category.

    Returns the category to navigate to, or suggestions + an escape-hatch
    URL for the Graph view if nothing matches.

    Examples:
      ?q=4k+hdr+movies        → video-4k-hdr
      ?q=exposed+passwords    → secrets-passwords
      ?q=photos+with+faces    → images-with-faces
      ?q=contracts            → docs-contracts
    """
    return resolve_query(q)


@router.get("/suggest")
async def suggest_categories(
    q:     str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=8, le=20),
    auth:  AuthContext = Depends(get_auth_context),
) -> list[dict[str, Any]]:
    """
    Typeahead: returns ranked category suggestions as the user types.
    Used to populate the dropdown on each keystroke.
    """
    ql = q.lower()

    # Prefix match on category name first (feels most like autocomplete)
    prefix_hits = [
        {"id": c.id, "name": c.name, "icon": c.icon,
         "color": c.color, "description": c.description, "score": 1.0}
        for c in ALL_CATEGORIES
        if c.name.lower().startswith(ql)
    ]

    # Then fuzzy scoring for the rest
    scored = _score_all(ql)

    # Merge, deduplicate, cap
    seen: set[str] = {h["id"] for h in prefix_hits}
    merged = prefix_hits + [s for s in scored if s["id"] not in seen]
    return merged[:limit]
