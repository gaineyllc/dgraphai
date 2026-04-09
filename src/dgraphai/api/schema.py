"""
Graph schema API — exposes the complete ontology to the frontend.

The query builder, attribute filter panel, and relationship explorer
all consume this endpoint to populate their dropdowns with real node
types, property names, relationship types, and cardinalities.

GET /api/schema
  Returns the full static ontology (node types, rel types, properties)

GET /api/schema/properties/{node_type}
  Returns property names + types for a specific node type
  (optionally from live graph if ?live=true)

GET /api/schema/stats
  Live counts per node type — used by query builder node palette
"""
from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.session import get_db

router = APIRouter(prefix="/api/schema", tags=["schema"])


# ── Static ontology ────────────────────────────────────────────────────────────

NODE_TYPES: list[dict[str, Any]] = [
    {
        "id": "File",
        "label": "File",
        "icon": "📄",
        "color": "#4f8ef7",
        "description": "An indexed file from any connected source",
        "primary_key": "id",
        "properties": [
            # Identity
            {"key": "id",              "label": "ID",              "type": "string",  "group": "Identity"},
            {"key": "name",            "label": "Name",            "type": "string",  "group": "Identity"},
            {"key": "path",            "label": "Path",            "type": "string",  "group": "Identity"},
            {"key": "extension",       "label": "Extension",       "type": "string",  "group": "Identity"},
            {"key": "mime_type",       "label": "MIME Type",       "type": "string",  "group": "Identity"},
            {"key": "file_category",   "label": "Category",        "type": "string",  "group": "Identity",
             "enum": ["video","audio","image","document","executable","archive","certificate",
                      "private_key","code","web_data","email","calendar","3d_model","other"]},
            # Storage
            {"key": "size",            "label": "Size (bytes)",    "type": "integer", "group": "Storage"},
            {"key": "sha256",          "label": "SHA-256",         "type": "string",  "group": "Storage"},
            {"key": "protocol",        "label": "Protocol",        "type": "string",  "group": "Storage"},
            {"key": "host",            "label": "Host",            "type": "string",  "group": "Storage"},
            {"key": "share",           "label": "Share",           "type": "string",  "group": "Storage"},
            {"key": "source_connector","label": "Source Connector","type": "string",  "group": "Storage"},
            # Timestamps
            {"key": "created",         "label": "Created",         "type": "datetime","group": "Timestamps"},
            {"key": "modified_at",     "label": "Modified",        "type": "datetime","group": "Timestamps"},
            {"key": "indexed_at",      "label": "Indexed At",      "type": "datetime","group": "Timestamps"},
            # Enrichment status
            {"key": "enrichment_status","label": "Enrichment Status","type": "string","group": "Processing",
             "enum": ["pending","processing","done","skipped","error"]},
            # AI
            {"key": "summary",         "label": "AI Summary",      "type": "string",  "group": "AI"},
            {"key": "sentiment",       "label": "Sentiment",       "type": "string",  "group": "AI",
             "enum": ["positive","negative","neutral"]},
            {"key": "language",        "label": "Language",        "type": "string",  "group": "AI"},
            {"key": "document_type",   "label": "Document Type",   "type": "string",  "group": "AI",
             "enum": ["invoice","contract","report","email","memo","article","manual","financial_statement","legal_filing","other"]},
            {"key": "action_items",    "label": "Action Items",    "type": "string",  "group": "AI"},
            {"key": "entities_people", "label": "People (entities)","type": "string", "group": "AI"},
            {"key": "entities_organizations","label": "Orgs (entities)","type": "string","group": "AI"},
            {"key": "entities_locations","label": "Locations (entities)","type": "string","group": "AI"},
            {"key": "entities_topics", "label": "Topics (entities)","type": "string", "group": "AI"},
            # Video
            {"key": "container_format","label": "Container",       "type": "string",  "group": "Video"},
            {"key": "video_codec",     "label": "Video Codec",     "type": "string",  "group": "Video"},
            {"key": "width",           "label": "Width (px)",      "type": "integer", "group": "Video"},
            {"key": "height",          "label": "Height (px)",     "type": "integer", "group": "Video"},
            {"key": "duration_secs",   "label": "Duration (s)",    "type": "float",   "group": "Video"},
            {"key": "fps",             "label": "Frame Rate",      "type": "float",   "group": "Video"},
            {"key": "overall_bitrate", "label": "Bitrate",         "type": "integer", "group": "Video"},
            {"key": "bit_depth",       "label": "Bit Depth",       "type": "integer", "group": "Video"},
            {"key": "color_space",     "label": "Color Space",     "type": "string",  "group": "Video"},
            {"key": "hdr_format",      "label": "HDR Format",      "type": "string",  "group": "Video",
             "enum": ["HDR10","HDR10+","Dolby Vision","HLG","SDR"]},
            {"key": "audio_codec",     "label": "Audio Codec",     "type": "string",  "group": "Video"},
            {"key": "audio_channels",  "label": "Audio Channels",  "type": "integer", "group": "Video"},
            {"key": "sample_rate",     "label": "Sample Rate (Hz)","type": "integer", "group": "Video"},
            {"key": "subtitle_languages","label": "Subtitle Langs","type": "string",  "group": "Video"},
            # Image
            {"key": "camera_make",     "label": "Camera Make",     "type": "string",  "group": "Image"},
            {"key": "camera_model",    "label": "Camera Model",    "type": "string",  "group": "Image"},
            {"key": "lens",            "label": "Lens",            "type": "string",  "group": "Image"},
            {"key": "focal_length",    "label": "Focal Length (mm)","type": "float",  "group": "Image"},
            {"key": "aperture",        "label": "Aperture (f/)",   "type": "float",   "group": "Image"},
            {"key": "shutter_speed",   "label": "Shutter Speed",   "type": "string",  "group": "Image"},
            {"key": "iso",             "label": "ISO",             "type": "integer", "group": "Image"},
            {"key": "datetime_original","label": "Date Taken",     "type": "datetime","group": "Image"},
            {"key": "gps_latitude",    "label": "GPS Latitude",    "type": "float",   "group": "Image"},
            {"key": "gps_longitude",   "label": "GPS Longitude",   "type": "float",   "group": "Image"},
            {"key": "gps_altitude",    "label": "GPS Altitude",    "type": "float",   "group": "Image"},
            {"key": "color_profile",   "label": "Color Profile",   "type": "string",  "group": "Image"},
            {"key": "face_count",      "label": "Face Count",      "type": "integer", "group": "Image"},
            # Vision AI
            {"key": "scene_type",      "label": "Scene Type",      "type": "string",  "group": "Vision AI",
             "enum": ["indoor","outdoor","landscape","portrait","document","screenshot","other"]},
            {"key": "objects",         "label": "Objects Detected","type": "string",  "group": "Vision AI"},
            {"key": "people_count",    "label": "People Count",    "type": "integer", "group": "Vision AI"},
            {"key": "text_visible",    "label": "Visible Text",    "type": "string",  "group": "Vision AI"},
            {"key": "dominant_colors", "label": "Dominant Colors", "type": "string",  "group": "Vision AI"},
            {"key": "is_document",     "label": "Is Document Photo","type": "boolean","group": "Vision AI"},
            # Audio tags
            {"key": "artist",          "label": "Artist",          "type": "string",  "group": "Audio"},
            {"key": "album",           "label": "Album",           "type": "string",  "group": "Audio"},
            {"key": "album_artist",    "label": "Album Artist",    "type": "string",  "group": "Audio"},
            {"key": "title",           "label": "Title",           "type": "string",  "group": "Audio"},
            {"key": "year",            "label": "Year",            "type": "integer", "group": "Audio"},
            {"key": "genre",           "label": "Genre",           "type": "string",  "group": "Audio"},
            {"key": "track_number",    "label": "Track #",         "type": "integer", "group": "Audio"},
            {"key": "bpm",             "label": "BPM",             "type": "float",   "group": "Audio"},
            {"key": "musicbrainz_id",  "label": "MusicBrainz ID",  "type": "string",  "group": "Audio"},
            {"key": "acoustid",        "label": "AcoustID",        "type": "string",  "group": "Audio"},
            # Document
            {"key": "author",          "label": "Author",          "type": "string",  "group": "Document"},
            {"key": "page_count",      "label": "Page Count",      "type": "integer", "group": "Document"},
            {"key": "word_count",      "label": "Word Count",      "type": "integer", "group": "Document"},
            {"key": "has_macros",      "label": "Has Macros",      "type": "boolean", "group": "Document"},
            {"key": "is_encrypted",    "label": "Encrypted",       "type": "boolean", "group": "Document"},
            {"key": "is_signed",       "label": "Digitally Signed","type": "boolean", "group": "Document"},
            # Security
            {"key": "pii_detected",    "label": "PII Detected",    "type": "boolean", "group": "Security"},
            {"key": "pii_types",       "label": "PII Types",       "type": "string",  "group": "Security"},
            {"key": "sensitivity_level","label": "Sensitivity",    "type": "string",  "group": "Security",
             "enum": ["low","medium","high","critical"]},
            {"key": "contains_secrets","label": "Contains Secrets","type": "boolean", "group": "Security"},
            {"key": "secret_types",    "label": "Secret Types",    "type": "string",  "group": "Security"},
            # Executable
            {"key": "binary_format",   "label": "Binary Format",   "type": "string",  "group": "Executable",
             "enum": ["PE","ELF","MACHO","DEX"]},
            {"key": "architecture",    "label": "Architecture",    "type": "string",  "group": "Executable"},
            {"key": "product_name",    "label": "Product Name",    "type": "string",  "group": "Executable"},
            {"key": "company_name",    "label": "Company",         "type": "string",  "group": "Executable"},
            {"key": "file_version",    "label": "File Version",    "type": "string",  "group": "Executable"},
            {"key": "signed",          "label": "Signed",          "type": "boolean", "group": "Executable"},
            {"key": "signature_valid", "label": "Signature Valid", "type": "boolean", "group": "Executable"},
            {"key": "is_packed",       "label": "Packed",          "type": "boolean", "group": "Executable"},
            {"key": "entropy",         "label": "Entropy",         "type": "float",   "group": "Executable"},
            {"key": "is_universal",    "label": "Universal Binary","type": "boolean", "group": "Executable"},
            {"key": "architectures",   "label": "Architectures",   "type": "string",  "group": "Executable"},
            {"key": "eol_status",      "label": "EOL Status",      "type": "string",  "group": "Executable",
             "enum": ["supported","eol","lts","unknown"]},
            {"key": "latest_version",  "label": "Latest Version",  "type": "string",  "group": "Executable"},
            {"key": "version_behind",  "label": "Versions Behind", "type": "integer", "group": "Executable"},
            {"key": "cve_count",       "label": "CVE Count",       "type": "integer", "group": "Executable"},
            # Binary AI
            {"key": "risk_assessment", "label": "Risk (AI)",       "type": "string",  "group": "AI",
             "enum": ["low","medium","high"]},
            {"key": "ai_category",     "label": "AI Category",     "type": "string",  "group": "AI"},
            # Archive
            {"key": "compression_method","label": "Compression",   "type": "string",  "group": "Archive"},
            {"key": "compression_ratio","label": "Compression Ratio","type": "float", "group": "Archive"},
            {"key": "file_count_in_archive","label": "Files in Archive","type": "integer","group": "Archive"},
            {"key": "contains_executables","label": "Contains Executables","type": "boolean","group": "Archive"},
            # Certificate (as File)
            {"key": "cert_subject",    "label": "Cert Subject",    "type": "string",  "group": "Certificate"},
            {"key": "cert_issuer",     "label": "Cert Issuer",     "type": "string",  "group": "Certificate"},
            {"key": "cert_valid_from", "label": "Valid From",      "type": "datetime","group": "Certificate"},
            {"key": "cert_valid_to",   "label": "Valid To",        "type": "datetime","group": "Certificate"},
            {"key": "cert_is_expired", "label": "Expired",         "type": "boolean", "group": "Certificate"},
            {"key": "days_until_expiry","label": "Days Until Expiry","type": "integer","group": "Certificate"},
            {"key": "cert_key_algorithm","label": "Key Algorithm", "type": "string",  "group": "Certificate"},
            {"key": "cert_fingerprint","label": "Fingerprint",     "type": "string",  "group": "Certificate"},
            {"key": "is_self_signed",  "label": "Self-Signed",     "type": "boolean", "group": "Certificate"},
            # Code
            {"key": "code_language",   "label": "Language",        "type": "string",  "group": "Code"},
            {"key": "line_count",      "label": "Line Count",      "type": "integer", "group": "Code"},
            {"key": "function_count",  "label": "Function Count",  "type": "integer", "group": "Code"},
            {"key": "framework",       "label": "Framework",       "type": "string",  "group": "Code"},
            {"key": "code_quality",    "label": "Code Quality",    "type": "string",  "group": "Code",
             "enum": ["good","fair","poor"]},
            {"key": "has_tests",       "label": "Has Tests",       "type": "boolean", "group": "Code"},
            {"key": "security_concerns","label": "Security Concerns","type": "string","group": "Code"},
        ],
    },
    {
        "id": "Directory", "label": "Directory", "icon": "📁", "color": "#fbbf24",
        "description": "A directory in the filesystem graph",
        "properties": [
            {"key": "id",         "label": "ID",         "type": "string",  "group": "Identity"},
            {"key": "path",       "label": "Path",       "type": "string",  "group": "Identity"},
            {"key": "name",       "label": "Name",       "type": "string",  "group": "Identity"},
            {"key": "host",       "label": "Host",       "type": "string",  "group": "Identity"},
            {"key": "share",      "label": "Share",      "type": "string",  "group": "Identity"},
            {"key": "file_count", "label": "File Count", "type": "integer", "group": "Stats"},
            {"key": "total_bytes","label": "Total Size", "type": "integer", "group": "Stats"},
        ],
    },
    {
        "id": "Person", "label": "Person", "icon": "👤", "color": "#f472b6",
        "description": "A person identified by face recognition or entity extraction",
        "properties": [
            {"key": "id",             "label": "ID",           "type": "string",  "group": "Identity"},
            {"key": "name",           "label": "Name",         "type": "string",  "group": "Identity"},
            {"key": "known",          "label": "Identified",   "type": "boolean", "group": "Identity"},
            {"key": "face_cluster_id","label": "Face Cluster", "type": "string",  "group": "Identity"},
            {"key": "source",         "label": "Source",       "type": "string",  "group": "Identity",
             "enum": ["face_recognition","entity_extraction","manual"]},
            {"key": "face_count",     "label": "Appearances",  "type": "integer", "group": "Stats"},
            {"key": "first_seen",     "label": "First Seen",   "type": "datetime","group": "Stats"},
            {"key": "last_seen",      "label": "Last Seen",    "type": "datetime","group": "Stats"},
        ],
    },
    {
        "id": "FaceCluster", "label": "Face Cluster", "icon": "👥", "color": "#ec4899",
        "description": "A cluster of face embeddings from InsightFace DBSCAN",
        "properties": [
            {"key": "id",         "label": "ID",         "type": "string",  "group": "Identity"},
            {"key": "label",      "label": "Label",      "type": "string",  "group": "Identity"},
            {"key": "known",      "label": "Identified", "type": "boolean", "group": "Identity"},
            {"key": "face_count", "label": "Appearances","type": "integer", "group": "Stats"},
            {"key": "first_seen", "label": "First Seen", "type": "datetime","group": "Stats"},
            {"key": "last_seen",  "label": "Last Seen",  "type": "datetime","group": "Stats"},
        ],
    },
    {
        "id": "Location", "label": "Location", "icon": "📍", "color": "#34d399",
        "description": "A geographic location from GPS data or entity extraction",
        "properties": [
            {"key": "id",         "label": "ID",         "type": "string", "group": "Identity"},
            {"key": "name",       "label": "Name",       "type": "string", "group": "Identity"},
            {"key": "city",       "label": "City",       "type": "string", "group": "Geography"},
            {"key": "region",     "label": "Region",     "type": "string", "group": "Geography"},
            {"key": "country",    "label": "Country",    "type": "string", "group": "Geography"},
            {"key": "latitude",   "label": "Latitude",   "type": "float",  "group": "Geography"},
            {"key": "longitude",  "label": "Longitude",  "type": "float",  "group": "Geography"},
            {"key": "place_type", "label": "Place Type", "type": "string", "group": "Geography"},
        ],
    },
    {
        "id": "Organization", "label": "Organization", "icon": "🏢", "color": "#fb923c",
        "description": "An organization extracted from document text",
        "properties": [
            {"key": "id",   "label": "ID",   "type": "string", "group": "Identity"},
            {"key": "name", "label": "Name", "type": "string", "group": "Identity"},
            {"key": "type", "label": "Type", "type": "string", "group": "Identity"},
        ],
    },
    {
        "id": "Topic", "label": "Topic", "icon": "🏷️", "color": "#a3e635",
        "description": "A semantic topic extracted by AI",
        "properties": [
            {"key": "id",   "label": "ID",   "type": "string", "group": "Identity"},
            {"key": "name", "label": "Name", "type": "string", "group": "Identity"},
        ],
    },
    {
        "id": "Tag", "label": "Tag", "icon": "🔖", "color": "#6b7280",
        "description": "A user-applied or system tag on a file",
        "properties": [
            {"key": "id",   "label": "ID",   "type": "string", "group": "Identity"},
            {"key": "name", "label": "Name", "type": "string", "group": "Identity"},
        ],
    },
    {
        "id": "Collection", "label": "Collection", "icon": "📚", "color": "#f59e0b",
        "description": "A named grouping of files",
        "properties": [
            {"key": "id",          "label": "ID",          "type": "string", "group": "Identity"},
            {"key": "name",        "label": "Name",        "type": "string", "group": "Identity"},
            {"key": "type",        "label": "Type",        "type": "string", "group": "Identity"},
            {"key": "description", "label": "Description", "type": "string", "group": "Identity"},
        ],
    },
    {
        "id": "Event", "label": "Event", "icon": "🎉", "color": "#fb923c",
        "description": "An event that files are temporally linked to",
        "properties": [
            {"key": "id",         "label": "ID",         "type": "string",  "group": "Identity"},
            {"key": "name",       "label": "Name",       "type": "string",  "group": "Identity"},
            {"key": "start_time", "label": "Start Time", "type": "datetime","group": "Time"},
            {"key": "end_time",   "label": "End Time",   "type": "datetime","group": "Time"},
        ],
    },
    {
        "id": "MediaItem", "label": "Media Item", "icon": "🎞️", "color": "#818cf8",
        "description": "A movie, TV show, or album from TMDB/IMDB",
        "properties": [
            {"key": "id",        "label": "ID",       "type": "string",  "group": "Identity"},
            {"key": "title",     "label": "Title",    "type": "string",  "group": "Identity"},
            {"key": "type",      "label": "Type",     "type": "string",  "group": "Identity",
             "enum": ["movie","tv","album","other"]},
            {"key": "year",      "label": "Year",     "type": "integer", "group": "Metadata"},
            {"key": "tmdb_id",   "label": "TMDB ID",  "type": "string",  "group": "Metadata"},
            {"key": "imdb_id",   "label": "IMDB ID",  "type": "string",  "group": "Metadata"},
            {"key": "genre",     "label": "Genre",    "type": "string",  "group": "Metadata"},
            {"key": "director",  "label": "Director", "type": "string",  "group": "Metadata"},
            {"key": "rating",    "label": "Rating",   "type": "float",   "group": "Metadata"},
            {"key": "overview",  "label": "Overview", "type": "string",  "group": "Metadata"},
        ],
    },
    {
        "id": "Application", "label": "Application", "icon": "🖥️", "color": "#8b5cf6",
        "description": "An installed application tracked by archon",
        "properties": [
            {"key": "id",                 "label": "ID",               "type": "string",  "group": "Identity"},
            {"key": "name",               "label": "Name",             "type": "string",  "group": "Identity"},
            {"key": "version_string",     "label": "Version",          "type": "string",  "group": "Version"},
            {"key": "architecture",       "label": "Architecture",     "type": "string",  "group": "Version"},
            {"key": "eol_status",         "label": "EOL Status",       "type": "string",  "group": "Lifecycle",
             "enum": ["supported","eol","lts","unknown"]},
            {"key": "eol_date",           "label": "EOL Date",         "type": "datetime","group": "Lifecycle"},
            {"key": "latest_version",     "label": "Latest Version",   "type": "string",  "group": "Lifecycle"},
            {"key": "version_behind",     "label": "Versions Behind",  "type": "integer", "group": "Lifecycle"},
            {"key": "update_available",   "label": "Update Available", "type": "boolean", "group": "Lifecycle"},
            {"key": "cve_count",          "label": "CVE Count",        "type": "integer", "group": "Security"},
            {"key": "critical_cve_count", "label": "Critical CVEs",    "type": "integer", "group": "Security"},
            {"key": "signed",             "label": "Signed",           "type": "boolean", "group": "Security"},
            {"key": "install_date",       "label": "Install Date",     "type": "datetime","group": "Usage"},
            {"key": "last_run",           "label": "Last Run",         "type": "datetime","group": "Usage"},
        ],
    },
    {
        "id": "Vulnerability", "label": "Vulnerability", "icon": "🛡️", "color": "#f87171",
        "description": "A CVE from NVD, OSV, or OSS-Index",
        "properties": [
            {"key": "id",                 "label": "ID",                "type": "string",  "group": "Identity"},
            {"key": "cve_id",             "label": "CVE ID",            "type": "string",  "group": "Identity"},
            {"key": "cvss_score",         "label": "CVSS Score",        "type": "float",   "group": "Severity"},
            {"key": "cvss_severity",      "label": "Severity",          "type": "string",  "group": "Severity",
             "enum": ["critical","high","medium","low","none"]},
            {"key": "exploit_available",  "label": "Exploit Available", "type": "boolean", "group": "Risk"},
            {"key": "actively_exploited", "label": "Actively Exploited","type": "boolean", "group": "Risk"},
            {"key": "description",        "label": "Description",       "type": "string",  "group": "Detail"},
            {"key": "published_date",     "label": "Published",         "type": "datetime","group": "Detail"},
            {"key": "patched_in_version", "label": "Patched In",        "type": "string",  "group": "Detail"},
        ],
    },
    {
        "id": "Certificate", "label": "Certificate", "icon": "🏅", "color": "#4ade80",
        "description": "A TLS, code-signing, or CA certificate node",
        "properties": [
            {"key": "id",               "label": "ID",            "type": "string",  "group": "Identity"},
            {"key": "subject",          "label": "Subject",       "type": "string",  "group": "Identity"},
            {"key": "issuer",           "label": "Issuer",        "type": "string",  "group": "Identity"},
            {"key": "serial",           "label": "Serial",        "type": "string",  "group": "Identity"},
            {"key": "valid_from",       "label": "Valid From",    "type": "datetime","group": "Validity"},
            {"key": "valid_to",         "label": "Valid To",      "type": "datetime","group": "Validity"},
            {"key": "is_expired",       "label": "Expired",       "type": "boolean", "group": "Validity"},
            {"key": "days_until_expiry","label": "Days Left",     "type": "integer", "group": "Validity"},
            {"key": "key_algorithm",    "label": "Key Algorithm", "type": "string",  "group": "Crypto"},
            {"key": "key_size",         "label": "Key Size (bits)","type": "integer","group": "Crypto"},
            {"key": "fingerprint",      "label": "Fingerprint",   "type": "string",  "group": "Crypto"},
            {"key": "is_ca",            "label": "Is CA",         "type": "boolean", "group": "Type"},
            {"key": "is_self_signed",   "label": "Self-Signed",   "type": "boolean", "group": "Type"},
        ],
    },
    {
        "id": "Dependency", "label": "Dependency", "icon": "🧩", "color": "#67e8f9",
        "description": "A software package dependency",
        "properties": [
            {"key": "id",      "label": "ID",      "type": "string", "group": "Identity"},
            {"key": "name",    "label": "Name",    "type": "string", "group": "Identity"},
            {"key": "version", "label": "Version", "type": "string", "group": "Identity"},
        ],
    },
    {
        "id": "License", "label": "License", "icon": "📜", "color": "#6ee7b7",
        "description": "A software license (SPDX)",
        "properties": [
            {"key": "id",   "label": "ID",       "type": "string", "group": "Identity"},
            {"key": "name", "label": "Name",     "type": "string", "group": "Identity"},
            {"key": "spdx", "label": "SPDX ID",  "type": "string", "group": "Identity"},
            {"key": "type", "label": "Type",     "type": "string", "group": "Identity",
             "enum": ["permissive","copyleft","weak-copyleft","proprietary","unknown"]},
        ],
    },
    {
        "id": "Vendor", "label": "Vendor", "icon": "🏭", "color": "#a78bfa",
        "description": "A software vendor",
        "properties": [
            {"key": "id",      "label": "ID",      "type": "string", "group": "Identity"},
            {"key": "name",    "label": "Name",    "type": "string", "group": "Identity"},
            {"key": "website", "label": "Website", "type": "string", "group": "Identity"},
        ],
    },
]

