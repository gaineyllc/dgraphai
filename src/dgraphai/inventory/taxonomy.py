"""
Data Inventory taxonomy — organized by DATA TYPE, not attributes.

Hierarchy principle:
  Group → Category (data type) → Subtype (file format / encoding)

Attributes like resolution, HDR, PII sensitivity, codec, etc. are NOT
sub-categories. They are filters applied on top of a data type when browsing
the node list. This mirrors how a user thinks about their data:
  "I have video files → specifically MKV files → let me filter by 4K/HDR"

Node types covered: File, Directory, Person, FaceCluster, Location,
  Organization, Topic, Tag, Collection, Event, MediaItem, Application,
  Binary, Vendor, Product, Version, Vulnerability, License, Dependency,
  Certificate (all 20 from archon schema)

Relationship types covered in Cypher: all 26 from archon schema
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Column:
    key:   str
    label: str
    width: int = 160
    kind:  str = "text"   # text | size | date | badge | bool | path | num | mono


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
    # Pre-applied attribute filters shown in the node list header
    # (these are informational, not structural sub-categories)
    default_filters: list[dict] = field(default_factory=list)


# ── Shared column sets ─────────────────────────────────────────────────────────

def _base() -> list[Column]:
    return [
        Column("name",             "Name",        220, "text"),
        Column("path",             "Path",        300, "path"),
        Column("size",             "Size",         80, "size"),
        Column("modified_at",      "Modified",    130, "date"),
        Column("source_connector", "Source",      120, "badge"),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY — organized by data type / file format
# ══════════════════════════════════════════════════════════════════════════════

INVENTORY: list[Category] = [

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Video
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="video", name="Video", group="Video",
        description="All video files across your connected sources",
        icon="🎬", color="#4f8ef7",
        cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [
            Column("video_codec",     "Codec",      80, "badge"),
            Column("height",          "Resolution", 90, "num"),
            Column("hdr_format",      "HDR",        80, "badge"),
            Column("duration_secs",   "Duration",   90, "num"),
            Column("audio_codec",     "Audio",      80, "badge"),
            Column("container_format","Container", 110, "badge"),
        ],
        tags=["media", "video"],
        subcategories=[
            Category(
                id="video-mkv", name="MKV", group="Video", parent_id="video",
                description="Matroska video files (.mkv) — common for high-quality encodes",
                icon="🎞️", color="#4f8ef7",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.extension = '.mkv' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("video_codec","Codec",80,"badge"), Column("height","Res",60,"num"), Column("hdr_format","HDR",80,"badge"), Column("duration_secs","Duration",90,"num")],
                tags=["video","mkv"],
            ),
            Category(
                id="video-mp4", name="MP4", group="Video", parent_id="video",
                description="MPEG-4 video files (.mp4, .m4v)",
                icon="🎞️", color="#60a5fa",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.extension IN ['.mp4','.m4v'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("video_codec","Codec",80,"badge"), Column("height","Res",60,"num"), Column("duration_secs","Duration",90,"num")],
                tags=["video","mp4"],
            ),
            Category(
                id="video-ts", name="Transport Stream", group="Video", parent_id="video",
                description="Transport stream files (.ts, .m2ts) — typically broadcast or Blu-ray",
                icon="📡", color="#818cf8",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.extension IN ['.ts','.m2ts','.mts'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("video_codec","Codec",80,"badge"), Column("height","Res",60,"num"), Column("duration_secs","Duration",90,"num")],
                tags=["video","ts","broadcast"],
            ),
            Category(
                id="video-mov", name="MOV / QuickTime", group="Video", parent_id="video",
                description="Apple QuickTime video files (.mov)",
                icon="🎞️", color="#a78bfa",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.extension = '.mov' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("video_codec","Codec",80,"badge"), Column("height","Res",60,"num"), Column("duration_secs","Duration",90,"num")],
                tags=["video","mov","quicktime"],
            ),
            Category(
                id="video-avi", name="AVI", group="Video", parent_id="video",
                description="Audio Video Interleave files (.avi)",
                icon="🎞️", color="#6366f1",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.extension = '.avi' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("video_codec","Codec",80,"badge"), Column("height","Res",60,"num"), Column("duration_secs","Duration",90,"num")],
                tags=["video","avi"],
            ),
            Category(
                id="video-wmv", name="WMV / ASF", group="Video", parent_id="video",
                description="Windows Media Video files (.wmv, .asf)",
                icon="🎞️", color="#7c3aed",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.extension IN ['.wmv','.asf'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("video_codec","Codec",80,"badge"), Column("height","Res",60,"num")],
                tags=["video","wmv","windows"],
            ),
            Category(
                id="video-webm", name="WebM / FLV", group="Video", parent_id="video",
                description="Web video formats (.webm, .flv)",
                icon="🌐", color="#4f46e5",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.extension IN ['.webm','.flv'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("video_codec","Codec",80,"badge"), Column("height","Res",60,"num"), Column("duration_secs","Duration",90,"num")],
                tags=["video","webm","web"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Audio
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="audio", name="Audio", group="Audio",
        description="All audio files — music, podcasts, recordings",
        icon="🎵", color="#a78bfa",
        cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [
            Column("audio_codec",   "Format",    80, "badge"),
            Column("artist",        "Artist",   140, "text"),
            Column("album",         "Album",    140, "text"),
            Column("duration_secs", "Duration",  90, "num"),
            Column("sample_rate",   "Sample Rate",90,"num"),
            Column("bit_depth",     "Bit Depth", 80, "num"),
        ],
        tags=["media","audio"],
        subcategories=[
            Category(
                id="audio-flac", name="FLAC", group="Audio", parent_id="audio",
                description="Free Lossless Audio Codec — lossless quality",
                icon="💎", color="#8b5cf6",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.extension = '.flac' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("artist","Artist",130,"text"), Column("album","Album",130,"text"), Column("bit_depth","Bit Depth",80,"num"), Column("sample_rate","Sample Rate",90,"num")],
                tags=["audio","flac","lossless"],
            ),
            Category(
                id="audio-mp3", name="MP3", group="Audio", parent_id="audio",
                description="MPEG Layer III audio files (.mp3)",
                icon="🎵", color="#c084fc",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.extension = '.mp3' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("artist","Artist",130,"text"), Column("album","Album",130,"text"), Column("overall_bitrate","Bitrate",80,"num"), Column("title","Title",160,"text")],
                tags=["audio","mp3"],
            ),
            Category(
                id="audio-aac", name="AAC / M4A", group="Audio", parent_id="audio",
                description="Advanced Audio Coding files (.aac, .m4a)",
                icon="🎵", color="#a78bfa",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.extension IN ['.aac','.m4a'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("artist","Artist",130,"text"), Column("album","Album",130,"text"), Column("overall_bitrate","Bitrate",80,"num")],
                tags=["audio","aac","m4a"],
            ),
            Category(
                id="audio-wav", name="WAV", group="Audio", parent_id="audio",
                description="Uncompressed PCM audio (.wav) — lossless, large files",
                icon="🔊", color="#7c3aed",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.extension = '.wav' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("bit_depth","Bit Depth",80,"num"), Column("sample_rate","Sample Rate",90,"num"), Column("duration_secs","Duration",90,"num")],
                tags=["audio","wav","lossless"],
            ),
            Category(
                id="audio-dsd", name="DSD / SACD", group="Audio", parent_id="audio",
                description="Direct Stream Digital high-resolution audio (.dsf, .dff)",
                icon="💿", color="#6d28d9",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.extension IN ['.dsf','.dff'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("sample_rate","Sample Rate",90,"num"), Column("artist","Artist",130,"text"), Column("album","Album",130,"text")],
                tags=["audio","dsd","lossless","hifi"],
            ),
            Category(
                id="audio-opus", name="Opus / OGG", group="Audio", parent_id="audio",
                description="Open source audio formats (.opus, .ogg, .oga)",
                icon="🎵", color="#9333ea",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.extension IN ['.opus','.ogg','.oga'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("artist","Artist",130,"text"), Column("album","Album",130,"text"), Column("overall_bitrate","Bitrate",80,"num")],
                tags=["audio","opus","ogg"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Images
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="images", name="Images", group="Images",
        description="All image and photo files",
        icon="🖼️", color="#34d399",
        cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [
            Column("width",          "W",          55, "num"),
            Column("height",         "H",          55, "num"),
            Column("camera_model",   "Camera",    130, "text"),
            Column("datetime_original","Taken",   130, "date"),
            Column("gps_latitude",   "Lat",        70, "num"),
        ],
        tags=["media","images"],
        subcategories=[
            Category(
                id="images-jpeg", name="JPEG", group="Images", parent_id="images",
                description="JPEG image files (.jpg, .jpeg) — most common photo format",
                icon="📷", color="#10b981",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.extension IN ['.jpg','.jpeg'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("width","W",55,"num"), Column("height","H",55,"num"), Column("camera_model","Camera",130,"text"), Column("datetime_original","Taken",130,"date")],
                tags=["images","jpeg"],
            ),
            Category(
                id="images-png", name="PNG", group="Images", parent_id="images",
                description="Portable Network Graphics (.png) — lossless, supports transparency",
                icon="🖼️", color="#34d399",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.extension = '.png' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("width","W",55,"num"), Column("height","H",55,"num"), Column("bit_depth","Bit Depth",80,"num")],
                tags=["images","png"],
            ),
            Category(
                id="images-raw", name="RAW / HEIF", group="Images", parent_id="images",
                description="Camera RAW files and HEIF — maximum quality, unprocessed sensor data",
                icon="📸", color="#059669",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.extension IN ['.cr2','.nef','.arw','.raf','.dng','.heic','.heif','.rw2'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("camera_make","Make",90,"text"), Column("camera_model","Camera",130,"text"), Column("focal_length","Focal (mm)",90,"num"), Column("iso","ISO",60,"num"), Column("aperture","f/",60,"num")],
                tags=["images","raw","heic","camera"],
            ),
            Category(
                id="images-tiff", name="TIFF / BMP", group="Images", parent_id="images",
                description="TIFF and BMP format — lossless, high bit depth",
                icon="🖼️", color="#047857",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.extension IN ['.tiff','.tif','.bmp'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("width","W",55,"num"), Column("height","H",55,"num"), Column("bit_depth","Bit Depth",80,"num"), Column("color_profile","Profile",100,"badge")],
                tags=["images","tiff","bmp"],
            ),
            Category(
                id="images-webp", name="WebP / GIF", group="Images", parent_id="images",
                description="Web image formats (.webp, .gif, .avif)",
                icon="🌐", color="#6ee7b7",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.extension IN ['.webp','.gif','.avif'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("width","W",55,"num"), Column("height","H",55,"num")],
                tags=["images","webp","gif","web"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Documents
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="documents", name="Documents", group="Documents",
        description="Office documents, PDFs, text files, and presentations",
        icon="📄", color="#fbbf24",
        cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [
            Column("mime_type",    "Format",    110, "badge"),
            Column("author",       "Author",    130, "text"),
            Column("page_count",   "Pages",      65, "num"),
            Column("word_count",   "Words",      75, "num"),
            Column("language",     "Language",   80, "badge"),
        ],
        tags=["documents"],
        subcategories=[
            Category(
                id="docs-pdf", name="PDF", group="Documents", parent_id="documents",
                description="Portable Document Format files (.pdf)",
                icon="📕", color="#f59e0b",
                cypher="MATCH (f:File) WHERE f.extension = '.pdf' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","Author",130,"text"), Column("page_count","Pages",65,"num"), Column("word_count","Words",75,"num"), Column("is_encrypted","Encrypted",80,"bool"), Column("is_signed","Signed",70,"bool")],
                tags=["documents","pdf"],
            ),
            Category(
                id="docs-word", name="Word (.docx / .doc)", group="Documents", parent_id="documents",
                description="Microsoft Word documents",
                icon="📝", color="#2563eb",
                cypher="MATCH (f:File) WHERE f.extension IN ['.docx','.doc','.odt','.rtf'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","Author",130,"text"), Column("word_count","Words",75,"num"), Column("has_macros","Macros",70,"bool"), Column("language","Language",80,"badge")],
                tags=["documents","word","docx"],
            ),
            Category(
                id="docs-excel", name="Excel (.xlsx / .csv)", group="Documents", parent_id="documents",
                description="Spreadsheets — Excel, CSV, ODS",
                icon="📊", color="#16a34a",
                cypher="MATCH (f:File) WHERE f.extension IN ['.xlsx','.xls','.csv','.ods','.tsv'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","Author",130,"text"), Column("has_macros","Macros",70,"bool"), Column("pii_detected","PII",60,"bool")],
                tags=["documents","excel","spreadsheet","csv"],
            ),
            Category(
                id="docs-powerpoint", name="PowerPoint (.pptx)", group="Documents", parent_id="documents",
                description="Presentations — PowerPoint, Keynote, ODP",
                icon="📊", color="#dc2626",
                cypher="MATCH (f:File) WHERE f.extension IN ['.pptx','.ppt','.key','.odp'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","Author",130,"text"), Column("page_count","Slides",65,"num")],
                tags=["documents","powerpoint","presentation"],
            ),
            Category(
                id="docs-text", name="Text / Markdown", group="Documents", parent_id="documents",
                description="Plain text, Markdown, and rich text files",
                icon="📋", color="#d97706",
                cypher="MATCH (f:File) WHERE f.extension IN ['.txt','.md','.rst','.rtf','.log'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("word_count","Words",75,"num"), Column("language","Language",80,"badge")],
                tags=["documents","text","markdown"],
            ),
            Category(
                id="docs-data", name="Data Files (.json / .xml / .yaml)", group="Documents", parent_id="documents",
                description="Structured data files — JSON, XML, YAML, TOML",
                icon="🗂️", color="#b45309",
                cypher="MATCH (f:File) WHERE f.extension IN ['.json','.xml','.yaml','.yml','.toml','.ini'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("contains_secrets","Secrets",80,"bool"), Column("pii_detected","PII",60,"bool")],
                tags=["documents","json","xml","yaml","data"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Email
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="emails", name="Email", group="Email",
        description=".eml, .msg, and .mbox email archive files",
        icon="✉️", color="#38bdf8",
        cypher="MATCH (f:File) WHERE f.file_category = 'email' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("author","From",140,"text"), Column("title","Subject",200,"text"), Column("pii_detected","PII",60,"bool"), Column("language","Language",80,"badge")],
        tags=["email"],
        subcategories=[
            Category(
                id="emails-eml", name=".eml / .mbox", group="Email", parent_id="emails",
                description="Standard email files (.eml, .mbox, .mbx)",
                icon="📧", color="#0ea5e9",
                cypher="MATCH (f:File) WHERE f.extension IN ['.eml','.mbox','.mbx'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","From",140,"text"), Column("title","Subject",200,"text"), Column("pii_detected","PII",60,"bool")],
                tags=["email","eml"],
            ),
            Category(
                id="emails-msg", name=".msg (Outlook)", group="Email", parent_id="emails",
                description="Microsoft Outlook message files (.msg)",
                icon="📧", color="#0284c7",
                cypher="MATCH (f:File) WHERE f.extension = '.msg' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","From",140,"text"), Column("title","Subject",200,"text"), Column("pii_detected","PII",60,"bool")],
                tags=["email","msg","outlook"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Source Code
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="code", name="Source Code", group="Code",
        description="Programming files, scripts, and config",
        icon="💻", color="#22d3ee",
        cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("code_language","Language",100,"badge"), Column("line_count","Lines",70,"num"), Column("contains_secrets","Secrets",80,"bool")],
        tags=["code"],
        subcategories=[
            Category(
                id="code-python", name="Python", group="Code", parent_id="code",
                description="Python source files (.py, .pyw, .pyi)",
                icon="🐍", color="#3b82f6",
                cypher="MATCH (f:File) WHERE f.extension IN ['.py','.pyw','.pyi'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("line_count","Lines",70,"num"), Column("function_count","Functions",80,"num"), Column("contains_secrets","Secrets",80,"bool")],
                tags=["code","python"],
            ),
            Category(
                id="code-javascript", name="JavaScript / TypeScript", group="Code", parent_id="code",
                description="JS and TS source files",
                icon="🟨", color="#eab308",
                cypher="MATCH (f:File) WHERE f.extension IN ['.js','.mjs','.cjs','.ts','.tsx','.jsx'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("line_count","Lines",70,"num"), Column("framework","Framework",110,"badge"), Column("contains_secrets","Secrets",80,"bool")],
                tags=["code","javascript","typescript"],
            ),
            Category(
                id="code-go", name="Go", group="Code", parent_id="code",
                description="Go source files (.go)",
                icon="🔵", color="#06b6d4",
                cypher="MATCH (f:File) WHERE f.extension = '.go' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("line_count","Lines",70,"num"), Column("function_count","Functions",80,"num")],
                tags=["code","go","golang"],
            ),
            Category(
                id="code-rust", name="Rust", group="Code", parent_id="code",
                description="Rust source files (.rs)",
                icon="🦀", color="#f97316",
                cypher="MATCH (f:File) WHERE f.extension = '.rs' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("line_count","Lines",70,"num"), Column("function_count","Functions",80,"num")],
                tags=["code","rust"],
            ),
            Category(
                id="code-java", name="Java / Kotlin / Scala", group="Code", parent_id="code",
                description="JVM language source files",
                icon="☕", color="#dc2626",
                cypher="MATCH (f:File) WHERE f.extension IN ['.java','.kt','.scala','.groovy'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("line_count","Lines",70,"num"), Column("framework","Framework",110,"badge")],
                tags=["code","java","kotlin"],
            ),
            Category(
                id="code-csharp", name="C# / C / C++", group="Code", parent_id="code",
                description="C-family source files",
                icon="🔷", color="#7c3aed",
                cypher="MATCH (f:File) WHERE f.extension IN ['.cs','.c','.cpp','.h','.hpp','.cc'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("line_count","Lines",70,"num"), Column("function_count","Functions",80,"num")],
                tags=["code","csharp","c","cpp"],
            ),
            Category(
                id="code-shell", name="Shell / PowerShell", group="Code", parent_id="code",
                description="Shell scripts (.sh, .bash, .zsh, .ps1, .bat, .cmd)",
                icon="🖥️", color="#059669",
                cypher="MATCH (f:File) WHERE f.extension IN ['.sh','.bash','.zsh','.fish','.ps1','.bat','.cmd'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("line_count","Lines",70,"num"), Column("contains_secrets","Secrets",80,"bool")],
                tags=["code","shell","bash","powershell"],
            ),
            Category(
                id="code-config", name="Config Files", group="Code", parent_id="code",
                description="Configuration files — .env, YAML, TOML, INI, properties",
                icon="⚙️", color="#0891b2",
                cypher="MATCH (f:File) WHERE f.extension IN ['.env','.properties','.conf','.cfg','.ini'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("contains_secrets","Secrets",80,"bool"), Column("line_count","Lines",70,"num")],
                tags=["code","config","env"],
            ),
            Category(
                id="code-sql", name="SQL / GraphQL", group="Code", parent_id="code",
                description="Database query files (.sql, .graphql, .gql)",
                icon="🗃️", color="#0369a1",
                cypher="MATCH (f:File) WHERE f.extension IN ['.sql','.graphql','.gql'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("line_count","Lines",70,"num"), Column("contains_secrets","Secrets",80,"bool")],
                tags=["code","sql","database"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Executables & Software
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="executables", name="Executables & Libraries", group="Software",
        description="Binary executables, libraries, and installers",
        icon="⚙️", color="#8b5cf6",
        cypher="MATCH (f:File) WHERE f.file_category = 'executable' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("binary_format","Format",70,"badge"), Column("company_name","Vendor",130,"text"), Column("file_version","Version",90,"text"), Column("signed","Signed",70,"bool"), Column("eol_status","EOL",80,"badge")],
        tags=["software","executables"],
        subcategories=[
            Category(
                id="exe-pe", name="Windows PE (.exe / .dll)", group="Software", parent_id="executables",
                description="Windows Portable Executable files — programs and libraries",
                icon="🪟", color="#0078d4",
                cypher="MATCH (f:File) WHERE f.file_category = 'executable' AND f.binary_format = 'PE' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("company_name","Vendor",130,"text"), Column("file_version","Version",90,"text"), Column("signed","Signed",70,"bool"), Column("is_packed","Packed",70,"bool")],
                tags=["software","exe","windows"],
            ),
            Category(
                id="exe-elf", name="Linux ELF", group="Software", parent_id="executables",
                description="Linux/Unix ELF binaries and shared objects",
                icon="🐧", color="#f97316",
                cypher="MATCH (f:File) WHERE f.file_category = 'executable' AND f.binary_format = 'ELF' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("architecture","Arch",70,"badge"), Column("signed","Signed",70,"bool"), Column("is_packed","Packed",70,"bool")],
                tags=["software","elf","linux"],
            ),
            Category(
                id="exe-macho", name="macOS Mach-O", group="Software", parent_id="executables",
                description="macOS and iOS Mach-O binaries",
                icon="🍎", color="#6b7280",
                cypher="MATCH (f:File) WHERE f.file_category = 'executable' AND f.binary_format = 'MACHO' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("architectures","Architectures",160,"text"), Column("signed","Signed",70,"bool"), Column("is_universal","Universal",90,"bool")],
                tags=["software","macho","macos"],
            ),
            Category(
                id="exe-msi", name="Installers (.msi / .pkg / .deb)", group="Software", parent_id="executables",
                description="Software installers — MSI, PKG, DEB, RPM",
                icon="📦", color="#7c3aed",
                cypher="MATCH (f:File) WHERE f.extension IN ['.msi','.pkg','.deb','.rpm','.dmg'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("company_name","Vendor",130,"text"), Column("file_version","Version",90,"text"), Column("signed","Signed",70,"bool")],
                tags=["software","installer","msi"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Archives
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="archives", name="Archives", group="Archives",
        description="Compressed and archive files",
        icon="📦", color="#fb923c",
        cypher="MATCH (f:File) WHERE f.file_category = 'archive' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("compression_method","Method",100,"badge"), Column("file_count_in_archive","Files",70,"num"), Column("compression_ratio","Ratio",70,"num"), Column("contains_executables","Has .exe",80,"bool")],
        tags=["archives"],
        subcategories=[
            Category(
                id="archives-zip", name="ZIP", group="Archives", parent_id="archives",
                description="ZIP archives (.zip, .jar, .war, .apk)",
                icon="🗜️", color="#ea580c",
                cypher="MATCH (f:File) WHERE f.extension IN ['.zip','.jar','.war','.ear','.apk','.ipa'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_count_in_archive","Files",70,"num"), Column("contains_executables","Has .exe",80,"bool")],
                tags=["archives","zip"],
            ),
            Category(
                id="archives-7z", name="7-Zip / RAR", group="Archives", parent_id="archives",
                description="High-compression archives (.7z, .rar, .ace)",
                icon="🗜️", color="#f97316",
                cypher="MATCH (f:File) WHERE f.extension IN ['.7z','.rar','.ace','.arj'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_count_in_archive","Files",70,"num"), Column("compression_ratio","Ratio",70,"num")],
                tags=["archives","7z","rar"],
            ),
            Category(
                id="archives-tar", name="TAR / GZ / BZ2", group="Archives", parent_id="archives",
                description="Unix archive formats (.tar, .tar.gz, .tgz, .bz2, .xz)",
                icon="🗜️", color="#fb923c",
                cypher="MATCH (f:File) WHERE f.extension IN ['.tar','.gz','.tgz','.bz2','.xz','.zst','.lz4'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_count_in_archive","Files",70,"num"), Column("compression_ratio","Ratio",70,"num")],
                tags=["archives","tar","unix"],
            ),
            Category(
                id="archives-iso", name="Disk Images (.iso / .img)", group="Archives", parent_id="archives",
                description="Disk image files (.iso, .img, .dmg)",
                icon="💿", color="#fbbf24",
                cypher="MATCH (f:File) WHERE f.extension IN ['.iso','.img'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_count_in_archive","Files",70,"num")],
                tags=["archives","iso","disk"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Certificates & Keys
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="certificates", name="Certificates & Keys", group="Security",
        description="TLS certificates, CA certificates, and private keys",
        icon="🏅", color="#4ade80",
        cypher="MATCH (f:File) WHERE f.file_category IN ['certificate','private_key'] AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("cert_subject","Subject",200,"text"), Column("cert_issuer","Issuer",160,"text"), Column("cert_valid_to","Expires",130,"date"), Column("cert_is_expired","Expired",80,"bool"), Column("days_until_expiry","Days Left",80,"num")],
        tags=["certificates","security"],
        subcategories=[
            Category(
                id="certs-pem", name="PEM / CRT", group="Security", parent_id="certificates",
                description="PEM-encoded certificates (.pem, .crt, .cer)",
                icon="🏅", color="#22c55e",
                cypher="MATCH (f:File) WHERE f.extension IN ['.pem','.crt','.cer'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("cert_subject","Subject",200,"text"), Column("cert_valid_to","Expires",130,"date"), Column("cert_is_expired","Expired",80,"bool"), Column("is_ca","Is CA",70,"bool")],
                tags=["certificates","pem"],
            ),
            Category(
                id="certs-pkcs12", name="PKCS#12 / PFX", group="Security", parent_id="certificates",
                description="PKCS#12 bundles — certificate + private key (.p12, .pfx)",
                icon="🔐", color="#16a34a",
                cypher="MATCH (f:File) WHERE f.extension IN ['.p12','.pfx'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("cert_subject","Subject",200,"text"), Column("cert_valid_to","Expires",130,"date")],
                tags=["certificates","pkcs12","pfx"],
            ),
            Category(
                id="certs-keys", name="Private Keys (.key)", group="Security", parent_id="certificates",
                description="Standalone private key files (.key, .der)",
                icon="🔑", color="#15803d",
                cypher="MATCH (f:File) WHERE f.extension IN ['.key','.der'] OR f.file_category = 'private_key' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("key_type","Key Type",100,"badge"), Column("key_bits","Key Size",80,"num"), Column("passphrase_protected","Protected",90,"bool")],
                tags=["certificates","keys","private-key"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: 3D & Design
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="3d-models", name="3D Models & CAD", group="Design & Engineering",
        description="3D models, CAD drawings, and engineering files",
        icon="🧊", color="#67e8f9",
        cypher="MATCH (f:File) WHERE f.file_category = '3d_model' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("extension","Format",80,"badge")],
        tags=["3d","cad","design"],
        subcategories=[
            Category(
                id="3d-stl", name="STL / OBJ", group="Design & Engineering", parent_id="3d-models",
                description="3D mesh formats — STL and OBJ",
                icon="🧊", color="#22d3ee",
                cypher="MATCH (f:File) WHERE f.extension IN ['.stl','.obj'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("extension","Format",80,"badge")],
                tags=["3d","stl","obj"],
            ),
            Category(
                id="3d-cad", name="CAD (.dwg / .dxf / .step)", group="Design & Engineering", parent_id="3d-models",
                description="Engineering CAD formats — DWG, DXF, STEP, IGES",
                icon="📐", color="#06b6d4",
                cypher="MATCH (f:File) WHERE f.extension IN ['.dwg','.dxf','.step','.stp','.iges','.igs'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("extension","Format",80,"badge")],
                tags=["3d","cad","engineering"],
            ),
            Category(
                id="3d-blend", name="Blender / FBX", group="Design & Engineering", parent_id="3d-models",
                description="3D scene formats — Blender, FBX, COLLADA",
                icon="🎨", color="#0e7490",
                cypher="MATCH (f:File) WHERE f.extension IN ['.blend','.fbx','.dae','.glb','.gltf'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("extension","Format",80,"badge")],
                tags=["3d","blender","fbx"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Calendar & Contacts
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="calendar-contacts", name="Calendar & Contacts", group="Productivity",
        description="Calendar files (.ics) and contact cards (.vcf)",
        icon="📅", color="#a3e635",
        cypher="MATCH (f:File) WHERE f.file_category IN ['calendar','contact'] AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("extension","Format",80,"badge")],
        tags=["calendar","contacts"],
        subcategories=[
            Category(
                id="calendar-ics", name="Calendar (.ics)", group="Productivity", parent_id="calendar-contacts",
                description="iCalendar event files",
                icon="📆", color="#84cc16",
                cypher="MATCH (f:File) WHERE f.extension = '.ics' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [],
                tags=["calendar","ics"],
            ),
            Category(
                id="contacts-vcf", name="Contacts (.vcf)", group="Productivity", parent_id="calendar-contacts",
                description="vCard contact files",
                icon="👤", color="#65a30d",
                cypher="MATCH (f:File) WHERE f.extension = '.vcf' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [],
                tags=["contacts","vcf"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: People & Identity
    # (from face recognition + entity extraction — not file types)
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="people", name="People", group="People & Identity",
        description="Individuals identified by face recognition or document analysis",
        icon="👤", color="#f472b6",
        cypher="MATCH (p:Person) WHERE p.tenant_id = $tid RETURN p AS f",
        columns=[Column("name","Name",180,"text"), Column("known","Identified",90,"bool"), Column("face_count","Appearances",100,"num"), Column("first_seen","First Seen",130,"date")],
        tags=["people"],
        subcategories=[
            Category(
                id="people-identified", name="Identified People", group="People & Identity", parent_id="people",
                description="People with a confirmed identity (known=true)",
                icon="✅", color="#ec4899",
                cypher="MATCH (p:Person) WHERE p.known = true AND p.tenant_id = $tid RETURN p AS f",
                columns=[Column("name","Name",180,"text"), Column("face_count","Appearances",100,"num"), Column("first_seen","First Seen",130,"date")],
                tags=["people","identified"],
            ),
            Category(
                id="people-unknown", name="Unidentified Faces", group="People & Identity", parent_id="people",
                description="Face clusters not yet matched to a named person",
                icon="👥", color="#f472b6",
                cypher="MATCH (fc:FaceCluster) WHERE NOT (fc)-[:SAME_PERSON_AS]->(:Person) AND fc.tenant_id = $tid RETURN fc AS f",
                columns=[Column("cluster_id","Cluster",120,"mono"), Column("face_count","Appearances",100,"num"), Column("first_seen","First Seen",130,"date")],
                tags=["people","faces","unidentified"],
            ),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Software Inventory
    # (installed applications — not file types)
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="applications", name="Installed Applications", group="Software Inventory",
        description="Applications detected on scanned systems",
        icon="🖥️", color="#8b5cf6",
        cypher="MATCH (a:Application) WHERE a.tenant_id = $tid RETURN a AS f",
        columns=[Column("name","Name",200,"text"), Column("version_string","Version",90,"text"), Column("eol_status","EOL",80,"badge"), Column("cve_count","CVEs",60,"num"), Column("update_available","Update",80,"bool")],
        tags=["software","applications"],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Storage
    # ═══════════════════════════════════════════════════════════════════════════
    Category(
        id="duplicates", name="Duplicate Files", group="Storage",
        description="Files sharing identical content (same SHA-256)",
        icon="♻️", color="#6b7280",
        cypher="MATCH (f:File)-[:DUPLICATE_OF]->(g:File) WHERE f.tenant_id = $tid RETURN DISTINCT f",
        columns=_base() + [Column("sha256","Hash",160,"mono"), Column("extension","Format",80,"badge")],
        tags=["storage","duplicates"],
    ),
    Category(
        id="directories", name="Directories", group="Storage",
        description="Folder structure across all connected sources",
        icon="📁", color="#fbbf24",
        cypher="MATCH (d:Directory) WHERE d.tenant_id = $tid RETURN d AS f",
        columns=[Column("name","Name",200,"text"), Column("path","Path",300,"path"), Column("file_count","Files",70,"num"), Column("total_bytes","Total Size",100,"size")],
        tags=["storage","filesystem"],
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
