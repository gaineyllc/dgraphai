"""
Complete Data Inventory taxonomy.

Covers every file category, subtype, and attribute that archon indexes —
including raw metadata extraction (ffprobe, ExifRead, lief, cryptography)
and all AI-derived attributes from local Ollama enrichment:
  - LLM: summary, document_type, sentiment, language, entities, topics,
         organizations, locations, action_items
  - Vision (LLaVA): scene_type, objects, people_count, text_visible,
                    dominant_colors, is_document
  - Code (qwen2.5-coder): framework, code_quality, has_tests, security_concerns
  - Binary (deepseek-r1): risk_assessment, category
  - Face (InsightFace): face_count, face_cluster_ids, known_people
  - Secrets: secret_types, contains_secrets
  - PII: pii_types, sensitivity_level
  - Relationships: inferred by reasoning model
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Column:
    key:   str
    label: str
    width: int  = 160
    kind:  str  = "text"   # text | size | date | badge | bool | path | num | mono


@dataclass
class Category:
    id:            str
    name:          str
    description:   str
    group:         str
    icon:          str
    color:         str
    cypher:        str
    columns:       list[Column] = field(default_factory=list)
    subcategories: list["Category"] = field(default_factory=list)
    tags:          list[str]    = field(default_factory=list)
    parent_id:     str | None   = None


# ── Shared column sets ─────────────────────────────────────────────────────────

def _base() -> list[Column]:
    return [
        Column("name",             "Name",        220, "text"),
        Column("path",             "Path",        300, "path"),
        Column("size",             "Size",         80, "size"),
        Column("modified_at",      "Modified",    130, "date"),
        Column("source_connector", "Source",      120, "badge"),
    ]

def _ai_cols() -> list[Column]:
    return [
        Column("summary",          "AI Summary",  260, "text"),
        Column("sentiment",        "Sentiment",    90, "badge"),
        Column("language",         "Language",     80, "badge"),
    ]

def _pii_cols() -> list[Column]:
    return [
        Column("pii_detected",     "PII",          60, "bool"),
        Column("pii_types",        "PII Types",   140, "text"),
        Column("sensitivity_level","Sensitivity", 110, "badge"),
    ]

def _secrets_cols() -> list[Column]:
    return [
        Column("contains_secrets", "Has Secrets",  90, "bool"),
        Column("secret_types",     "Secret Types",130, "text"),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY
# ══════════════════════════════════════════════════════════════════════════════

INVENTORY: list[Category] = [

    # ══ VIDEO ══════════════════════════════════════════════════════════════════
    Category(
        id          = "video",
        name        = "Video",
        description = "All video files — movies, TV, recordings, clips",
        group       = "Media",
        icon        = "🎬",
        color       = "#4f8ef7",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'video' AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [
            Column("video_codec",    "Codec",        80, "badge"),
            Column("width",          "W",            55, "num"),
            Column("height",         "H",            55, "num"),
            Column("duration_secs",  "Duration",     90, "num"),
            Column("hdr_format",     "HDR",          80, "badge"),
            Column("container_format","Container",  110, "badge"),
        ],
        tags        = ["media","video"],
        subcategories = [

            Category(
                id          = "video-4k",
                name        = "4K / UHD",
                description = "2160p video files",
                group       = "Media",
                icon        = "📺",
                color       = "#818cf8",
                parent_id   = "video",
                cypher      = "MATCH (f:File) WHERE f.file_category = 'video' AND f.height >= 2160 AND f.tenant_id = $tid RETURN f",
                columns     = _base() + [
                    Column("video_codec",   "Codec",       80, "badge"),
                    Column("hdr_format",    "HDR",         80, "badge"),
                    Column("audio_codec",   "Audio",       80, "badge"),
                    Column("duration_secs", "Duration",    90, "num"),
                    Column("overall_bitrate","Bitrate",    90, "num"),
                ],
                tags        = ["video","4k","uhd"],
                subcategories = [
                    Category(
                        id="video-4k-hdr", name="4K + HDR",
                        description="4K files with HDR or Dolby Vision",
                        group="Media", icon="✨", color="#6366f1", parent_id="video-4k",
                        cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.height >= 2160 AND f.hdr_format IS NOT NULL AND f.tenant_id = $tid RETURN f",
                        columns=_base() + [Column("hdr_format","HDR",90,"badge"), Column("video_codec","Codec",80,"badge"), Column("duration_secs","Duration",90,"num")],
                        tags=["video","4k","hdr"],
                    ),
                    Category(
                        id="video-4k-av1", name="4K AV1",
                        description="4K files encoded in AV1",
                        group="Media", icon="⚡", color="#7c3aed", parent_id="video-4k",
                        cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.height >= 2160 AND f.video_codec = 'av1' AND f.tenant_id = $tid RETURN f",
                        columns=_base() + [Column("hdr_format","HDR",90,"badge"), Column("overall_bitrate","Bitrate",90,"num")],
                        tags=["video","4k","av1"],
                    ),
                ],
            ),

            Category(
                id="video-1080p", name="1080p HD",
                description="1080p full HD video",
                group="Media", icon="🖥️", color="#60a5fa", parent_id="video",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.height = 1080 AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("video_codec","Codec",80,"badge"), Column("hdr_format","HDR",80,"badge"), Column("duration_secs","Duration",90,"num")],
                tags=["video","1080p"],
            ),

            Category(
                id="video-hdr", name="HDR / Dolby Vision",
                description="Any video with HDR metadata",
                group="Media", icon="🌟", color="#a78bfa", parent_id="video",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.hdr_format IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("hdr_format","HDR Format",100,"badge"), Column("height","Res",60,"num"), Column("video_codec","Codec",80,"badge")],
                tags=["video","hdr"],
            ),

            Category(
                id="video-long", name="Long-form (>1h)",
                description="Videos over one hour — likely movies or TV",
                group="Media", icon="🎥", color="#3b82f6", parent_id="video",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.duration_secs > 3600 AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("duration_secs","Duration (s)",100,"num"), Column("height","Res",60,"num"), Column("hdr_format","HDR",80,"badge")],
                tags=["video","movies"],
            ),

            Category(
                id="video-ai-summarized", name="AI Summarized",
                description="Videos analyzed by LLM enricher",
                group="Media", icon="🤖", color="#4f8ef7", parent_id="video",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.summary IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + _ai_cols() + [Column("height","Res",60,"num")],
                tags=["video","ai"],
            ),
        ],
    ),

    # ══ AUDIO ══════════════════════════════════════════════════════════════════
    Category(
        id          = "audio",
        name        = "Audio",
        description = "Music, podcasts, audiobooks, and recordings",
        group       = "Media",
        icon        = "🎵",
        color       = "#a78bfa",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'audio' AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [
            Column("artist",        "Artist",    140, "text"),
            Column("album",         "Album",     140, "text"),
            Column("audio_codec",   "Codec",      80, "badge"),
            Column("duration_secs", "Duration",   90, "num"),
            Column("overall_bitrate","Bitrate",   90, "num"),
            Column("sample_rate",   "Sample Rate",90, "num"),
        ],
        tags        = ["media","audio"],
        subcategories = [
            Category(
                id="audio-lossless", name="Lossless",
                description="FLAC, WAV, ALAC, DSD lossless audio",
                group="Media", icon="💎", color="#8b5cf6", parent_id="audio",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.audio_codec IN ['flac','pcm_s16le','pcm_s24le','pcm_s32le','alac','dsf','dff'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("artist","Artist",140,"text"), Column("album","Album",140,"text"), Column("bit_depth","Bit Depth",80,"num"), Column("sample_rate","Sample Rate",90,"num")],
                tags=["audio","lossless","hifi"],
            ),
            Category(
                id="audio-tagged", name="Fully Tagged",
                description="Audio files with complete metadata tags",
                group="Media", icon="🏷️", color="#7c3aed", parent_id="audio",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.artist IS NOT NULL AND f.album IS NOT NULL AND f.title IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("artist","Artist",130,"text"), Column("album","Album",130,"text"), Column("title","Title",160,"text"), Column("year","Year",60,"num"), Column("genre","Genre",90,"badge")],
                tags=["audio","metadata"],
            ),
            Category(
                id="audio-untagged", name="Untagged",
                description="Audio files missing artist, album, or title",
                group="Media", icon="❓", color="#6b7280", parent_id="audio",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND (f.artist IS NULL OR f.album IS NULL) AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("audio_codec","Codec",80,"badge"), Column("duration_secs","Duration",90,"num")],
                tags=["audio","cleanup"],
            ),
            Category(
                id="audio-hires", name="Hi-Res (96kHz+)",
                description="High resolution audio at 96kHz or above",
                group="Media", icon="🎧", color="#c084fc", parent_id="audio",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.sample_rate >= 96000 AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("sample_rate","Sample Rate",90,"num"), Column("bit_depth","Bit Depth",80,"num"), Column("audio_codec","Codec",80,"badge")],
                tags=["audio","hires","hifi"],
            ),
        ],
    ),

    # ══ IMAGES ════════════════════════════════════════════════════════════════
    Category(
        id          = "images",
        name        = "Images & Photos",
        description = "Photos, screenshots, RAW files, and illustrations",
        group       = "Media",
        icon        = "🖼️",
        color       = "#34d399",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'image' AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [
            Column("width",          "W",          55, "num"),
            Column("height",         "H",          55, "num"),
            Column("camera_model",   "Camera",    130, "text"),
            Column("datetime_original","Taken",   130, "date"),
            Column("gps_latitude",   "Lat",        70, "num"),
            Column("gps_longitude",  "Lon",        70, "num"),
        ],
        tags        = ["media","images"],
        subcategories = [

            Category(
                id="images-with-faces", name="Contains Faces",
                description="Photos with one or more detected faces",
                group="Media", icon="👤", color="#f472b6", parent_id="images",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.face_count > 0 AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("face_count","Faces",60,"num"), Column("camera_model","Camera",130,"text"), Column("datetime_original","Taken",130,"date")],
                tags=["images","people","faces"],
                subcategories=[
                    Category(
                        id="images-identified-people", name="Identified People",
                        description="Photos where at least one face is identified",
                        group="Media", icon="✅", color="#ec4899", parent_id="images-with-faces",
                        cypher="MATCH (f:File)-[:CONTAINS_FACE]->(fc:FaceCluster)<-[:BELONGS_TO]-(p:Person) WHERE p.known = true AND f.tenant_id = $tid RETURN DISTINCT f",
                        columns=_base() + [Column("face_count","Faces",60,"num"), Column("datetime_original","Taken",130,"date")],
                        tags=["images","people","identified"],
                    ),
                    Category(
                        id="images-group-shots", name="Group Photos",
                        description="Photos with 3 or more people",
                        group="Media", icon="👥", color="#db2777", parent_id="images-with-faces",
                        cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.face_count >= 3 AND f.tenant_id = $tid RETURN f",
                        columns=_base() + [Column("face_count","Faces",60,"num"), Column("datetime_original","Taken",130,"date"), Column("gps_latitude","Lat",70,"num")],
                        tags=["images","people","group"],
                    ),
                ],
            ),

            Category(
                id="images-geotagged", name="Geotagged",
                description="Photos with GPS coordinates in EXIF",
                group="Media", icon="📍", color="#10b981", parent_id="images",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.gps_latitude IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("gps_latitude","Latitude",90,"num"), Column("gps_longitude","Longitude",90,"num"), Column("camera_model","Camera",130,"text"), Column("datetime_original","Taken",130,"date")],
                tags=["images","location","gps"],
            ),

            Category(
                id="images-raw", name="RAW / HEIF",
                description="RAW camera files (CR2, NEF, ARW) and HEIF/HEIC",
                group="Media", icon="📷", color="#059669", parent_id="images",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.mime_type IN ['image/x-raw','image/heif','image/heic','image/x-canon-cr2','image/x-nikon-nef','image/x-sony-arw'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("camera_make","Make",90,"text"), Column("camera_model","Camera",130,"text"), Column("focal_length","Focal",70,"num"), Column("iso","ISO",60,"num")],
                tags=["images","raw","camera"],
            ),

            Category(
                id="images-ai-analyzed", name="AI Vision Analyzed",
                description="Images processed by LLaVA vision model",
                group="Media", icon="🤖", color="#34d399", parent_id="images",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.summary IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [
                    Column("summary",      "AI Description",220,"text"),
                    Column("scene_type",   "Scene",          90,"badge"),
                    Column("mood",         "Mood",           90,"badge"),
                    Column("people_count", "People",         60,"num"),
                    Column("text_visible", "Text in Image", 140,"text"),
                ],
                tags=["images","ai","vision"],
            ),

            Category(
                id="images-screenshots", name="Screenshots",
                description="Screen captures identified by AI vision",
                group="Media", icon="🖥️", color="#14b8a6", parent_id="images",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.scene_type = 'screenshot' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("text_visible","Visible Text",200,"text"), Column("width","W",55,"num"), Column("height","H",55,"num")],
                tags=["images","screenshots"],
            ),
        ],
    ),

    # ══ DOCUMENTS ═════════════════════════════════════════════════════════════
    Category(
        id          = "documents",
        name        = "Documents",
        description = "PDFs, Office files, text docs, spreadsheets, emails",
        group       = "Documents & Text",
        icon        = "📄",
        color       = "#fbbf24",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'document' AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [
            Column("document_type",  "Type",        90, "badge"),
            Column("author",         "Author",      130, "text"),
            Column("page_count",     "Pages",        65, "num"),
            Column("language",       "Language",     80, "badge"),
            Column("summary",        "AI Summary",  220, "text"),
        ],
        tags        = ["documents"],
        subcategories = [

            Category(
                id="docs-pdf", name="PDF",
                description="PDF documents",
                group="Documents & Text", icon="📕", color="#f59e0b", parent_id="documents",
                cypher="MATCH (f:File) WHERE f.mime_type = 'application/pdf' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","Author",130,"text"), Column("page_count","Pages",65,"num"), Column("is_encrypted","Encrypted",80,"bool"), Column("word_count","Words",75,"num"), Column("summary","AI Summary",220,"text")],
                tags=["documents","pdf"],
            ),

            Category(
                id="docs-office", name="Office Docs",
                description="Word, Excel, PowerPoint files",
                group="Documents & Text", icon="💼", color="#f97316", parent_id="documents",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.mime_type IN ['application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/msword','application/vnd.ms-excel','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/vnd.ms-powerpoint','application/vnd.openxmlformats-officedocument.presentationml.presentation'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","Author",130,"text"), Column("title","Title",180,"text"), Column("word_count","Words",75,"num"), Column("summary","AI Summary",220,"text")],
                tags=["documents","office"],
            ),

            Category(
                id="docs-contracts", name="Contracts",
                description="AI-classified contract documents",
                group="Documents & Text", icon="📝", color="#d97706", parent_id="documents",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.document_type = 'contract' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","Author",130,"text"), Column("page_count","Pages",65,"num"), Column("entities_people","People",160,"text"), Column("summary","AI Summary",220,"text")],
                tags=["documents","contracts","legal","ai"],
            ),

            Category(
                id="docs-invoices", name="Invoices",
                description="AI-classified invoice documents",
                group="Documents & Text", icon="🧾", color="#b45309", parent_id="documents",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.document_type = 'invoice' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","Author",130,"text"), Column("entities_organizations","Organizations",180,"text"), Column("summary","AI Summary",220,"text")],
                tags=["documents","invoices","financial","ai"],
            ),

            Category(
                id="docs-reports", name="Reports",
                description="AI-classified report documents",
                group="Documents & Text", icon="📊", color="#92400e", parent_id="documents",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.document_type = 'report' AND f.tenant_id = $tid RETURN f",
                columns=_base() + _ai_cols() + [Column("page_count","Pages",65,"num"), Column("entities_topics","Topics",200,"text")],
                tags=["documents","reports","ai"],
            ),

            Category(
                id="docs-pii", name="Contains PII",
                description="Documents with detected personal data",
                group="Documents & Text", icon="🔒", color="#ef4444", parent_id="documents",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.pii_detected = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + _pii_cols() + [Column("document_type","Type",90,"badge"), Column("page_count","Pages",65,"num")],
                tags=["documents","pii","compliance"],
                subcategories=[
                    Category(
                        id="docs-pii-high", name="High Sensitivity PII",
                        description="Documents with high-sensitivity personal data",
                        group="Documents & Text", icon="🔴", color="#dc2626", parent_id="docs-pii",
                        cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.pii_detected = true AND f.sensitivity_level = 'high' AND f.tenant_id = $tid RETURN f",
                        columns=_base() + _pii_cols() + [Column("document_type","Type",90,"badge"), Column("summary","AI Summary",220,"text")],
                        tags=["documents","pii","compliance","high-sensitivity"],
                    ),
                ],
            ),

            Category(
                id="docs-multilingual", name="Non-English",
                description="Documents in languages other than English",
                group="Documents & Text", icon="🌐", color="#fbbf24", parent_id="documents",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.language IS NOT NULL AND f.language <> 'en' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("language","Language",80,"badge"), Column("document_type","Type",90,"badge"), Column("summary","AI Summary",220,"text")],
                tags=["documents","multilingual","ai"],
            ),
        ],
    ),

    # ══ EMAIL ════════════════════════════════════════════════════════════════
    Category(
        id          = "emails",
        name        = "Email",
        description = ".eml, .msg, and .mbox email files",
        group       = "Documents & Text",
        icon        = "✉️",
        color       = "#38bdf8",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'email' AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [
            Column("author",     "From",   140, "text"),
            Column("title",      "Subject",200, "text"),
            Column("summary",    "AI Summary",220,"text"),
            Column("sentiment",  "Sentiment",90,"badge"),
            Column("pii_detected","PII",   60, "bool"),
        ],
        tags        = ["email","documents"],
        subcategories=[
            Category(
                id="emails-with-pii", name="Contains PII",
                description="Emails with detected personal data",
                group="Documents & Text", icon="🔒", color="#0ea5e9", parent_id="emails",
                cypher="MATCH (f:File) WHERE f.file_category = 'email' AND f.pii_detected = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + _pii_cols() + [Column("title","Subject",200,"text"), Column("summary","AI Summary",220,"text")],
                tags=["email","pii","compliance"],
            ),
            Category(
                id="emails-action-items", name="Has Action Items",
                description="Emails where AI detected tasks or action items",
                group="Documents & Text", icon="✅", color="#0284c7", parent_id="emails",
                cypher="MATCH (f:File) WHERE f.file_category = 'email' AND f.action_items IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("title","Subject",200,"text"), Column("action_items","Action Items",260,"text"), Column("sentiment","Sentiment",90,"badge")],
                tags=["email","ai","actions"],
            ),
        ],
    ),

    # ══ SOURCE CODE ════════════════════════════════════════════════════════════
    Category(
        id          = "code",
        name        = "Source Code",
        description = "Programming files, scripts, and configuration",
        group       = "Code & Config",
        icon        = "💻",
        color       = "#22d3ee",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'code' AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [
            Column("code_language",  "Language",  100, "badge"),
            Column("line_count",     "Lines",      70, "num"),
            Column("function_count", "Functions",  80, "num"),
            Column("contains_secrets","Secrets",   80, "bool"),
            Column("summary",        "AI Summary",200, "text"),
        ],
        tags        = ["code"],
        subcategories = [

            Category(
                id="code-secrets", name="Contains Secrets",
                description="Source files with hardcoded credentials, keys, or tokens",
                group="Code & Config", icon="🔑", color="#f87171", parent_id="code",
                cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.contains_secrets = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + _secrets_cols() + [Column("code_language","Language",100,"badge"), Column("line_count","Lines",70,"num")],
                tags=["code","security","secrets"],
            ),

            Category(
                id="code-security-concerns", name="Security Issues",
                description="Code with AI-detected security concerns",
                group="Code & Config", icon="⚠️", color="#fb923c", parent_id="code",
                cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.security_concerns IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("code_language","Language",100,"badge"), Column("security_concerns","Issues",240,"text"), Column("code_quality","Quality",90,"badge")],
                tags=["code","security","ai"],
            ),

            Category(
                id="code-poor-quality", name="Poor Quality",
                description="Code rated poor quality by AI analysis",
                group="Code & Config", icon="💢", color="#f59e0b", parent_id="code",
                cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.code_quality = 'poor' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("code_language","Language",100,"badge"), Column("line_count","Lines",70,"num"), Column("summary","AI Summary",200,"text")],
                tags=["code","quality","ai"],
            ),

            Category(
                id="code-config", name="Config Files",
                description=".env, YAML, TOML, JSON, INI configuration files",
                group="Code & Config", icon="⚙️", color="#06b6d4", parent_id="code",
                cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.code_language IN ['env','YAML','TOML','JSON','INI'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("code_language","Format",90,"badge"), Column("contains_secrets","Secrets",80,"bool"), Column("line_count","Lines",70,"num")],
                tags=["code","config"],
            ),

            Category(
                id="code-tests", name="Test Files",
                description="Code identified as unit tests or test suites",
                group="Code & Config", icon="🧪", color="#2dd4bf", parent_id="code",
                cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.has_tests = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("code_language","Language",100,"badge"), Column("framework","Framework",110,"badge"), Column("line_count","Lines",70,"num")],
                tags=["code","tests"],
            ),
        ],
    ),

    # ══ EXECUTABLES ═══════════════════════════════════════════════════════════
    Category(
        id          = "executables",
        name        = "Executables & Libraries",
        description = "PE, ELF, Mach-O binaries and libraries",
        group       = "Software",
        icon        = "⚙️",
        color       = "#8b5cf6",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'executable' AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [
            Column("binary_format",  "Format",     70, "badge"),
            Column("vendor",         "Vendor",    130, "text"),
            Column("product_version","Version",    90, "text"),
            Column("signed",         "Signed",     70, "bool"),
            Column("eol_status",     "EOL",        80, "badge"),
            Column("summary",        "AI Summary",180, "text"),
        ],
        tags        = ["software","executables"],
        subcategories = [

            Category(
                id="exe-eol", name="End-of-Life",
                description="Software past its support end date",
                group="Software", icon="💀", color="#f87171", parent_id="executables",
                cypher="MATCH (f:File) WHERE f.eol_status = 'eol' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("product_version","Version",90,"text"), Column("vendor","Vendor",130,"text"), Column("eol_date","EOL Date",110,"date")],
                tags=["software","eol","compliance"],
            ),

            Category(
                id="exe-unsigned", name="Unsigned",
                description="Executables without valid code signature",
                group="Software", icon="🚫", color="#fbbf24", parent_id="executables",
                cypher="MATCH (f:File) WHERE f.file_category = 'executable' AND f.signed = false AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("binary_format","Format",70,"badge"), Column("product_version","Version",90,"text"), Column("vendor","Vendor",130,"text")],
                tags=["software","security"],
            ),

            Category(
                id="exe-high-risk", name="High Risk",
                description="Binaries rated high risk by AI analysis",
                group="Software", icon="🚨", color="#ef4444", parent_id="executables",
                cypher="MATCH (f:File) WHERE f.file_category = 'executable' AND f.risk_assessment = 'high' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("risk_assessment","Risk",90,"badge"), Column("binary_format","Format",70,"badge"), Column("signed","Signed",70,"bool"), Column("summary","AI Summary",180,"text")],
                tags=["software","security","ai"],
            ),

            Category(
                id="exe-packed", name="Packed / High Entropy",
                description="Binaries with high entropy — possibly packed or obfuscated",
                group="Software", icon="🎭", color="#7c3aed", parent_id="executables",
                cypher="MATCH (f:File) WHERE f.is_packed = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("entropy","Entropy",80,"num"), Column("signed","Signed",70,"bool"), Column("binary_format","Format",70,"badge")],
                tags=["software","security"],
            ),

            Category(
                id="exe-drivers", name="Drivers",
                description="Kernel drivers and system modules",
                group="Software", icon="🔧", color="#6d28d9", parent_id="executables",
                cypher="MATCH (f:File) WHERE (f.name ENDS WITH '.sys' OR f.ai_category = 'driver') AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("product_version","Version",90,"text"), Column("signed","Signed",70,"bool"), Column("vendor","Vendor",130,"text")],
                tags=["software","drivers"],
            ),
        ],
    ),

    # ══ ARCHIVES ══════════════════════════════════════════════════════════════
    Category(
        id          = "archives",
        name        = "Archives",
        description = "ZIP, RAR, 7z, tar, ISO and other compressed files",
        group       = "Software",
        icon        = "📦",
        color       = "#fb923c",
        cypher      = "MATCH (f:File) WHERE f.file_category = 'archive' AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [
            Column("file_count_in_archive","Files",    70, "num"),
            Column("compression_ratio",    "Ratio",    70, "num"),
            Column("contains_executables", "Has .exe", 80, "bool"),
        ],
        tags        = ["archives"],
        subcategories=[
            Category(
                id="archives-with-exe", name="Contains Executables",
                description="Archives containing .exe, .dll, .bat files",
                group="Software", icon="⚠️", color="#f97316", parent_id="archives",
                cypher="MATCH (f:File) WHERE f.file_category = 'archive' AND f.contains_executables = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_count_in_archive","Files",70,"num"), Column("size","Size",80,"size")],
                tags=["archives","security"],
            ),
        ],
    ),

    # ══ CERTIFICATES ══════════════════════════════════════════════════════════
    Category(
        id          = "certificates",
        name        = "Certificates & Keys",
        description = "TLS, code signing, CA certs, and private keys",
        group       = "Security",
        icon        = "🏅",
        color       = "#4ade80",
        cypher      = "MATCH (f:File) WHERE f.file_category IN ['certificate','private_key'] AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [
            Column("cert_subject",     "Subject",    200, "text"),
            Column("cert_issuer",      "Issuer",     160, "text"),
            Column("cert_valid_to",    "Expires",    130, "date"),
            Column("cert_is_expired",  "Expired",     80, "bool"),
            Column("days_until_expiry","Days Left",   80, "num"),
            Column("is_self_signed",   "Self-Signed", 90, "bool"),
        ],
        tags        = ["certificates","security"],
        subcategories = [
            Category(
                id="certs-expired", name="Expired",
                description="Certificates past their expiry date",
                group="Security", icon="❌", color="#f87171", parent_id="certificates",
                cypher="MATCH (f:File) WHERE f.cert_is_expired = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("cert_subject","Subject",200,"text"), Column("cert_valid_to","Expired",130,"date"), Column("cert_issuer","Issuer",160,"text")],
                tags=["certificates","security"],
            ),
            Category(
                id="certs-expiring-30", name="Expiring < 30 days",
                description="Certificates expiring within 30 days",
                group="Security", icon="⏰", color="#fbbf24", parent_id="certificates",
                cypher="MATCH (f:File) WHERE f.file_category = 'certificate' AND f.days_until_expiry < 30 AND f.days_until_expiry >= 0 AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("cert_subject","Subject",200,"text"), Column("days_until_expiry","Days Left",80,"num"), Column("cert_valid_to","Expires",130,"date")],
                tags=["certificates","security"],
            ),
            Category(
                id="certs-self-signed", name="Self-Signed",
                description="Certificates signed by their own key",
                group="Security", icon="🔏", color="#86efac", parent_id="certificates",
                cypher="MATCH (f:File) WHERE f.file_category = 'certificate' AND f.is_self_signed = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("cert_subject","Subject",200,"text"), Column("days_until_expiry","Days Left",80,"num")],
                tags=["certificates","security"],
            ),
            Category(
                id="private-keys", name="Private Keys",
                description="RSA, EC, and other private key files",
                group="Security", icon="🔐", color="#22c55e", parent_id="certificates",
                cypher="MATCH (f:File) WHERE f.file_category = 'private_key' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("key_type","Key Type",100,"badge"), Column("key_bits","Key Size",80,"num"), Column("passphrase_protected","Protected",90,"bool")],
                tags=["certificates","keys","security"],
            ),
        ],
    ),

    # ══ SECRETS ════════════════════════════════════════════════════════════════
    Category(
        id          = "secrets",
        name        = "Exposed Secrets",
        description = "Files with hardcoded API keys, passwords, or tokens",
        group       = "Security",
        icon        = "🔑",
        color       = "#f87171",
        cypher      = "MATCH (f:File) WHERE f.contains_secrets = true AND f.tenant_id = $tid RETURN f",
        columns     = _base() + _secrets_cols() + [
            Column("file_category",  "File Type",   90, "badge"),
            Column("code_language",  "Language",   100, "badge"),
            Column("sensitivity_level","Severity", 110, "badge"),
        ],
        tags        = ["security","secrets"],
        subcategories = [
            Category(
                id="secrets-api-keys", name="API Keys",
                description="Files with detected API keys",
                group="Security", icon="🗝️", color="#f87171", parent_id="secrets",
                cypher="MATCH (f:File) WHERE f.secret_types CONTAINS 'api_key' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("code_language","Language",100,"badge"), Column("sensitivity_level","Severity",110,"badge"), Column("path","Path",300,"path")],
                tags=["security","secrets","api-key"],
            ),
            Category(
                id="secrets-passwords", name="Passwords",
                description="Files with detected passwords or credentials",
                group="Security", icon="🔓", color="#ef4444", parent_id="secrets",
                cypher="MATCH (f:File) WHERE (f.secret_types CONTAINS 'password' OR f.secret_types CONTAINS 'passwd') AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_category","Type",90,"badge"), Column("code_language","Language",100,"badge")],
                tags=["security","secrets","passwords"],
            ),
            Category(
                id="secrets-tokens", name="Auth Tokens",
                description="Files with bearer tokens or auth tokens",
                group="Security", icon="🎟️", color="#fca5a5", parent_id="secrets",
                cypher="MATCH (f:File) WHERE (f.secret_types CONTAINS 'token' OR f.secret_types CONTAINS 'bearer') AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_category","Type",90,"badge"), Column("code_language","Language",100,"badge")],
                tags=["security","secrets","tokens"],
            ),
        ],
    ),

    # ══ PII ════════════════════════════════════════════════════════════════════
    Category(
        id          = "pii",
        name        = "Personal Data (PII)",
        description = "Files with detected personally identifiable information",
        group       = "Security",
        icon        = "🔒",
        color       = "#fb7185",
        cypher      = "MATCH (f:File) WHERE f.pii_detected = true AND f.tenant_id = $tid RETURN f",
        columns     = _base() + _pii_cols() + [Column("file_category","Type",90,"badge")],
        tags        = ["security","pii","compliance","gdpr"],
        subcategories = [
            Category(
                id="pii-high", name="High Sensitivity",
                description="Files with high-sensitivity PII (SSN, financial, health)",
                group="Security", icon="🔴", color="#ef4444", parent_id="pii",
                cypher="MATCH (f:File) WHERE f.pii_detected = true AND f.sensitivity_level = 'high' AND f.tenant_id = $tid RETURN f",
                columns=_base() + _pii_cols() + [Column("file_category","Type",90,"badge"), Column("summary","AI Summary",220,"text")],
                tags=["pii","compliance","gdpr","high-sensitivity"],
            ),
            Category(
                id="pii-emails-phones", name="Emails & Phones",
                description="Files containing email addresses or phone numbers",
                group="Security", icon="📞", color="#f43f5e", parent_id="pii",
                cypher="MATCH (f:File) WHERE (f.pii_types CONTAINS 'email' OR f.pii_types CONTAINS 'phone') AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("pii_types","PII Types",160,"text"), Column("file_category","Type",90,"badge")],
                tags=["pii","compliance"],
            ),
            Category(
                id="pii-ssn", name="SSN / National ID",
                description="Files containing social security or national ID numbers",
                group="Security", icon="🪪", color="#dc2626", parent_id="pii",
                cypher="MATCH (f:File) WHERE f.pii_types CONTAINS 'ssn' AND f.tenant_id = $tid RETURN f",
                columns=_base() + _pii_cols() + [Column("file_category","Type",90,"badge")],
                tags=["pii","compliance","gdpr"],
            ),
        ],
    ),

    # ══ CVE / VULNERABILITIES ═════════════════════════════════════════════════
    Category(
        id          = "vulnerabilities",
        name        = "Vulnerabilities",
        description = "Software with known CVEs from NVD/OSV",
        group       = "Security",
        icon        = "🛡️",
        color       = "#f87171",
        cypher      = "MATCH (a:Application)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE a.tenant_id = $tid RETURN DISTINCT a AS f",
        columns     = [
            Column("name",           "Name",      200, "text"),
            Column("product_version","Version",    90, "text"),
            Column("vendor",         "Vendor",    120, "text"),
            Column("source_connector","Source",   120, "badge"),
        ],
        tags        = ["security","cve","vulnerabilities"],
        subcategories=[
            Category(
                id="cve-critical", name="Critical CVEs",
                description="Software with critical CVSS severity vulnerabilities",
                group="Security", icon="🚨", color="#dc2626", parent_id="vulnerabilities",
                cypher="MATCH (a:Application)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE v.cvss_severity = 'critical' AND a.tenant_id = $tid RETURN DISTINCT a AS f",
                columns=[Column("name","Name",200,"text"), Column("product_version","Version",90,"text"), Column("vendor","Vendor",120,"text")],
                tags=["security","cve","critical"],
            ),
            Category(
                id="cve-high", name="High CVEs",
                description="Software with high severity vulnerabilities",
                group="Security", icon="🔥", color="#ef4444", parent_id="vulnerabilities",
                cypher="MATCH (a:Application)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE v.cvss_severity = 'high' AND a.tenant_id = $tid RETURN DISTINCT a AS f",
                columns=[Column("name","Name",200,"text"), Column("product_version","Version",90,"text"), Column("vendor","Vendor",120,"text")],
                tags=["security","cve","high"],
            ),
        ],
    ),

    # ══ PEOPLE ════════════════════════════════════════════════════════════════
    Category(
        id          = "people",
        name        = "People",
        description = "People identified via face recognition or document entities",
        group       = "People & Identity",
        icon        = "👤",
        color       = "#f472b6",
        cypher      = "MATCH (p:Person) WHERE p.tenant_id = $tid RETURN p AS f",
        columns     = [
            Column("name",        "Name",         180, "text"),
            Column("known",       "Identified",    90, "bool"),
            Column("face_count",  "Appearances",  100, "num"),
            Column("first_seen",  "First Seen",   130, "date"),
            Column("last_seen",   "Last Seen",    130, "date"),
        ],
        tags        = ["people"],
        subcategories = [
            Category(
                id="people-identified", name="Identified",
                description="People with a confirmed identity",
                group="People & Identity", icon="✅", color="#ec4899", parent_id="people",
                cypher="MATCH (p:Person) WHERE p.known = true AND p.tenant_id = $tid RETURN p AS f",
                columns=[Column("name","Name",180,"text"), Column("face_count","Appearances",100,"num"), Column("first_seen","First Seen",130,"date"), Column("last_seen","Last Seen",130,"date")],
                tags=["people","identified"],
            ),
            Category(
                id="people-unknown-clusters", name="Unknown Clusters",
                description="Unidentified faces grouped by similarity",
                group="People & Identity", icon="👥", color="#f472b6", parent_id="people",
                cypher="MATCH (fc:FaceCluster) WHERE fc.known = false AND fc.tenant_id = $tid RETURN fc AS f",
                columns=[Column("cluster_id","Cluster ID",120,"mono"), Column("face_count","Appearances",100,"num"), Column("first_seen","First Seen",130,"date")],
                tags=["people","faces","unidentified"],
            ),
            Category(
                id="people-entities", name="Mentioned in Docs",
                description="People extracted from documents by AI entity recognition",
                group="People & Identity", icon="📝", color="#db2777", parent_id="people",
                cypher="MATCH (p:Person) WHERE p.source = 'entity_extraction' AND p.tenant_id = $tid RETURN p AS f",
                columns=[Column("name","Name",180,"text"), Column("source_file","Source File",200,"path"), Column("context","Context",240,"text")],
                tags=["people","ai","entities"],
            ),
        ],
    ),

    # ══ 3D MODELS ════════════════════════════════════════════════════════════
    Category(
        id          = "3d-models",
        name        = "3D Models & CAD",
        description = "STL, OBJ, FBX, STEP, DWG, and other 3D/CAD files",
        group       = "Design & Engineering",
        icon        = "🧊",
        color       = "#67e8f9",
        cypher      = "MATCH (f:File) WHERE f.file_category = '3d_model' AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [Column("mime_type","Format",110,"badge")],
        tags        = ["3d","cad","design"],
    ),

    # ══ CALENDAR / CONTACTS ════════════════════════════════════════════════════
    Category(
        id          = "calendar-contacts",
        name        = "Calendar & Contacts",
        description = ".ics calendar files and .vcf contact cards",
        group       = "Documents & Text",
        icon        = "📅",
        color       = "#a3e635",
        cypher      = "MATCH (f:File) WHERE f.file_category IN ['calendar','contact'] AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [Column("file_category","Type",90,"badge")],
        tags        = ["calendar","contacts"],
    ),

    # ══ DUPLICATES ════════════════════════════════════════════════════════════
    Category(
        id          = "duplicates",
        name        = "Duplicate Files",
        description = "Files with identical content (same SHA-256 hash)",
        group       = "Storage",
        icon        = "♻️",
        color       = "#6b7280",
        cypher      = "MATCH (f:File) WHERE f.sha256 IS NOT NULL AND f.tenant_id = $tid WITH f.sha256 AS h, collect(f) AS files WHERE size(files) > 1 UNWIND files AS f RETURN f",
        columns     = _base() + [Column("sha256","Hash",160,"mono"), Column("file_category","Type",90,"badge")],
        tags        = ["storage","cleanup","duplicates"],
    ),

    # ══ AI ANALYSIS SURFACE ═══════════════════════════════════════════════════
    Category(
        id          = "ai-enriched",
        name        = "AI Enriched",
        description = "All files that have been processed by local AI models",
        group       = "AI Analysis",
        icon        = "🤖",
        color       = "#c084fc",
        cypher      = "MATCH (f:File) WHERE f.summary IS NOT NULL AND f.tenant_id = $tid RETURN f",
        columns     = _base() + [
            Column("file_category", "Type",       90, "badge"),
            Column("summary",       "Summary",   260, "text"),
            Column("sentiment",     "Sentiment",  90, "badge"),
            Column("language",      "Language",   80, "badge"),
        ],
        tags        = ["ai"],
        subcategories = [
            Category(
                id="ai-negative-sentiment", name="Negative Sentiment",
                description="Files rated negative in tone by AI analysis",
                group="AI Analysis", icon="😟", color="#a855f7", parent_id="ai-enriched",
                cypher="MATCH (f:File) WHERE f.sentiment = 'negative' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_category","Type",90,"badge"), Column("document_type","Doc Type",90,"badge"), Column("summary","Summary",260,"text")],
                tags=["ai","sentiment"],
            ),
            Category(
                id="ai-inferred-relationships", name="Inferred Relationships",
                description="Files connected by AI-inferred semantic relationships",
                group="AI Analysis", icon="🔗", color="#9333ea", parent_id="ai-enriched",
                cypher="MATCH (f:File)-[r:SIMILAR_TO|REFERENCES|PART_OF]->(g:File) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("summary","Summary",260,"text"), Column("file_category","Type",90,"badge")],
                tags=["ai","relationships"],
            ),
            Category(
                id="ai-has-action-items", name="Has Action Items",
                description="Files where AI detected tasks, todos, or action items",
                group="AI Analysis", icon="✅", color="#7c3aed", parent_id="ai-enriched",
                cypher="MATCH (f:File) WHERE f.action_items IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("action_items","Action Items",300,"text"), Column("document_type","Type",90,"badge")],
                tags=["ai","actions"],
            ),
        ],
    ),
]


# ── Flat index ─────────────────────────────────────────────────────────────────

def _flatten(cats: list[Category]) -> list[Category]:
    out = []
    for c in cats:
        out.append(c)
        if c.subcategories:
            out.extend(_flatten(c.subcategories))
    return out

ALL_CATEGORIES: list[Category]      = _flatten(INVENTORY)
CATEGORY_INDEX: dict[str, Category] = {c.id: c for c in ALL_CATEGORIES}


def get_category(cid: str) -> Category | None:
    return CATEGORY_INDEX.get(cid)

def get_by_group() -> dict[str, list[Category]]:
    """Top-level categories only, grouped."""
    out: dict[str, list[Category]] = {}
    for c in INVENTORY:
        out.setdefault(c.group, []).append(c)
    return out
