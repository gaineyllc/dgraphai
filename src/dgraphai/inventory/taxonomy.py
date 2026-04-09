"""
Data and technology inventory taxonomy.
Normalizes the raw graph into meaningful categories that non-technical
users can browse — like Wiz's "Technology" view.

Each category is:
  - A human-readable name and description
  - A Cypher query that returns matching nodes
  - An icon, color, and group
  - Optionally hierarchical (subcategories)

Clicking a category navigates to QueryWorkspace with the query pre-loaded.
The URL encodes the query, making every view shareable and bookmarkable.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

CATEGORY_GROUPS = [
    "Data & Content",
    "Software & Applications",
    "Security & Credentials",
    "Infrastructure",
    "People & Identity",
]


@dataclass
class Category:
    id:          str
    name:        str
    description: str
    group:       str
    icon:        str           # emoji or icon name
    color:       str           # hex
    cypher:      str           # query that returns nodes for this category
    count_field: str = "f"     # variable name in cypher to count
    subcategories: list["Category"] = field(default_factory=list)
    tags:        list[str] = field(default_factory=list)


INVENTORY: list[Category] = [

    # ── Data & Content ────────────────────────────────────────────────────────

    Category(
        id          = "video-media",
        name        = "Video Media",
        description = "All video files including movies, TV shows, and recordings",
        group       = "Data & Content",
        icon        = "🎬",
        color       = "#4f8ef7",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'video' AND f.tenant_id = $tid RETURN f",
        tags        = ["media", "video"],
    ),
    Category(
        id          = "4k-video",
        name        = "4K / UHD Video",
        description = "Video files with 2160p resolution",
        group       = "Data & Content",
        icon        = "📺",
        color       = "#6366f1",
        cypher      = "MATCH (f:File) WHERE f.resolution = '2160p' AND f.tenant_id = $tid RETURN f",
        tags        = ["media", "video", "4k"],
    ),
    Category(
        id          = "audio-media",
        name        = "Audio",
        description = "Music, podcasts, and audio recordings",
        group       = "Data & Content",
        icon        = "🎵",
        color       = "#a78bfa",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'audio' AND f.tenant_id = $tid RETURN f",
        tags        = ["media", "audio"],
    ),
    Category(
        id          = "images",
        name        = "Images & Photos",
        description = "Photos, screenshots, and image files",
        group       = "Data & Content",
        icon        = "🖼️",
        color       = "#34d399",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'image' AND f.tenant_id = $tid RETURN f",
        tags        = ["media", "images"],
    ),
    Category(
        id          = "documents",
        name        = "Documents",
        description = "PDFs, Word docs, spreadsheets, and presentations",
        group       = "Data & Content",
        icon        = "📄",
        color       = "#fbbf24",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'document' AND f.tenant_id = $tid RETURN f",
        tags        = ["documents"],
    ),
    Category(
        id          = "pii-data",
        name        = "Personal Data (PII)",
        description = "Files containing personally identifiable information",
        group       = "Data & Content",
        icon        = "🔒",
        color       = "#f87171",
        cypher      = "MATCH (f:File) WHERE f.pii_detected = true AND f.tenant_id = $tid RETURN f",
        tags        = ["security", "pii", "compliance"],
    ),
    Category(
        id          = "high-sensitivity",
        name        = "High Sensitivity Files",
        description = "Files classified as high sensitivity",
        group       = "Data & Content",
        icon        = "🔴",
        color       = "#ef4444",
        cypher      = "MATCH (f:File) WHERE f.sensitivity_level = 'high' AND f.tenant_id = $tid RETURN f",
        tags        = ["security", "compliance"],
    ),
    Category(
        id          = "source-code",
        name        = "Source Code",
        description = "Programming files and scripts",
        group       = "Data & Content",
        icon        = "💻",
        color       = "#22d3ee",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'code' AND f.tenant_id = $tid RETURN f",
        tags        = ["code"],
    ),
    Category(
        id          = "archives",
        name        = "Archives & Compressed",
        description = "ZIP, RAR, 7z, tar, and other archives",
        group       = "Data & Content",
        icon        = "📦",
        color       = "#fb923c",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'archive' AND f.tenant_id = $tid RETURN f",
        tags        = ["archives"],
    ),
    Category(
        id          = "duplicate-files",
        name        = "Duplicate Files",
        description = "Files with identical content (same SHA-256 hash)",
        group       = "Data & Content",
        icon        = "♻️",
        color       = "#6b7280",
        cypher      = (
            "MATCH (f:File) WHERE f.sha256 IS NOT NULL AND f.tenant_id = $tid "
            "WITH f.sha256 AS h, collect(f) AS files WHERE size(files) > 1 "
            "UNWIND files AS f RETURN f"
        ),
        tags        = ["storage", "cleanup"],
    ),

    # ── Software & Applications ───────────────────────────────────────────────

    Category(
        id          = "all-software",
        name        = "All Applications",
        description = "All installed and portable software",
        group       = "Software & Applications",
        icon        = "⚙️",
        color       = "#8b5cf6",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'executable' AND f.tenant_id = $tid RETURN f",
        tags        = ["software"],
    ),
    Category(
        id          = "eol-software",
        name        = "End-of-Life Software",
        description = "Applications past their support end date",
        group       = "Software & Applications",
        icon        = "💀",
        color       = "#f87171",
        cypher      = "MATCH (f:File) WHERE f.eol_status = 'eol' AND f.tenant_id = $tid RETURN f",
        tags        = ["software", "security", "compliance"],
    ),
    Category(
        id          = "unsigned-executables",
        name        = "Unsigned Executables",
        description = "Executables without a valid code signature",
        group       = "Software & Applications",
        icon        = "⚠️",
        color       = "#fbbf24",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'executable' AND f.signed = false AND f.tenant_id = $tid RETURN f",
        tags        = ["software", "security"],
    ),
    Category(
        id          = "packed-executables",
        name        = "Packed / Obfuscated",
        description = "Executables with high entropy (possibly packed or encrypted)",
        group       = "Software & Applications",
        icon        = "🎭",
        color       = "#fb923c",
        cypher      = "MATCH (f:File) WHERE f.is_packed = true AND f.tenant_id = $tid RETURN f",
        tags        = ["software", "security"],
    ),

    # ── Security & Credentials ────────────────────────────────────────────────

    Category(
        id          = "exposed-secrets",
        name        = "Exposed Secrets",
        description = "Files containing API keys, passwords, or tokens",
        group       = "Security & Credentials",
        icon        = "🔑",
        color       = "#f87171",
        cypher      = "MATCH (f:File) WHERE f.contains_secrets = true AND f.tenant_id = $tid RETURN f",
        tags        = ["security", "secrets"],
    ),
    Category(
        id          = "certificates",
        name        = "Certificates",
        description = "TLS, code signing, and other certificates",
        group       = "Security & Credentials",
        icon        = "🏅",
        color       = "#4ade80",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'certificate' AND f.tenant_id = $tid RETURN f",
        tags        = ["certificates"],
    ),
    Category(
        id          = "expired-certs",
        name        = "Expired Certificates",
        description = "Certificates that have passed their expiry date",
        group       = "Security & Credentials",
        icon        = "❌",
        color       = "#f87171",
        cypher      = "MATCH (f:File) WHERE f.cert_is_expired = true AND f.tenant_id = $tid RETURN f",
        tags        = ["certificates", "security"],
    ),
    Category(
        id          = "expiring-certs",
        name        = "Certificates Expiring Soon",
        description = "Certificates expiring within 30 days",
        group       = "Security & Credentials",
        icon        = "⏰",
        color       = "#fbbf24",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'certificate' AND f.days_until_expiry < 30 AND f.days_until_expiry >= 0 AND f.tenant_id = $tid RETURN f",
        tags        = ["certificates", "security"],
    ),
    Category(
        id          = "cve-affected",
        name        = "CVE-Affected Software",
        description = "Applications with known vulnerabilities",
        group       = "Security & Credentials",
        icon        = "🛡️",
        color       = "#f87171",
        cypher      = "MATCH (a:Application)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE a.tenant_id = $tid RETURN DISTINCT a AS f",
        tags        = ["security", "cve"],
    ),

    # ── People & Identity ─────────────────────────────────────────────────────

    Category(
        id          = "known-people",
        name        = "Identified People",
        description = "People identified in photos and documents",
        group       = "People & Identity",
        icon        = "👤",
        color       = "#f472b6",
        cypher      = "MATCH (p:Person) WHERE p.known = true AND p.tenant_id = $tid RETURN p AS f",
        count_field = "f",
        tags        = ["people"],
    ),
    Category(
        id          = "face-clusters",
        name        = "Face Clusters",
        description = "Groups of files containing the same person",
        group       = "People & Identity",
        icon        = "👥",
        color       = "#ec4899",
        cypher      = "MATCH (fc:FaceCluster) WHERE fc.tenant_id = $tid RETURN fc AS f",
        tags        = ["people", "faces"],
    ),

]

# Index by ID for fast lookup
CATEGORY_INDEX: dict[str, Category] = {c.id: c for c in INVENTORY}


def get_category(category_id: str) -> Category | None:
    return CATEGORY_INDEX.get(category_id)


def get_by_group() -> dict[str, list[Category]]:
    result: dict[str, list[Category]] = {}
    for cat in INVENTORY:
        result.setdefault(cat.group, []).append(cat)
    return result