RELATIONSHIP_TYPES: list[dict[str, Any]] = [
    # Filesystem
    {"id": "CHILD_OF",        "label": "Child Of",           "group": "Filesystem", "from": ["File","Directory"], "to": ["Directory"], "directed": True,
     "description": "File or directory is contained within a directory"},
    {"id": "DUPLICATE_OF",    "label": "Duplicate Of",       "group": "Filesystem", "from": ["File"], "to": ["File"], "directed": True,
     "properties": [], "description": "Files share identical SHA-256 hash"},
    {"id": "SIMILAR_TO",      "label": "Similar To",         "group": "Filesystem", "from": ["File"], "to": ["File"], "directed": False,
     "properties": [{"key": "score", "label": "Similarity Score", "type": "float"}],
     "description": "AI-inferred semantic similarity between files"},
    {"id": "PART_OF",         "label": "Part Of",            "group": "Filesystem", "from": ["File","Application"], "to": ["Collection","Product"], "directed": True,
     "description": "File belongs to a collection; application is part of a product"},
    {"id": "REFERENCES",      "label": "References",         "group": "Filesystem", "from": ["File"], "to": ["File"], "directed": True,
     "description": "AI-inferred reference from one file to another"},
    # Semantic
    {"id": "MENTIONS",        "label": "Mentions",           "group": "Semantic", "from": ["File"], "to": ["Person","Organization","Topic","Location"], "directed": True,
     "description": "Entity extracted from document text by AI"},
    {"id": "TAGGED_WITH",     "label": "Tagged With",        "group": "Semantic", "from": ["File"], "to": ["Tag"], "directed": True,
     "description": "User-applied or system-generated tag"},
    {"id": "LOCATED_AT",      "label": "Located At",         "group": "Semantic", "from": ["File"], "to": ["Location"], "directed": True,
     "description": "File's GPS coordinates resolved to a Location node"},
    {"id": "OCCURRED_DURING", "label": "Occurred During",    "group": "Semantic", "from": ["File"], "to": ["Event"], "directed": True,
     "description": "File's timestamp falls within an Event window"},
    # Visual
    {"id": "DEPICTS",         "label": "Depicts",            "group": "Visual", "from": ["File"], "to": ["Person","Location"], "directed": True,
     "description": "Image or video visually depicts a person or place"},
    {"id": "CONTAINS_FACE",   "label": "Contains Face",      "group": "Visual", "from": ["File"], "to": ["FaceCluster"], "directed": True,
     "properties": [{"key": "frame_offset", "label": "Frame Offset (s)", "type": "float"}, {"key": "confidence", "label": "Confidence", "type": "float"}],
     "description": "Image or video contains a detected face belonging to a cluster"},
    # Media
    {"id": "MATCHED_TO",      "label": "Matched To",         "group": "Media", "from": ["File"], "to": ["MediaItem"], "directed": True,
     "properties": [{"key": "confidence", "label": "Confidence", "type": "float"}],
     "description": "Video/audio matched to a TMDB/IMDB/MusicBrainz entry"},
    # Software
    {"id": "IS_APPLICATION",  "label": "Is Application",     "group": "Software", "from": ["File"], "to": ["Application"], "directed": True,
     "description": "Executable file is an instance of an Application"},
    {"id": "IS_BINARY",       "label": "Is Binary",          "group": "Software", "from": ["File"], "to": ["Binary"], "directed": True,
     "description": "File is a parsed binary (PE/ELF/Mach-O)"},
    {"id": "MADE_BY",         "label": "Made By",            "group": "Software", "from": ["Application"], "to": ["Vendor"], "directed": True,
     "description": "Application was made by this vendor"},
    {"id": "IS_VERSION_OF",   "label": "Is Version Of",      "group": "Software", "from": ["Application"], "to": ["Product"], "directed": True,
     "description": "Application is a specific version of a product"},
    {"id": "DEPENDS_ON",      "label": "Depends On",         "group": "Software", "from": ["Application","Binary"], "to": ["Dependency"], "directed": True,
     "description": "Application or binary has a software dependency"},
    {"id": "LICENSED_UNDER",  "label": "Licensed Under",     "group": "Software", "from": ["Application","File"], "to": ["License"], "directed": True,
     "description": "Software is distributed under this license"},
    {"id": "HAS_VULNERABILITY","label": "Has Vulnerability",  "group": "Software", "from": ["Application","Dependency"], "to": ["Vulnerability"], "directed": True,
     "description": "Application or dependency has a known CVE"},
    {"id": "SIGNED_BY",       "label": "Signed By",          "group": "Software", "from": ["Application","Binary"], "to": ["Certificate"], "directed": True,
     "description": "Binary is code-signed with this certificate"},
    {"id": "OWNS",            "label": "Owns",               "group": "Software", "from": ["Vendor"], "to": ["Product"], "directed": True,
     "description": "Vendor owns this product"},
    {"id": "HAS_VERSION",     "label": "Has Version",        "group": "Software", "from": ["Product"], "to": ["Version"], "directed": True,
     "description": "Product has this release version"},
    {"id": "SUPERSEDES",      "label": "Supersedes",         "group": "Software", "from": ["Version"], "to": ["Version"], "directed": True,
     "description": "This version supersedes an older version"},
    # Geography
    {"id": "WITHIN",          "label": "Within",             "group": "Geography", "from": ["Location"], "to": ["Location"], "directed": True,
     "description": "Location is geographically contained within a larger area"},
    # Face/People
    {"id": "SAME_PERSON_AS",  "label": "Same Person As",     "group": "Identity", "from": ["FaceCluster"], "to": ["Person"], "directed": True,
     "properties": [{"key": "confidence", "label": "Confidence", "type": "float"}],
     "description": "Face cluster has been identified as this person"},
]


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("")
async def get_schema(
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    """Full ontology: node types, relationship types, property definitions."""
    return {
        "node_types":         NODE_TYPES,
        "relationship_types": RELATIONSHIP_TYPES,
        "total_node_types":   len(NODE_TYPES),
        "total_rel_types":    len(RELATIONSHIP_TYPES),
    }


@router.get("/node-types")
async def list_node_types(
    auth: AuthContext = Depends(get_auth_context),
) -> list[dict[str, Any]]:
    """Lightweight node type list for palette rendering."""
    return [
        {"id": n["id"], "label": n["label"], "icon": n["icon"], "color": n["color"], "description": n["description"]}
        for n in NODE_TYPES
    ]


@router.get("/properties/{node_type}")
async def get_node_properties(
    node_type: str,
    live:  bool = Query(default=False, description="Sample live graph for additional properties"),
    auth:  AuthContext = Depends(get_auth_context),
    db:    AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Property definitions for a node type.
    With ?live=true, also samples the live graph to detect any extra properties
    not in the static schema (e.g., custom enricher outputs).
    """
    static = next((n for n in NODE_TYPES if n["id"] == node_type), None)
    if not static:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown node type: {node_type}")

    props = list(static.get("properties", []))

    if live:
        from sqlalchemy import select
        from src.dgraphai.db.models import Tenant
        from src.dgraphai.graph.backends.factory import get_backend_for_tenant

        result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
        tenant = result.scalar_one_or_none()
        if tenant:
            backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})
            try:
                async with backend:
                    rows = await backend.query(
                        f"MATCH (n:{node_type}) WHERE n.tenant_id = $tid RETURN n LIMIT 20",
                        {"tid": str(auth.tenant_id)}, auth.tenant_id
                    )
                    live_keys: set[str] = set()
                    for row in rows:
                        n = row.get("n") or next(iter(row.values()), {})
                        if isinstance(n, dict):
                            live_keys.update(n.keys())

                    static_keys = {p["key"] for p in props}
                    for k in sorted(live_keys - static_keys - {"tenant_id"}):
                        props.append({"key": k, "label": k.replace("_", " ").title(), "type": "string", "group": "Other", "live_only": True})
            except Exception:
                pass

    return {
        "node_type":  node_type,
        "properties": props,
        "groups":     _group_props(props),
    }


@router.get("/relationships")
async def list_relationship_types(
    from_type: str | None = Query(default=None),
    to_type:   str | None = Query(default=None),
    auth:      AuthContext = Depends(get_auth_context),
) -> list[dict[str, Any]]:
    """
    List relationship types, optionally filtered by from/to node type.
    Used by the query builder to populate relationship dropdowns
    when two nodes are selected.
    """
    rels = RELATIONSHIP_TYPES
    if from_type:
        rels = [r for r in rels if from_type in r.get("from", [])]
    if to_type:
        rels = [r for r in rels if to_type in r.get("to", [])]
    return rels


@router.get("/stats")
async def schema_stats(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Live node count per type — used by the query builder node palette
    to show how many nodes of each type exist in this tenant's graph.
    """
    from sqlalchemy import select
    from src.dgraphai.db.models import Tenant
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant
    import asyncio

    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return {}

    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})

    async def count_type(nt: str) -> tuple[str, int | None]:
        try:
            async with backend:
                rows = await backend.query(
                    f"MATCH (n:{nt}) WHERE n.tenant_id = $tid RETURN count(n) AS c",
                    {"tid": str(auth.tenant_id)}, auth.tenant_id
                )
                return nt, rows[0]["c"] if rows else 0
        except Exception:
            return nt, None

    counts = await asyncio.gather(*[count_type(n["id"]) for n in NODE_TYPES])
    return {nt: cnt for nt, cnt in counts}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _group_props(props: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for p in props:
        out.setdefault(p.get("group", "Other"), []).append(p)
    return out
