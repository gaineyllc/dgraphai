"""
Data and technology inventory taxonomy.
Hierarchical categories — each has optional subcategories for drill-down.
Each category defines which columns to show when listing its nodes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Column:
    """A column to display in the node table for this category."""
    key:     str           # node property key
    label:   str           # display header
    width:   int = 160     # px hint
    kind:    str = "text"  # text | size | date | badge | bool | path


@dataclass
class Category:
    id:            str
    name:          str
    description:   str
    group:         str
    icon:          str
    color:         str
    cypher:        str         # full MATCH … RETURN f query
    count_field:   str = "f"
    columns:       list[Column] = field(default_factory=list)
    subcategories: list["Category"] = field(default_factory=list)
    tags:          list[str] = field(default_factory=list)
    parent_id:     str | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _file_base() -> list[Column]:
    return [
        Column("name",       "Name",        220, "text"),
        Column("path",       "Path",        300, "path"),
        Column("size",       "Size",        90,  "size"),
        Column("modified_at","Modified",    130, "date"),
        Column("source_connector", "Source", 120, "badge"),
    ]


# ── Inventory ──────────────────────────────────────────────────────────────────

INVENTORY: list[Category] = [

    # ══ Data & Content ═══════════════════════════════════════════════════════

    Category(
        id          = "media",
        name        = "Media",
        description = "All media files — video, audio, and images",
        group       = "Data & Content",
        icon        = "🎬",
        color       = "#4f8ef7",
        cypher      = "MATCH (f:File) WHERE f.file_category IN ['video','audio','image'] AND f.tenant_id = $tid RETURN f",
        columns     = _file_base() + [Column("file_category","Type",80,"badge"), Column("duration","Duration",90,"text")],
        tags        = ["media"],
        subcategories = [
            Category(
                id          = "video-media",
                name        = "Video",
                description = "All video files",
                group       = "Data & Content",
                icon        = "📹",
                color       = "#4f8ef7",
                parent_id   = "media",
                cypher      = "MATCH (f:File) WHERE f.file_category = 'video' AND f.tenant_id = $tid RETURN f",
                columns     = _file_base() + [
                    Column("resolution",  "Resolution", 90, "badge"),
                    Column("codec",       "Codec",      90, "badge"),
                    Column("duration",    "Duration",   90, "text"),
                    Column("hdr_format",  "HDR",        80, "badge"),
                ],
                tags        = ["media", "video"],
                subcategories = [
                    Category(
                        id        = "video-4k",
                        name      = "4K / UHD",
                        description = "2160p video files",
                        group     = "Data & Content",
                        icon      = "📺",
                        color     = "#818cf8",
                        parent_id = "video-media",
                        cypher    = "MATCH (f:File) WHERE f.file_category = 'video' AND f.resolution = '2160p' AND f.tenant_id = $tid RETURN f",
                        columns   = _file_base() + [Column("resolution","Resolution",90,"badge"), Column("hdr_format","HDR",80,"badge"), Column("codec","Codec",90,"badge"), Column("size","Size",90,"size")],
                        tags      = ["media","video","4k"],
                    ),
                    Category(
                        id        = "video-hdr",
                        name      = "HDR / Dolby Vision",
                        description = "Video with HDR or Dolby Vision grading",
                        group     = "Data & Content",
                        icon      = "✨",
                        color     = "#6366f1",
                        parent_id = "video-media",
                        cypher    = "MATCH (f:File) WHERE f.file_category = 'video' AND f.hdr_format IS NOT NULL AND f.tenant_id = $tid RETURN f",
                        columns   = _file_base() + [Column("hdr_format","HDR Format",100,"badge"), Column("resolution","Resolution",90,"badge"), Column("codec","Codec",90,"badge")],
                        tags      = ["media","video","hdr"],
                    ),
                    Category(
                        id        = "video-1080p",
                        name      = "1080p",
                        description = "Full HD video files",
                        group     = "Data & Content",
                        icon      = "🖥️",
                        color     = "#60a5fa",
                        parent_id = "video-media",
                        cypher    = "MATCH (f:File) WHERE f.file_category = 'video' AND f.resolution = '1080p' AND f.tenant_id = $tid RETURN f",
                        columns   = _file_base() + [Column("resolution","Resolution",90,"badge"), Column("codec","Codec",90,"badge"), Column("size","Size",90,"size")],
                        tags      = ["media","video","1080p"],
                    ),
                ],
            ),
            Category(
                id          = "audio-media",
                name        = "Audio",
                description = "Music, podcasts, and audio recordings",
                group       = "Data & Content",
                icon        = "🎵",
                color       = "#a78bfa",
                parent_id   = "media",
                cypher      = "MATCH (f:File) WHERE f.file_category = 'audio' AND f.tenant_id = $tid RETURN f",
                columns     = _file_base() + [
                    Column("artist",   "Artist",   140, "text"),
                    Column("album",    "Album",    140, "text"),
                    Column("duration", "Duration",  90, "text"),
                    Column("bitrate",  "Bitrate",   80, "badge"),
                ],
                tags        = ["media", "audio"],
            ),
            Category(
                id          = "images",
                name        = "Images & Photos",
                description = "Photos, screenshots, and image files",
                group       = "Data & Content",
                icon        = "🖼️",
                color       = "#34d399",
                parent_id   = "media",
                cypher      = "MATCH (f:File) WHERE f.file_category = 'image' AND f.tenant_id = $tid RETURN f",
                columns     = _file_base() + [
                    Column("width",    "Width",   70, "text"),
                    Column("height",   "Height",  70, "text"),
                    Column("camera",   "Camera", 120, "text"),
                    Column("taken_at", "Taken",  130, "date"),
                ],
                tags        = ["media", "images"],
                subcategories = [
                    Category(
                        id        = "images-faces",
                        name      = "Contains Faces",
                        description = "Photos with detected faces",
                        group     = "Data & Content",
                        icon      = "👤",
                        color     = "#f472b6",
                        parent_id = "images",
                        cypher    = "MATCH (f:File) WHERE f.file_category = 'image' AND f.face_count > 0 AND f.tenant_id = $tid RETURN f",
                        columns   = _file_base() + [Column("face_count","Faces",70,"text"), Column("camera","Camera",120,"text"), Column("taken_at","Taken",130,"date")],
                        tags      = ["images","people"],
                    ),
                    Category(
                        id        = "images-raw",
                        name      = "RAW / HEIF",
                        description = "RAW camera files and HEIF images",
                        group     = "Data & Content",
                        icon      = "📷",
                        color     = "#10b981",
                        parent_id = "images",
                        cypher    = "MATCH (f:File) WHERE f.file_category = 'image' AND f.mime_type IN ['image/x-raw','image/heif','image/heic'] AND f.tenant_id = $tid RETURN f",
                        columns   = _file_base() + [Column("mime_type","Format",100,"badge"), Column("camera","Camera",120,"text"), Column("size","Size",90,"size")],
                        tags      = ["images","raw"],
                    ),
                ],
            ),
        ],
    ),

    Category(
        id          = "documents",
        name        = "Documents",
        description = "PDFs, Word docs, spreadsheets, presentations, and text files",
        group       = "Data & Content",
        icon        = "📄",
        color       = "#fbbf24",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'document' AND f.tenant_id = $tid RETURN f",
        columns     = _file_base() + [Column("mime_type","Type",120,"badge"), Column("page_count","Pages",70,"text"), Column("author","Author",120,"text")],
        tags        = ["documents"],
        subcategories = [
            Category(
                id        = "docs-pdf",
                name      = "PDFs",
                description = "PDF documents",
                group     = "Data & Content",
                icon      = "📕",
                color     = "#f59e0b",
                parent_id = "documents",
                cypher    = "MATCH (f:File) WHERE f.mime_type = 'application/pdf' AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("page_count","Pages",70,"text"), Column("author","Author",120,"text"), Column("pii_detected","PII",60,"bool")],
                tags      = ["documents","pdf"],
            ),
            Category(
                id        = "docs-spreadsheet",
                name      = "Spreadsheets",
                description = "Excel, CSV, and other tabular data",
                group     = "Data & Content",
                icon      = "📊",
                color     = "#10b981",
                parent_id = "documents",
                cypher    = "MATCH (f:File) WHERE f.file_category = 'document' AND f.mime_type IN ['application/vnd.ms-excel','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','text/csv'] AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("mime_type","Format",110,"badge"), Column("pii_detected","PII",60,"bool"), Column("size","Size",90,"size")],
                tags      = ["documents","spreadsheet"],
            ),
            Category(
                id        = "docs-pii",
                name      = "Contains PII",
                description = "Documents with detected personal data",
                group     = "Data & Content",
                icon      = "🔒",
                color     = "#f87171",
                parent_id = "documents",
                cypher    = "MATCH (f:File) WHERE f.file_category = 'document' AND f.pii_detected = true AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("mime_type","Type",110,"badge"), Column("sensitivity_level","Sensitivity",110,"badge"), Column("page_count","Pages",70,"text")],
                tags      = ["documents","pii","compliance"],
            ),
        ],
    ),

    Category(
        id          = "source-code",
        name        = "Source Code",
        description = "Programming files, scripts, and configuration",
        group       = "Data & Content",
        icon        = "💻",
        color       = "#22d3ee",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'code' AND f.tenant_id = $tid RETURN f",
        columns     = _file_base() + [Column("language","Language",100,"badge"), Column("line_count","Lines",80,"text"), Column("contains_secrets","Secrets",80,"bool")],
        tags        = ["code"],
        subcategories = [
            Category(
                id        = "code-secrets",
                name      = "Contains Secrets",
                description = "Source files with hardcoded credentials or tokens",
                group     = "Data & Content",
                icon      = "🔑",
                color     = "#f87171",
                parent_id = "source-code",
                cypher    = "MATCH (f:File) WHERE f.file_category = 'code' AND f.contains_secrets = true AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("language","Language",100,"badge"), Column("line_count","Lines",80,"text"), Column("sensitivity_level","Sensitivity",110,"badge")],
                tags      = ["code","security","secrets"],
            ),
            Category(
                id        = "code-config",
                name      = "Config Files",
                description = ".env, YAML, TOML, JSON config files",
                group     = "Data & Content",
                icon      = "⚙️",
                color     = "#06b6d4",
                parent_id = "source-code",
                cypher    = "MATCH (f:File) WHERE f.file_category = 'code' AND f.language IN ['env','yaml','toml','json','ini','properties'] AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("language","Format",90,"badge"), Column("contains_secrets","Secrets",80,"bool")],
                tags      = ["code","config"],
            ),
        ],
    ),

    Category(
        id          = "archives",
        name        = "Archives",
        description = "ZIP, RAR, 7z, tar, and other compressed files",
        group       = "Data & Content",
        icon        = "📦",
        color       = "#fb923c",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'archive' AND f.tenant_id = $tid RETURN f",
        columns     = _file_base() + [Column("mime_type","Format",110,"badge"), Column("compressed_size","Compressed",90,"size"), Column("uncompressed_size","Uncompressed",110,"size")],
        tags        = ["archives"],
    ),

    Category(
        id          = "duplicate-files",
        name        = "Duplicate Files",
        description = "Files with identical content (same SHA-256 hash)",
        group       = "Data & Content",
        icon        = "♻️",
        color       = "#6b7280",
        cypher      = "MATCH (f:File) WHERE f.sha256 IS NOT NULL AND f.tenant_id = $tid WITH f.sha256 AS h, collect(f) AS files WHERE size(files) > 1 UNWIND files AS f RETURN f",
        columns     = _file_base() + [Column("sha256","Hash",140,"text"), Column("size","Size",90,"size")],
        tags        = ["storage", "cleanup"],
    ),

    # ══ Software & Applications ════════════════════════════════════════════════

    Category(
        id          = "software",
        name        = "Software",
        description = "Installed and portable applications",
        group       = "Software & Applications",
        icon        = "⚙️",
        color       = "#8b5cf6",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'executable' AND f.tenant_id = $tid RETURN f",
        columns     = _file_base() + [Column("version","Version",90,"text"), Column("vendor","Vendor",120,"text"), Column("signed","Signed",70,"bool"), Column("eol_status","EOL",80,"badge")],
        tags        = ["software"],
        subcategories = [
            Category(
                id        = "eol-software",
                name      = "End-of-Life",
                description = "Applications past their support end date",
                group     = "Software & Applications",
                icon      = "💀",
                color     = "#f87171",
                parent_id = "software",
                cypher    = "MATCH (f:File) WHERE f.eol_status = 'eol' AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("version","Version",90,"text"), Column("vendor","Vendor",120,"text"), Column("eol_date","EOL Date",110,"date")],
                tags      = ["software","security","compliance"],
            ),
            Category(
                id        = "unsigned-executables",
                name      = "Unsigned",
                description = "Executables without a valid code signature",
                group     = "Software & Applications",
                icon      = "⚠️",
                color     = "#fbbf24",
                parent_id = "software",
                cypher    = "MATCH (f:File) WHERE f.file_category = 'executable' AND f.signed = false AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("version","Version",90,"text"), Column("vendor","Vendor",120,"text"), Column("size","Size",90,"size")],
                tags      = ["software","security"],
            ),
            Category(
                id        = "packed-executables",
                name      = "Packed / Obfuscated",
                description = "Executables with high entropy",
                group     = "Software & Applications",
                icon      = "🎭",
                color     = "#fb923c",
                parent_id = "software",
                cypher    = "MATCH (f:File) WHERE f.is_packed = true AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("entropy","Entropy",80,"text"), Column("signed","Signed",70,"bool"), Column("size","Size",90,"size")],
                tags      = ["software","security"],
            ),
        ],
    ),

    # ══ Security & Credentials ════════════════════════════════════════════════

    Category(
        id          = "secrets",
        name        = "Secrets & Credentials",
        description = "Files containing exposed credentials, keys, or tokens",
        group       = "Security & Credentials",
        icon        = "🔑",
        color       = "#f87171",
        cypher      = "MATCH (f:File) WHERE f.contains_secrets = true AND f.tenant_id = $tid RETURN f",
        columns     = _file_base() + [Column("sensitivity_level","Severity",110,"badge"), Column("file_category","Type",90,"badge"), Column("language","Language",90,"badge")],
        tags        = ["security","secrets"],
        subcategories = [
            Category(
                id        = "api-keys",
                name      = "API Keys",
                description = "Files with detected API keys",
                group     = "Security & Credentials",
                icon      = "🗝️",
                color     = "#f87171",
                parent_id = "secrets",
                cypher    = "MATCH (f:File) WHERE f.secret_types CONTAINS 'api_key' AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("language","Language",90,"badge"), Column("sensitivity_level","Severity",110,"badge")],
                tags      = ["security","secrets","api-key"],
            ),
            Category(
                id        = "private-keys",
                name      = "Private Keys",
                description = "RSA, EC, and other private key files",
                group     = "Security & Credentials",
                icon      = "🔐",
                color     = "#ef4444",
                parent_id = "secrets",
                cypher    = "MATCH (f:File) WHERE f.file_category = 'private_key' AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("key_type","Key Type",100,"badge"), Column("key_bits","Key Size",80,"text"), Column("passphrase_protected","Protected",90,"bool")],
                tags      = ["security","secrets","keys"],
            ),
        ],
    ),

    Category(
        id          = "certificates",
        name        = "Certificates",
        description = "TLS, code signing, and other certificates",
        group       = "Security & Credentials",
        icon        = "🏅",
        color       = "#4ade80",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'certificate' AND f.tenant_id = $tid RETURN f",
        columns     = _file_base() + [Column("cert_subject","Subject",180,"text"), Column("cert_issuer","Issuer",140,"text"), Column("cert_expiry","Expires",130,"date"), Column("cert_is_expired","Expired",80,"bool")],
        tags        = ["certificates"],
        subcategories = [
            Category(
                id        = "expired-certs",
                name      = "Expired",
                description = "Certificates past their expiry date",
                group     = "Security & Credentials",
                icon      = "❌",
                color     = "#f87171",
                parent_id = "certificates",
                cypher    = "MATCH (f:File) WHERE f.cert_is_expired = true AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("cert_subject","Subject",180,"text"), Column("cert_expiry","Expired",130,"date"), Column("cert_issuer","Issuer",140,"text")],
                tags      = ["certificates","security"],
            ),
            Category(
                id        = "expiring-certs",
                name      = "Expiring Soon",
                description = "Certificates expiring within 30 days",
                group     = "Security & Credentials",
                icon      = "⏰",
                color     = "#fbbf24",
                parent_id = "certificates",
                cypher    = "MATCH (f:File) WHERE f.file_category = 'certificate' AND f.days_until_expiry < 30 AND f.days_until_expiry >= 0 AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("cert_subject","Subject",180,"text"), Column("days_until_expiry","Days Left",90,"text"), Column("cert_issuer","Issuer",140,"text")],
                tags      = ["certificates","security"],
            ),
        ],
    ),

    Category(
        id          = "pii-data",
        name        = "Personal Data (PII)",
        description = "Files containing personally identifiable information",
        group       = "Security & Credentials",
        icon        = "🔒",
        color       = "#f87171",
        cypher      = "MATCH (f:File) WHERE f.pii_detected = true AND f.tenant_id = $tid RETURN f",
        columns     = _file_base() + [Column("sensitivity_level","Sensitivity",110,"badge"), Column("file_category","Type",90,"badge"), Column("pii_types","PII Types",160,"text")],
        tags        = ["security","pii","compliance"],
        subcategories = [
            Category(
                id        = "pii-high",
                name      = "High Sensitivity",
                description = "High-sensitivity PII files",
                group     = "Security & Credentials",
                icon      = "🔴",
                color     = "#ef4444",
                parent_id = "pii-data",
                cypher    = "MATCH (f:File) WHERE f.pii_detected = true AND f.sensitivity_level = 'high' AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("pii_types","PII Types",160,"text"), Column("file_category","Type",90,"badge")],
                tags      = ["pii","compliance"],
            ),
            Category(
                id        = "pii-medium",
                name      = "Medium Sensitivity",
                description = "Medium-sensitivity PII files",
                group     = "Security & Credentials",
                icon      = "🟡",
                color     = "#f59e0b",
                parent_id = "pii-data",
                cypher    = "MATCH (f:File) WHERE f.pii_detected = true AND f.sensitivity_level = 'medium' AND f.tenant_id = $tid RETURN f",
                columns   = _file_base() + [Column("pii_types","PII Types",160,"text"), Column("file_category","Type",90,"badge")],
                tags      = ["pii","compliance"],
            ),
        ],
    ),

    Category(
        id          = "cve-affected",
        name        = "CVE-Affected Software",
        description = "Applications with known vulnerabilities",
        group       = "Security & Credentials",
        icon        = "🛡️",
        color       = "#f87171",
        cypher      = "MATCH (a:Application)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE a.tenant_id = $tid RETURN DISTINCT a AS f",
        columns     = [Column("name","Name",200,"text"), Column("version","Version",90,"text"), Column("vendor","Vendor",120,"text"), Column("source_connector","Source",120,"badge")],
        tags        = ["security","cve"],
    ),

    # ══ People & Identity ══════════════════════════════════════════════════════

    Category(
        id          = "people",
        name        = "People",
        description = "Identified individuals and face clusters in your data",
        group       = "People & Identity",
        icon        = "👤",
        color       = "#f472b6",
        cypher      = "MATCH (p:Person) WHERE p.tenant_id = $tid RETURN p AS f",
        count_field = "f",
        columns     = [Column("name","Name",180,"text"), Column("known","Known",70,"bool"), Column("face_count","Appearances",100,"text"), Column("first_seen","First Seen",130,"date")],
        tags        = ["people"],
        subcategories = [
            Category(
                id        = "known-people",
                name      = "Identified",
                description = "People with a confirmed identity",
                group     = "People & Identity",
                icon      = "✅",
                color     = "#ec4899",
                parent_id = "people",
                cypher    = "MATCH (p:Person) WHERE p.known = true AND p.tenant_id = $tid RETURN p AS f",
                columns   = [Column("name","Name",180,"text"), Column("face_count","Appearances",100,"text"), Column("first_seen","First Seen",130,"date"), Column("last_seen","Last Seen",130,"date")],
                tags      = ["people"],
            ),
            Category(
                id        = "face-clusters",
                name      = "Unidentified Clusters",
                description = "Groups of photos with the same unknown face",
                group     = "People & Identity",
                icon      = "👥",
                color     = "#f472b6",
                parent_id = "people",
                cypher    = "MATCH (fc:FaceCluster) WHERE fc.known = false AND fc.tenant_id = $tid RETURN fc AS f",
                columns   = [Column("cluster_id","Cluster ID",120,"text"), Column("face_count","Appearances",100,"text"), Column("first_seen","First Seen",130,"date")],
                tags      = ["people","faces"],
            ),
        ],
    ),
]

# ── Flat index ─────────────────────────────────────────────────────────────────

def _flatten(cats: list[Category]) -> list[Category]:
    result = []
    for c in cats:
        result.append(c)
        if c.subcategories:
            result.extend(_flatten(c.subcategories))
    return result

ALL_CATEGORIES: list[Category]       = _flatten(INVENTORY)
CATEGORY_INDEX: dict[str, Category]  = {c.id: c for c in ALL_CATEGORIES}


def get_category(category_id: str) -> Category | None:
    return CATEGORY_INDEX.get(category_id)

def get_by_group() -> dict[str, list[Category]]:
    """Return only top-level categories grouped."""
    result: dict[str, list[Category]] = {}
    for cat in INVENTORY:
        result.setdefault(cat.group, []).append(cat)
    return result
