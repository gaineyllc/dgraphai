"""
Complete Data Inventory taxonomy for dgraph.ai.

Node types: File, Directory, Person, FaceCluster, Location, Organization,
  Topic, Tag, Collection, Event, MediaItem, Application, Binary,
  Vendor, Product, Version, Vulnerability, License, Dependency, Certificate

Relationship types (26):
  Filesystem:  CHILD_OF, DUPLICATE_OF, SIMILAR_TO, PART_OF, REFERENCES
  Semantic:    MENTIONS, TAGGED_WITH, LOCATED_AT, OCCURRED_DURING
  Visual:      DEPICTS, CONTAINS_FACE
  Media:       MATCHED_TO
  Software:    IS_APPLICATION, IS_BINARY, MADE_BY, IS_VERSION_OF, DEPENDS_ON,
               LICENSED_UNDER, HAS_VULNERABILITY, SIGNED_BY, OWNS, HAS_VERSION,
               SUPERSEDES
  Geography:   WITHIN
  Face/People: SAME_PERSON_AS

AI-enriched attributes covered:
  LLM (Ollama):        summary, document_type, sentiment, language, action_items,
                       entities_people, entities_orgs, entities_locations, topics
  Vision (LLaVA):      scene_type, objects, people_count, text_visible,
                       dominant_colors, is_document, mood
  Code (qwen2.5-coder):framework, code_quality, has_tests, security_concerns
  Binary (deepseek-r1):risk_assessment, ai_category
  Face (InsightFace):  face_count, face_cluster_ids, known
  Secrets:             contains_secrets, secret_types
  PII:                 pii_detected, pii_types, sensitivity_level
  Media matching:      tmdb_id, imdb_id, matched_media_title
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


# ── Shared column sets ─────────────────────────────────────────────────────────

def _base() -> list[Column]:
    return [
        Column("name",             "Name",        220, "text"),
        Column("path",             "Path",        300, "path"),
        Column("size",             "Size",         80, "size"),
        Column("modified_at",      "Modified",    130, "date"),
        Column("source_connector", "Source",      120, "badge"),
    ]

def _ai() -> list[Column]:
    return [
        Column("summary",   "AI Summary",  260, "text"),
        Column("sentiment", "Sentiment",    90, "badge"),
        Column("language",  "Language",     80, "badge"),
    ]

def _pii() -> list[Column]:
    return [
        Column("pii_detected",     "PII",         60, "bool"),
        Column("pii_types",        "PII Types",  140, "text"),
        Column("sensitivity_level","Sensitivity",110, "badge"),
    ]

def _secrets() -> list[Column]:
    return [
        Column("contains_secrets","Has Secrets", 90, "bool"),
        Column("secret_types",    "Secret Types",130,"text"),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY
# ══════════════════════════════════════════════════════════════════════════════

INVENTORY: list[Category] = [

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Media
    # ═══════════════════════════════════════════════════════════════════════════

    Category(
        id="video", name="Video", group="Media",
        description="All video files — movies, TV, recordings, clips",
        icon="🎬", color="#4f8ef7",
        cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [
            Column("video_codec",     "Codec",      80, "badge"),
            Column("height",          "Res",        60, "num"),
            Column("duration_secs",   "Duration",   90, "num"),
            Column("hdr_format",      "HDR",        80, "badge"),
            Column("container_format","Container", 110, "badge"),
            Column("summary",         "AI Summary",200, "text"),
        ],
        tags=["media","video"],
        subcategories=[

            Category(
                id="video-4k", name="4K / UHD", group="Media", parent_id="video",
                description="2160p and above video",
                icon="📺", color="#818cf8",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.height >= 2160 AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("video_codec","Codec",80,"badge"), Column("hdr_format","HDR",80,"badge"), Column("audio_codec","Audio",80,"badge"), Column("duration_secs","Duration",90,"num"), Column("overall_bitrate","Bitrate",90,"num")],
                tags=["video","4k"],
                subcategories=[
                    Category(id="video-4k-hdr", name="4K + HDR/DV", group="Media", parent_id="video-4k",
                        description="4K with HDR10, Dolby Vision, or HLG",
                        icon="✨", color="#6366f1",
                        cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.height >= 2160 AND f.hdr_format IS NOT NULL AND f.tenant_id = $tid RETURN f",
                        columns=_base() + [Column("hdr_format","HDR",90,"badge"), Column("video_codec","Codec",80,"badge"), Column("duration_secs","Duration",90,"num")],
                        tags=["video","4k","hdr"]),
                    Category(id="video-4k-av1", name="4K AV1", group="Media", parent_id="video-4k",
                        description="4K files encoded in AV1",
                        icon="⚡", color="#7c3aed",
                        cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.height >= 2160 AND f.video_codec = 'av1' AND f.tenant_id = $tid RETURN f",
                        columns=_base() + [Column("hdr_format","HDR",90,"badge"), Column("overall_bitrate","Bitrate",90,"num")],
                        tags=["video","4k","av1"]),
                ],
            ),

            Category(id="video-1080p", name="1080p HD", group="Media", parent_id="video",
                description="1080p full HD video",
                icon="🖥️", color="#60a5fa",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.height = 1080 AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("video_codec","Codec",80,"badge"), Column("hdr_format","HDR",80,"badge"), Column("duration_secs","Duration",90,"num")],
                tags=["video","1080p"]),

            Category(id="video-hdr", name="HDR / Dolby Vision", group="Media", parent_id="video",
                description="Any video with HDR metadata",
                icon="🌟", color="#a78bfa",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.hdr_format IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("hdr_format","HDR Format",100,"badge"), Column("height","Res",60,"num"), Column("video_codec","Codec",80,"badge")],
                tags=["video","hdr"]),

            Category(id="video-long", name="Long-form (>1h)", group="Media", parent_id="video",
                description="Videos over one hour — movies, TV episodes, recordings",
                icon="🎥", color="#3b82f6",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.duration_secs > 3600 AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("duration_secs","Duration (s)",100,"num"), Column("height","Res",60,"num"), Column("hdr_format","HDR",80,"badge")],
                tags=["video","movies"]),

            # Media matching relationship
            Category(id="video-matched-media", name="Matched to Media DB", group="Media", parent_id="video",
                description="Videos matched to TMDB/IMDB via MATCHED_TO relationship",
                icon="🎞️", color="#4f8ef7",
                cypher="MATCH (f:File)-[:MATCHED_TO]->(m:MediaItem) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("matched_media_title","Matched Title",200,"text"), Column("height","Res",60,"num"), Column("duration_secs","Duration",90,"num")],
                tags=["video","media-matching","ai"]),

            Category(id="video-in-collection", name="In a Collection", group="Media", parent_id="video",
                description="Videos grouped into a Collection via PART_OF",
                icon="📚", color="#6366f1",
                cypher="MATCH (f:File)-[:PART_OF]->(c:Collection) WHERE f.file_category = 'video' AND f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("height","Res",60,"num"), Column("duration_secs","Duration",90,"num")],
                tags=["video","collections"]),

            Category(id="video-ai-summarized", name="AI Analyzed", group="Media", parent_id="video",
                description="Videos processed by LLM enricher",
                icon="🤖", color="#818cf8",
                cypher="MATCH (f:File) WHERE f.file_category = 'video' AND f.summary IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + _ai() + [Column("height","Res",60,"num")],
                tags=["video","ai"]),
        ],
    ),

    Category(
        id="audio", name="Audio", group="Media",
        description="Music, podcasts, audiobooks, and recordings",
        icon="🎵", color="#a78bfa",
        cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [
            Column("artist",        "Artist",    140, "text"),
            Column("album",         "Album",     140, "text"),
            Column("audio_codec",   "Codec",      80, "badge"),
            Column("duration_secs", "Duration",   90, "num"),
            Column("overall_bitrate","Bitrate",   90, "num"),
            Column("sample_rate",   "Sample Rate",90, "num"),
        ],
        tags=["media","audio"],
        subcategories=[
            Category(id="audio-lossless", name="Lossless", group="Media", parent_id="audio",
                description="FLAC, WAV, ALAC, DSD lossless audio",
                icon="💎", color="#8b5cf6",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.audio_codec IN ['flac','pcm_s16le','pcm_s24le','pcm_s32le','alac','dsf','dff'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("artist","Artist",140,"text"), Column("album","Album",140,"text"), Column("bit_depth","Bit Depth",80,"num"), Column("sample_rate","Sample Rate",90,"num")],
                tags=["audio","lossless","hifi"]),
            Category(id="audio-hires", name="Hi-Res (96kHz+)", group="Media", parent_id="audio",
                description="Audio at 96kHz or above",
                icon="🎧", color="#c084fc",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.sample_rate >= 96000 AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("sample_rate","Sample Rate",90,"num"), Column("bit_depth","Bit Depth",80,"num"), Column("audio_codec","Codec",80,"badge")],
                tags=["audio","hires","hifi"]),
            Category(id="audio-tagged", name="Fully Tagged", group="Media", parent_id="audio",
                description="Audio with complete ID3/Vorbis tags",
                icon="🏷️", color="#7c3aed",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND f.artist IS NOT NULL AND f.album IS NOT NULL AND f.title IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("artist","Artist",130,"text"), Column("album","Album",130,"text"), Column("title","Title",160,"text"), Column("year","Year",60,"num"), Column("genre","Genre",90,"badge")],
                tags=["audio","metadata"]),
            Category(id="audio-untagged", name="Untagged", group="Media", parent_id="audio",
                description="Audio missing artist, album, or title",
                icon="❓", color="#6b7280",
                cypher="MATCH (f:File) WHERE f.file_category = 'audio' AND (f.artist IS NULL OR f.album IS NULL) AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("audio_codec","Codec",80,"badge"), Column("duration_secs","Duration",90,"num")],
                tags=["audio","cleanup"]),
            Category(id="audio-matched-media", name="Matched to Media DB", group="Media", parent_id="audio",
                description="Audio matched to a MediaItem via MATCHED_TO",
                icon="📀", color="#a78bfa",
                cypher="MATCH (f:File)-[:MATCHED_TO]->(m:MediaItem) WHERE f.file_category = 'audio' AND f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("artist","Artist",130,"text"), Column("album","Album",130,"text"), Column("audio_codec","Codec",80,"badge")],
                tags=["audio","media-matching"]),
        ],
    ),

    Category(
        id="images", name="Images & Photos", group="Media",
        description="Photos, screenshots, RAW files, and illustrations",
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
            Category(id="images-with-faces", name="Contains Faces", group="Media", parent_id="images",
                description="Images with face detections via CONTAINS_FACE",
                icon="👤", color="#f472b6",
                cypher="MATCH (f:File)-[:CONTAINS_FACE]->(:FaceCluster) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("face_count","Faces",60,"num"), Column("camera_model","Camera",130,"text"), Column("datetime_original","Taken",130,"date")],
                tags=["images","people","faces"],
                subcategories=[
                    Category(id="images-identified-people", name="Identified People", group="Media", parent_id="images-with-faces",
                        description="Images linked to a known Person via SAME_PERSON_AS",
                        icon="✅", color="#ec4899",
                        cypher="MATCH (f:File)-[:CONTAINS_FACE]->(fc:FaceCluster)-[:SAME_PERSON_AS]->(p:Person) WHERE p.known = true AND f.tenant_id = $tid RETURN DISTINCT f",
                        columns=_base() + [Column("face_count","Faces",60,"num"), Column("datetime_original","Taken",130,"date")],
                        tags=["images","people","identified"]),
                    Category(id="images-group-shots", name="Group Photos (3+)", group="Media", parent_id="images-with-faces",
                        description="Images with 3 or more face clusters",
                        icon="👥", color="#db2777",
                        cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.face_count >= 3 AND f.tenant_id = $tid RETURN f",
                        columns=_base() + [Column("face_count","Faces",60,"num"), Column("datetime_original","Taken",130,"date")],
                        tags=["images","people","group"]),
                ]),
            Category(id="images-geotagged", name="Geotagged", group="Media", parent_id="images",
                description="Photos with GPS in EXIF, optionally linked to Location node via LOCATED_AT",
                icon="📍", color="#10b981",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.gps_latitude IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("gps_latitude","Latitude",90,"num"), Column("gps_longitude","Longitude",90,"num"), Column("camera_model","Camera",130,"text"), Column("datetime_original","Taken",130,"date")],
                tags=["images","location","gps"]),
            Category(id="images-located", name="Linked to Location", group="Media", parent_id="images",
                description="Images with a LOCATED_AT → Location node",
                icon="🗺️", color="#059669",
                cypher="MATCH (f:File)-[:LOCATED_AT]->(l:Location) WHERE f.file_category = 'image' AND f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("gps_latitude","Lat",70,"num"), Column("gps_longitude","Lon",70,"num"), Column("datetime_original","Taken",130,"date")],
                tags=["images","location"]),
            Category(id="images-depicts-person", name="Depicts a Person", group="Media", parent_id="images",
                description="Images with a DEPICTS → Person relationship",
                icon="🧑", color="#f472b6",
                cypher="MATCH (f:File)-[:DEPICTS]->(p:Person) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("datetime_original","Taken",130,"date"), Column("camera_model","Camera",130,"text")],
                tags=["images","people"]),
            Category(id="images-in-event", name="From an Event", group="Media", parent_id="images",
                description="Images linked to an Event node via OCCURRED_DURING",
                icon="🎉", color="#34d399",
                cypher="MATCH (f:File)-[:OCCURRED_DURING]->(e:Event) WHERE f.file_category = 'image' AND f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("datetime_original","Taken",130,"date"), Column("camera_model","Camera",130,"text")],
                tags=["images","events"]),
            Category(id="images-raw", name="RAW / HEIF", group="Media", parent_id="images",
                description="RAW camera files (CR2, NEF, ARW) and HEIF/HEIC",
                icon="📷", color="#059669",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.mime_type IN ['image/x-raw','image/heif','image/heic','image/x-canon-cr2','image/x-nikon-nef','image/x-sony-arw'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("camera_make","Make",90,"text"), Column("camera_model","Camera",130,"text"), Column("focal_length","Focal",70,"num"), Column("iso","ISO",60,"num"), Column("aperture","Aperture",80,"num")],
                tags=["images","raw","camera"]),
            Category(id="images-ai-analyzed", name="AI Vision Analyzed", group="Media", parent_id="images",
                description="Images processed by LLaVA with scene/object/mood data",
                icon="🤖", color="#34d399",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.summary IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("summary","AI Description",220,"text"), Column("scene_type","Scene",90,"badge"), Column("sentiment","Mood",90,"badge"), Column("people_count","People",60,"num"), Column("text_visible","Visible Text",140,"text")],
                tags=["images","ai","vision"]),
            Category(id="images-screenshots", name="Screenshots", group="Media", parent_id="images",
                description="Screen captures identified by LLaVA (scene_type=screenshot)",
                icon="🖥️", color="#14b8a6",
                cypher="MATCH (f:File) WHERE f.file_category = 'image' AND f.scene_type = 'screenshot' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("text_visible","Visible Text",200,"text"), Column("width","W",55,"num"), Column("height","H",55,"num")],
                tags=["images","screenshots"]),
            Category(id="images-duplicates", name="Duplicate Images", group="Media", parent_id="images",
                description="Images linked via DUPLICATE_OF",
                icon="♻️", color="#6b7280",
                cypher="MATCH (f:File)-[:DUPLICATE_OF]->(g:File) WHERE f.file_category = 'image' AND f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("sha256","Hash",160,"mono"), Column("width","W",55,"num"), Column("height","H",55,"num")],
                tags=["images","duplicates","storage"]),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Documents & Text
    # ═══════════════════════════════════════════════════════════════════════════

    Category(
        id="documents", name="Documents", group="Documents & Text",
        description="PDFs, Office files, text docs, spreadsheets",
        icon="📄", color="#fbbf24",
        cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("document_type","Type",90,"badge"), Column("author","Author",130,"text"), Column("page_count","Pages",65,"num"), Column("language","Language",80,"badge"), Column("summary","AI Summary",220,"text")],
        tags=["documents"],
        subcategories=[
            Category(id="docs-pdf", name="PDF", group="Documents & Text", parent_id="documents",
                description="PDF documents",
                icon="📕", color="#f59e0b",
                cypher="MATCH (f:File) WHERE f.mime_type = 'application/pdf' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","Author",130,"text"), Column("page_count","Pages",65,"num"), Column("is_encrypted","Encrypted",80,"bool"), Column("word_count","Words",75,"num"), Column("summary","AI Summary",220,"text")],
                tags=["documents","pdf"]),
            Category(id="docs-office", name="Office Docs", group="Documents & Text", parent_id="documents",
                description="Word, Excel, PowerPoint files",
                icon="💼", color="#f97316",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.mime_type IN ['application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/msword','application/vnd.ms-excel','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/vnd.ms-powerpoint','application/vnd.openxmlformats-officedocument.presentationml.presentation'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","Author",130,"text"), Column("title","Title",180,"text"), Column("word_count","Words",75,"num"), Column("summary","AI Summary",220,"text")],
                tags=["documents","office"]),

            # AI document type classifications
            Category(id="docs-contracts", name="Contracts", group="Documents & Text", parent_id="documents",
                description="AI-classified contracts (document_type=contract)",
                icon="📝", color="#d97706",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.document_type = 'contract' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("author","Author",130,"text"), Column("page_count","Pages",65,"num"), Column("entities_people","People",180,"text"), Column("entities_organizations","Organizations",200,"text"), Column("summary","AI Summary",220,"text")],
                tags=["documents","contracts","legal","ai"]),
            Category(id="docs-invoices", name="Invoices", group="Documents & Text", parent_id="documents",
                description="AI-classified invoices (document_type=invoice)",
                icon="🧾", color="#b45309",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.document_type = 'invoice' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("entities_organizations","Organizations",200,"text"), Column("summary","AI Summary",220,"text")],
                tags=["documents","invoices","financial","ai"]),
            Category(id="docs-reports", name="Reports", group="Documents & Text", parent_id="documents",
                description="AI-classified reports (document_type=report)",
                icon="📊", color="#92400e",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.document_type = 'report' AND f.tenant_id = $tid RETURN f",
                columns=_base() + _ai() + [Column("page_count","Pages",65,"num"), Column("entities_topics","Topics",200,"text")],
                tags=["documents","reports","ai"]),
            Category(id="docs-manuals", name="Manuals", group="Documents & Text", parent_id="documents",
                description="AI-classified manuals (document_type=manual)",
                icon="📖", color="#78350f",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.document_type = 'manual' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("page_count","Pages",65,"num"), Column("language","Language",80,"badge"), Column("summary","AI Summary",220,"text")],
                tags=["documents","manuals","ai"]),

            # Mentions relationships
            Category(id="docs-mentions-person", name="Mentions People", group="Documents & Text", parent_id="documents",
                description="Documents with MENTIONS → Person relationships",
                icon="👤", color="#f472b6",
                cypher="MATCH (f:File)-[:MENTIONS]->(p:Person) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("document_type","Type",90,"badge"), Column("entities_people","People",200,"text"), Column("summary","AI Summary",220,"text")],
                tags=["documents","people","ai"]),
            Category(id="docs-mentions-org", name="Mentions Organizations", group="Documents & Text", parent_id="documents",
                description="Documents with MENTIONS → Organization relationships",
                icon="🏢", color="#fbbf24",
                cypher="MATCH (f:File)-[:MENTIONS]->(o:Organization) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("document_type","Type",90,"badge"), Column("entities_organizations","Organizations",220,"text"), Column("summary","AI Summary",220,"text")],
                tags=["documents","organizations","ai"]),
            Category(id="docs-mentions-location", name="Mentions Locations", group="Documents & Text", parent_id="documents",
                description="Documents with MENTIONS → Location relationships",
                icon="📍", color="#34d399",
                cypher="MATCH (f:File)-[:MENTIONS]->(l:Location) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("document_type","Type",90,"badge"), Column("entities_locations","Locations",200,"text"), Column("summary","AI Summary",220,"text")],
                tags=["documents","locations","ai"]),

            # PII
            Category(id="docs-pii", name="Contains PII", group="Documents & Text", parent_id="documents",
                description="Documents with detected personally identifiable information",
                icon="🔒", color="#ef4444",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.pii_detected = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + _pii() + [Column("document_type","Type",90,"badge"), Column("page_count","Pages",65,"num")],
                tags=["documents","pii","compliance","gdpr"],
                subcategories=[
                    Category(id="docs-pii-high", name="High Sensitivity", group="Documents & Text", parent_id="docs-pii",
                        description="High-sensitivity PII documents",
                        icon="🔴", color="#dc2626",
                        cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.pii_detected = true AND f.sensitivity_level = 'high' AND f.tenant_id = $tid RETURN f",
                        columns=_base() + _pii() + [Column("document_type","Type",90,"badge"), Column("summary","AI Summary",220,"text")],
                        tags=["documents","pii","compliance","gdpr","high-sensitivity"]),
                ]),

            Category(id="docs-references-file", name="References Other Files", group="Documents & Text", parent_id="documents",
                description="Documents with REFERENCES → File relationships",
                icon="🔗", color="#fbbf24",
                cypher="MATCH (f:File)-[:REFERENCES]->(g:File) WHERE f.file_category = 'document' AND f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("document_type","Type",90,"badge"), Column("summary","AI Summary",220,"text")],
                tags=["documents","references"]),
            Category(id="docs-in-collection", name="In a Collection", group="Documents & Text", parent_id="documents",
                description="Documents grouped via PART_OF → Collection",
                icon="📚", color="#f59e0b",
                cypher="MATCH (f:File)-[:PART_OF]->(c:Collection) WHERE f.file_category = 'document' AND f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("document_type","Type",90,"badge"), Column("author","Author",130,"text")],
                tags=["documents","collections"]),
            Category(id="docs-tagged", name="Tagged", group="Documents & Text", parent_id="documents",
                description="Documents with TAGGED_WITH → Tag relationships",
                icon="🏷️", color="#d97706",
                cypher="MATCH (f:File)-[:TAGGED_WITH]->(t:Tag) WHERE f.file_category = 'document' AND f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("document_type","Type",90,"badge"), Column("summary","AI Summary",220,"text")],
                tags=["documents","tags"]),
            Category(id="docs-multilingual", name="Non-English", group="Documents & Text", parent_id="documents",
                description="Documents in languages other than English",
                icon="🌐", color="#fbbf24",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.language IS NOT NULL AND f.language <> 'en' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("language","Language",80,"badge"), Column("document_type","Type",90,"badge"), Column("summary","AI Summary",220,"text")],
                tags=["documents","multilingual","ai"]),
            Category(id="docs-has-action-items", name="Has Action Items", group="Documents & Text", parent_id="documents",
                description="Documents with AI-detected tasks or action items",
                icon="✅", color="#d97706",
                cypher="MATCH (f:File) WHERE f.file_category = 'document' AND f.action_items IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("action_items","Action Items",300,"text"), Column("document_type","Type",90,"badge")],
                tags=["documents","ai","actions"]),
        ],
    ),

    Category(
        id="emails", name="Email", group="Documents & Text",
        description=".eml, .msg, and .mbox files",
        icon="✉️", color="#38bdf8",
        cypher="MATCH (f:File) WHERE f.file_category = 'email' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("author","From",140,"text"), Column("title","Subject",200,"text"), Column("summary","AI Summary",220,"text"), Column("sentiment","Sentiment",90,"badge"), Column("pii_detected","PII",60,"bool")],
        tags=["email","documents"],
        subcategories=[
            Category(id="emails-pii", name="Contains PII", group="Documents & Text", parent_id="emails",
                description="Emails with detected personal data",
                icon="🔒", color="#0ea5e9",
                cypher="MATCH (f:File) WHERE f.file_category = 'email' AND f.pii_detected = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + _pii() + [Column("title","Subject",200,"text")],
                tags=["email","pii","compliance"]),
            Category(id="emails-action-items", name="Has Action Items", group="Documents & Text", parent_id="emails",
                description="Emails with AI-detected tasks",
                icon="✅", color="#0284c7",
                cypher="MATCH (f:File) WHERE f.file_category = 'email' AND f.action_items IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("title","Subject",200,"text"), Column("action_items","Action Items",260,"text"), Column("sentiment","Sentiment",90,"badge")],
                tags=["email","ai","actions"]),
            Category(id="emails-mentions-people", name="Mentions People", group="Documents & Text", parent_id="emails",
                description="Emails with MENTIONS → Person",
                icon="👤", color="#38bdf8",
                cypher="MATCH (f:File)-[:MENTIONS]->(p:Person) WHERE f.file_category = 'email' AND f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("title","Subject",200,"text"), Column("entities_people","People",200,"text")],
                tags=["email","people","ai"]),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Code & Config
    # ═══════════════════════════════════════════════════════════════════════════

    Category(
        id="code", name="Source Code", group="Code & Config",
        description="Programming files, scripts, and configuration",
        icon="💻", color="#22d3ee",
        cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("code_language","Language",100,"badge"), Column("line_count","Lines",70,"num"), Column("function_count","Functions",80,"num"), Column("contains_secrets","Secrets",80,"bool"), Column("summary","AI Summary",200,"text")],
        tags=["code"],
        subcategories=[
            Category(id="code-secrets", name="Contains Secrets", group="Code & Config", parent_id="code",
                description="Source files with hardcoded credentials (MENTIONS → Organization/key pattern)",
                icon="🔑", color="#f87171",
                cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.contains_secrets = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + _secrets() + [Column("code_language","Language",100,"badge"), Column("line_count","Lines",70,"num")],
                tags=["code","security","secrets"]),
            Category(id="code-security-concerns", name="Security Issues", group="Code & Config", parent_id="code",
                description="Code with AI-detected security concerns",
                icon="⚠️", color="#fb923c",
                cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.security_concerns IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("code_language","Language",100,"badge"), Column("security_concerns","Issues",240,"text"), Column("code_quality","Quality",90,"badge")],
                tags=["code","security","ai"]),
            Category(id="code-poor-quality", name="Poor Quality", group="Code & Config", parent_id="code",
                description="Code rated poor by AI analysis",
                icon="💢", color="#f59e0b",
                cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.code_quality = 'poor' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("code_language","Language",100,"badge"), Column("line_count","Lines",70,"num"), Column("summary","AI Summary",200,"text")],
                tags=["code","quality","ai"]),
            Category(id="code-config", name="Config Files", group="Code & Config", parent_id="code",
                description=".env, YAML, TOML, JSON, INI configuration files",
                icon="⚙️", color="#06b6d4",
                cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.code_language IN ['env','YAML','TOML','JSON','INI'] AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("code_language","Format",90,"badge"), Column("contains_secrets","Secrets",80,"bool"), Column("line_count","Lines",70,"num")],
                tags=["code","config"]),
            Category(id="code-tests", name="Test Files", group="Code & Config", parent_id="code",
                description="Code identified as test suites by AI",
                icon="🧪", color="#2dd4bf",
                cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.has_tests = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("code_language","Language",100,"badge"), Column("framework","Framework",110,"badge"), Column("line_count","Lines",70,"num")],
                tags=["code","tests"]),
            Category(id="code-licensed", name="Has License", group="Code & Config", parent_id="code",
                description="Code files with LICENSED_UNDER → License",
                icon="📜", color="#22d3ee",
                cypher="MATCH (f:File)-[:LICENSED_UNDER]->(l:License) WHERE f.file_category = 'code' AND f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("code_language","Language",100,"badge"), Column("line_count","Lines",70,"num")],
                tags=["code","license"]),
            Category(id="code-similar", name="Similar to Other Files", group="Code & Config", parent_id="code",
                description="Code files connected via SIMILAR_TO",
                icon="🔗", color="#06b6d4",
                cypher="MATCH (f:File)-[:SIMILAR_TO]->(g:File) WHERE f.file_category = 'code' AND f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("code_language","Language",100,"badge"), Column("summary","AI Summary",200,"text")],
                tags=["code","similar","ai"]),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Software
    # ═══════════════════════════════════════════════════════════════════════════

    Category(
        id="executables", name="Executables & Libraries", group="Software",
        description="PE, ELF, Mach-O binaries and libraries",
        icon="⚙️", color="#8b5cf6",
        cypher="MATCH (f:File) WHERE f.file_category = 'executable' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("binary_format","Format",70,"badge"), Column("product_name","Product",140,"text"), Column("company_name","Vendor",130,"text"), Column("file_version","Version",90,"text"), Column("signed","Signed",70,"bool"), Column("eol_status","EOL",80,"badge")],
        tags=["software","executables"],
        subcategories=[
            Category(id="exe-eol", name="End-of-Life", group="Software", parent_id="executables",
                description="Software past support end date",
                icon="💀", color="#f87171",
                cypher="MATCH (f:File) WHERE f.eol_status = 'eol' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_version","Version",90,"text"), Column("company_name","Vendor",130,"text"), Column("eol_date","EOL Date",110,"date")],
                tags=["software","eol","compliance"]),
            Category(id="exe-unsigned", name="Unsigned", group="Software", parent_id="executables",
                description="Executables without valid code signature",
                icon="🚫", color="#fbbf24",
                cypher="MATCH (f:File) WHERE f.file_category = 'executable' AND f.signed = false AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("binary_format","Format",70,"badge"), Column("file_version","Version",90,"text"), Column("company_name","Vendor",130,"text")],
                tags=["software","security"]),
            Category(id="exe-high-risk", name="High Risk (AI)", group="Software", parent_id="executables",
                description="Binaries rated high risk by AI analysis",
                icon="🚨", color="#ef4444",
                cypher="MATCH (f:File) WHERE f.file_category = 'executable' AND f.risk_assessment = 'high' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("risk_assessment","Risk",90,"badge"), Column("binary_format","Format",70,"badge"), Column("signed","Signed",70,"bool"), Column("summary","AI Summary",180,"text")],
                tags=["software","security","ai"]),
            Category(id="exe-packed", name="Packed / High Entropy", group="Software", parent_id="executables",
                description="Binaries with high entropy (possibly packed or obfuscated)",
                icon="🎭", color="#7c3aed",
                cypher="MATCH (f:File) WHERE f.is_packed = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("entropy","Entropy",80,"num"), Column("signed","Signed",70,"bool"), Column("binary_format","Format",70,"badge")],
                tags=["software","security"]),
            Category(id="exe-with-vulnerabilities", name="Has CVEs", group="Software", parent_id="executables",
                description="Executables linked to Vulnerability via IS_APPLICATION → HAS_VULNERABILITY",
                icon="🛡️", color="#f87171",
                cypher="MATCH (f:File)-[:IS_APPLICATION]->(a:Application)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("file_version","Version",90,"text"), Column("company_name","Vendor",130,"text"), Column("cve_count","CVEs",60,"num")],
                tags=["software","cve","security"]),
            Category(id="exe-signed-by", name="Certificate Known", group="Software", parent_id="executables",
                description="Executables with SIGNED_BY → Certificate relationship",
                icon="🏅", color="#4ade80",
                cypher="MATCH (f:File)-[:IS_BINARY]->(b:Binary)-[:SIGNED_BY]->(c:Certificate) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("binary_format","Format",70,"badge"), Column("company_name","Vendor",130,"text"), Column("signature_valid","Sig Valid",90,"bool")],
                tags=["software","certificates"]),
            Category(id="exe-depends-on", name="Has Dependencies", group="Software", parent_id="executables",
                description="Executables with DEPENDS_ON → Dependency graph",
                icon="🧩", color="#8b5cf6",
                cypher="MATCH (f:File)-[:IS_BINARY]->(b:Binary)-[:DEPENDS_ON]->(d:Dependency) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("binary_format","Format",70,"badge"), Column("file_version","Version",90,"text")],
                tags=["software","dependencies"]),
            Category(id="exe-made-by", name="Vendor Known", group="Software", parent_id="executables",
                description="Executables linked to a Vendor node via MADE_BY",
                icon="🏭", color="#a78bfa",
                cypher="MATCH (f:File)-[:IS_APPLICATION]->(a:Application)-[:MADE_BY]->(v:Vendor) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("company_name","Vendor",130,"text"), Column("file_version","Version",90,"text"), Column("eol_status","EOL",80,"badge")],
                tags=["software","vendor"]),
            Category(id="exe-drivers", name="Drivers", group="Software", parent_id="executables",
                description="Kernel drivers and system modules (.sys / ai_category=driver)",
                icon="🔧", color="#6d28d9",
                cypher="MATCH (f:File) WHERE (f.name ENDS WITH '.sys' OR f.ai_category = 'driver') AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_version","Version",90,"text"), Column("signed","Signed",70,"bool"), Column("company_name","Vendor",130,"text")],
                tags=["software","drivers"]),
        ],
    ),

    Category(
        id="archives", name="Archives", group="Software",
        description="ZIP, RAR, 7z, tar, ISO and other compressed files",
        icon="📦", color="#fb923c",
        cypher="MATCH (f:File) WHERE f.file_category = 'archive' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("file_count_in_archive","Files",70,"num"), Column("compression_ratio","Ratio",70,"num"), Column("contains_executables","Has .exe",80,"bool")],
        tags=["archives"],
        subcategories=[
            Category(id="archives-with-exe", name="Contains Executables", group="Software", parent_id="archives",
                description="Archives with embedded .exe, .dll, .bat, .ps1",
                icon="⚠️", color="#f97316",
                cypher="MATCH (f:File) WHERE f.file_category = 'archive' AND f.contains_executables = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_count_in_archive","Files",70,"num"), Column("size","Size",80,"size")],
                tags=["archives","security"]),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Security
    # ═══════════════════════════════════════════════════════════════════════════

    Category(
        id="certificates", name="Certificates & Keys", group="Security",
        description="TLS, code signing, CA certificates, and private keys",
        icon="🏅", color="#4ade80",
        cypher="MATCH (f:File) WHERE f.file_category IN ['certificate','private_key'] AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("cert_subject","Subject",200,"text"), Column("cert_issuer","Issuer",160,"text"), Column("cert_valid_to","Expires",130,"date"), Column("cert_is_expired","Expired",80,"bool"), Column("days_until_expiry","Days Left",80,"num"), Column("is_self_signed","Self-Signed",90,"bool")],
        tags=["certificates","security"],
        subcategories=[
            Category(id="certs-expired", name="Expired", group="Security", parent_id="certificates",
                description="Certificates past expiry date",
                icon="❌", color="#f87171",
                cypher="MATCH (f:File) WHERE f.cert_is_expired = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("cert_subject","Subject",200,"text"), Column("cert_valid_to","Expired",130,"date"), Column("cert_issuer","Issuer",160,"text")],
                tags=["certificates","security"]),
            Category(id="certs-expiring-30", name="Expiring < 30 days", group="Security", parent_id="certificates",
                description="Certificates expiring within 30 days",
                icon="⏰", color="#fbbf24",
                cypher="MATCH (f:File) WHERE f.file_category = 'certificate' AND f.days_until_expiry < 30 AND f.days_until_expiry >= 0 AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("cert_subject","Subject",200,"text"), Column("days_until_expiry","Days Left",80,"num"), Column("cert_valid_to","Expires",130,"date")],
                tags=["certificates","security"]),
            Category(id="certs-self-signed", name="Self-Signed", group="Security", parent_id="certificates",
                description="Certificates issued by their own key",
                icon="🔏", color="#86efac",
                cypher="MATCH (f:File) WHERE f.file_category = 'certificate' AND f.is_self_signed = true AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("cert_subject","Subject",200,"text"), Column("days_until_expiry","Days Left",80,"num"), Column("cert_key_algorithm","Algorithm",100,"badge")],
                tags=["certificates","security"]),
            Category(id="private-keys", name="Private Keys", group="Security", parent_id="certificates",
                description="RSA, EC, and other private key files",
                icon="🔐", color="#22c55e",
                cypher="MATCH (f:File) WHERE f.file_category = 'private_key' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("key_type","Key Type",100,"badge"), Column("key_bits","Key Size",80,"num"), Column("passphrase_protected","Protected",90,"bool")],
                tags=["certificates","keys","security"]),
            Category(id="certs-used-by", name="Used by Software", group="Security", parent_id="certificates",
                description="Certificate nodes referenced by SIGNED_BY relationships",
                icon="🔗", color="#4ade80",
                cypher="MATCH (:Application)-[:SIGNED_BY]->(c:Certificate) WHERE c.tenant_id = $tid RETURN c AS f",
                columns=[Column("cert_subject","Subject",200,"text"), Column("cert_issuer","Issuer",160,"text"), Column("cert_valid_to","Expires",130,"date"), Column("is_self_signed","Self-Signed",90,"bool")],
                tags=["certificates","software"]),
        ],
    ),

    Category(
        id="secrets", name="Exposed Secrets", group="Security",
        description="Files with hardcoded API keys, passwords, or tokens",
        icon="🔑", color="#f87171",
        cypher="MATCH (f:File) WHERE f.contains_secrets = true AND f.tenant_id = $tid RETURN f",
        columns=_base() + _secrets() + [Column("file_category","File Type",90,"badge"), Column("code_language","Language",100,"badge"), Column("sensitivity_level","Severity",110,"badge")],
        tags=["security","secrets"],
        subcategories=[
            Category(id="secrets-api-keys", name="API Keys", group="Security", parent_id="secrets",
                description="Files with API key patterns detected",
                icon="🗝️", color="#f87171",
                cypher="MATCH (f:File) WHERE f.secret_types CONTAINS 'api_key' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("code_language","Language",100,"badge"), Column("sensitivity_level","Severity",110,"badge")],
                tags=["security","secrets","api-key"]),
            Category(id="secrets-passwords", name="Passwords", group="Security", parent_id="secrets",
                description="Files with password or credential patterns",
                icon="🔓", color="#ef4444",
                cypher="MATCH (f:File) WHERE (f.secret_types CONTAINS 'password' OR f.secret_types CONTAINS 'passwd') AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_category","Type",90,"badge"), Column("code_language","Language",100,"badge")],
                tags=["security","secrets","passwords"]),
            Category(id="secrets-tokens", name="Auth Tokens", group="Security", parent_id="secrets",
                description="Files with bearer tokens or auth tokens",
                icon="🎟️", color="#fca5a5",
                cypher="MATCH (f:File) WHERE (f.secret_types CONTAINS 'token' OR f.secret_types CONTAINS 'bearer') AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_category","Type",90,"badge"), Column("code_language","Language",100,"badge")],
                tags=["security","secrets","tokens"]),
            Category(id="secrets-private-keys-in-code", name="Private Keys in Code", group="Security", parent_id="secrets",
                description="Source files containing embedded private key material",
                icon="🔐", color="#dc2626",
                cypher="MATCH (f:File) WHERE f.file_category = 'code' AND f.secret_types CONTAINS 'private_key' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("code_language","Language",100,"badge"), Column("line_count","Lines",70,"num")],
                tags=["security","secrets","keys"]),
        ],
    ),

    Category(
        id="pii", name="Personal Data (PII)", group="Security",
        description="Files with detected personally identifiable information",
        icon="🔒", color="#fb7185",
        cypher="MATCH (f:File) WHERE f.pii_detected = true AND f.tenant_id = $tid RETURN f",
        columns=_base() + _pii() + [Column("file_category","Type",90,"badge")],
        tags=["security","pii","compliance","gdpr"],
        subcategories=[
            Category(id="pii-high", name="High Sensitivity", group="Security", parent_id="pii",
                description="High-sensitivity PII (SSN, financial, health records)",
                icon="🔴", color="#ef4444",
                cypher="MATCH (f:File) WHERE f.pii_detected = true AND f.sensitivity_level = 'high' AND f.tenant_id = $tid RETURN f",
                columns=_base() + _pii() + [Column("file_category","Type",90,"badge"), Column("summary","AI Summary",220,"text")],
                tags=["pii","compliance","gdpr","high-sensitivity"]),
            Category(id="pii-emails-phones", name="Emails & Phones", group="Security", parent_id="pii",
                description="Files containing email addresses or phone numbers",
                icon="📞", color="#f43f5e",
                cypher="MATCH (f:File) WHERE (f.pii_types CONTAINS 'email' OR f.pii_types CONTAINS 'phone') AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("pii_types","PII Types",160,"text"), Column("file_category","Type",90,"badge")],
                tags=["pii","compliance"]),
            Category(id="pii-ssn", name="SSN / National ID", group="Security", parent_id="pii",
                description="Files containing social security or national ID numbers",
                icon="🪪", color="#dc2626",
                cypher="MATCH (f:File) WHERE f.pii_types CONTAINS 'ssn' AND f.tenant_id = $tid RETURN f",
                columns=_base() + _pii() + [Column("file_category","Type",90,"badge")],
                tags=["pii","compliance","gdpr"]),
        ],
    ),

    Category(
        id="vulnerabilities", name="Vulnerabilities (CVE)", group="Security",
        description="Applications with known CVEs from NVD/OSV/OSS-Index",
        icon="🛡️", color="#f87171",
        cypher="MATCH (a:Application)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE a.tenant_id = $tid RETURN DISTINCT a AS f",
        columns=[Column("name","Name",200,"text"), Column("version_string","Version",90,"text"), Column("eol_status","EOL",80,"badge"), Column("cve_count","CVEs",60,"num"), Column("critical_cve_count","Critical",70,"num"), Column("source_connector","Source",120,"badge")],
        tags=["security","cve","vulnerabilities"],
        subcategories=[
            Category(id="cve-critical", name="Critical Severity", group="Security", parent_id="vulnerabilities",
                description="Applications with CVSS critical (9.0+) vulnerabilities",
                icon="🚨", color="#dc2626",
                cypher="MATCH (a:Application)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE v.cvss_severity = 'critical' AND a.tenant_id = $tid RETURN DISTINCT a AS f",
                columns=[Column("name","Name",200,"text"), Column("version_string","Version",90,"text"), Column("critical_cve_count","Critical CVEs",90,"num")],
                tags=["security","cve","critical"]),
            Category(id="cve-exploited", name="Actively Exploited", group="Security", parent_id="vulnerabilities",
                description="CVEs marked as actively exploited in the wild",
                icon="🔥", color="#b91c1c",
                cypher="MATCH (a:Application)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE v.actively_exploited = true AND a.tenant_id = $tid RETURN DISTINCT a AS f",
                columns=[Column("name","Name",200,"text"), Column("version_string","Version",90,"text"), Column("cve_count","CVEs",60,"num")],
                tags=["security","cve","exploited"]),
            Category(id="cve-with-exploit", name="Exploit Available", group="Security", parent_id="vulnerabilities",
                description="CVEs where a public exploit exists",
                icon="💣", color="#ef4444",
                cypher="MATCH (a:Application)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE v.exploit_available = true AND a.tenant_id = $tid RETURN DISTINCT a AS f",
                columns=[Column("name","Name",200,"text"), Column("version_string","Version",90,"text"), Column("cve_count","CVEs",60,"num")],
                tags=["security","cve","exploit"]),
            Category(id="cve-dep-chain", name="Vulnerable Dependencies", group="Security", parent_id="vulnerabilities",
                description="Dependencies linked to Vulnerabilities via DEPENDS_ON → HAS_VULNERABILITY",
                icon="🧩", color="#f87171",
                cypher="MATCH (a:Application)-[:DEPENDS_ON]->(d:Dependency)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE a.tenant_id = $tid RETURN DISTINCT a AS f",
                columns=[Column("name","Name",200,"text"), Column("version_string","Version",90,"text")],
                tags=["security","cve","dependencies"]),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: People & Identity
    # ═══════════════════════════════════════════════════════════════════════════

    Category(
        id="people", name="People", group="People & Identity",
        description="People identified via face recognition or document entity extraction",
        icon="👤", color="#f472b6",
        cypher="MATCH (p:Person) WHERE p.tenant_id = $tid RETURN p AS f",
        columns=[Column("name","Name",180,"text"), Column("known","Identified",90,"bool"), Column("face_count","Appearances",100,"num"), Column("first_seen","First Seen",130,"date"), Column("last_seen","Last Seen",130,"date")],
        tags=["people"],
        subcategories=[
            Category(id="people-identified", name="Identified", group="People & Identity", parent_id="people",
                description="People with a confirmed name (known=true)",
                icon="✅", color="#ec4899",
                cypher="MATCH (p:Person) WHERE p.known = true AND p.tenant_id = $tid RETURN p AS f",
                columns=[Column("name","Name",180,"text"), Column("face_count","Appearances",100,"num"), Column("first_seen","First Seen",130,"date"), Column("last_seen","Last Seen",130,"date")],
                tags=["people","identified"]),
            Category(id="people-unknown-clusters", name="Unidentified Clusters", group="People & Identity", parent_id="people",
                description="Face clusters not yet linked to a Person (SAME_PERSON_AS pending)",
                icon="👥", color="#f472b6",
                cypher="MATCH (fc:FaceCluster) WHERE NOT (fc)-[:SAME_PERSON_AS]->(:Person) AND fc.tenant_id = $tid RETURN fc AS f",
                columns=[Column("cluster_id","Cluster ID",120,"mono"), Column("face_count","Appearances",100,"num"), Column("first_seen","First Seen",130,"date")],
                tags=["people","faces","unidentified"]),
            Category(id="people-entity-extracted", name="Mentioned in Docs", group="People & Identity", parent_id="people",
                description="People extracted from documents via MENTIONS (AI entity recognition)",
                icon="📝", color="#db2777",
                cypher="MATCH (f:File)-[:MENTIONS]->(p:Person) WHERE f.tenant_id = $tid RETURN DISTINCT p AS f",
                columns=[Column("name","Name",180,"text"), Column("known","Identified",90,"bool"), Column("face_count","Appearances",100,"num")],
                tags=["people","ai","entities"]),
            Category(id="people-depicts", name="Depicted in Images", group="People & Identity", parent_id="people",
                description="People who appear in images via DEPICTS relationships",
                icon="🖼️", color="#f43f5e",
                cypher="MATCH (f:File)-[:DEPICTS]->(p:Person) WHERE f.tenant_id = $tid RETURN DISTINCT p AS f",
                columns=[Column("name","Name",180,"text"), Column("known","Identified",90,"bool"), Column("face_count","Appearances",100,"num")],
                tags=["people","images"]),
        ],
    ),

    Category(
        id="organizations", name="Organizations", group="People & Identity",
        description="Organizations extracted from documents by AI entity recognition",
        icon="🏢", color="#fb923c",
        cypher="MATCH (o:Organization) WHERE o.tenant_id = $tid RETURN o AS f",
        columns=[Column("name","Name",200,"text"), Column("type","Type",100,"badge"), Column("source_connector","Source",120,"badge")],
        tags=["organizations","ai","entities"],
        subcategories=[
            Category(id="orgs-mentioned-in-docs", name="In Documents", group="People & Identity", parent_id="organizations",
                description="Organizations referenced via MENTIONS from documents",
                icon="📄", color="#f97316",
                cypher="MATCH (f:File)-[:MENTIONS]->(o:Organization) WHERE f.tenant_id = $tid RETURN DISTINCT o AS f",
                columns=[Column("name","Name",200,"text"), Column("type","Type",100,"badge")],
                tags=["organizations","documents","ai"]),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Knowledge Graph
    # ═══════════════════════════════════════════════════════════════════════════

    Category(
        id="locations", name="Locations", group="Knowledge Graph",
        description="Geographic locations extracted from files or GPS data",
        icon="📍", color="#34d399",
        cypher="MATCH (l:Location) WHERE l.tenant_id = $tid RETURN l AS f",
        columns=[Column("name","Name",200,"text"), Column("city","City",120,"text"), Column("country","Country",100,"text"), Column("place_type","Type",90,"badge"), Column("latitude","Lat",70,"num"), Column("longitude","Lon",70,"num")],
        tags=["locations","geography"],
        subcategories=[
            Category(id="locations-with-files", name="Has Associated Files", group="Knowledge Graph", parent_id="locations",
                description="Locations linked to files via LOCATED_AT",
                icon="📂", color="#10b981",
                cypher="MATCH (f:File)-[:LOCATED_AT]->(l:Location) WHERE l.tenant_id = $tid RETURN DISTINCT l AS f",
                columns=[Column("name","Name",200,"text"), Column("city","City",120,"text"), Column("country","Country",100,"text"), Column("place_type","Type",90,"badge")],
                tags=["locations","files"]),
            Category(id="locations-nested", name="Part of Larger Area", group="Knowledge Graph", parent_id="locations",
                description="Locations with WITHIN → Location hierarchy",
                icon="🗺️", color="#059669",
                cypher="MATCH (l:Location)-[:WITHIN]->(p:Location) WHERE l.tenant_id = $tid RETURN DISTINCT l AS f",
                columns=[Column("name","Name",200,"text"), Column("city","City",120,"text"), Column("country","Country",100,"text")],
                tags=["locations","geography"]),
        ],
    ),

    Category(
        id="topics", name="Topics", group="Knowledge Graph",
        description="Semantic topics extracted from documents by AI",
        icon="🏷️", color="#a3e635",
        cypher="MATCH (t:Topic) WHERE t.tenant_id = $tid RETURN t AS f",
        columns=[Column("name","Topic Name",200,"text"), Column("source_connector","Source",120,"badge")],
        tags=["topics","ai","knowledge"],
        subcategories=[
            Category(id="topics-in-documents", name="Documented Topics", group="Knowledge Graph", parent_id="topics",
                description="Topics referenced in documents via MENTIONS",
                icon="📄", color="#84cc16",
                cypher="MATCH (f:File)-[:MENTIONS]->(t:Topic) WHERE f.tenant_id = $tid RETURN DISTINCT t AS f",
                columns=[Column("name","Topic",200,"text")],
                tags=["topics","documents","ai"]),
        ],
    ),

    Category(
        id="events", name="Events", group="Knowledge Graph",
        description="Events that files are linked to via OCCURRED_DURING",
        icon="🎉", color="#fb923c",
        cypher="MATCH (e:Event) WHERE e.tenant_id = $tid RETURN e AS f",
        columns=[Column("name","Event Name",200,"text"), Column("start_time","Start",130,"date"), Column("end_time","End",130,"date")],
        tags=["events","knowledge"],
    ),

    Category(
        id="collections", name="Collections", group="Knowledge Graph",
        description="Named file groupings created via PART_OF relationships",
        icon="📚", color="#f59e0b",
        cypher="MATCH (c:Collection) WHERE c.tenant_id = $tid RETURN c AS f",
        columns=[Column("name","Name",200,"text"), Column("type","Type",100,"badge"), Column("description","Description",260,"text")],
        tags=["collections","knowledge"],
    ),

    Category(
        id="media-items", name="Media Items (TMDB/IMDB)", group="Knowledge Graph",
        description="Movies, TV shows, and albums matched via MATCHED_TO",
        icon="🎞️", color="#818cf8",
        cypher="MATCH (m:MediaItem) WHERE m.tenant_id = $tid RETURN m AS f",
        columns=[Column("title","Title",220,"text"), Column("type","Type",80,"badge"), Column("year","Year",60,"num"), Column("genre","Genre",100,"badge"), Column("director","Director",140,"text"), Column("rating","Rating",70,"num")],
        tags=["media","media-matching"],
        subcategories=[
            Category(id="media-movies", name="Movies", group="Knowledge Graph", parent_id="media-items",
                description="Movie MediaItems matched to video files",
                icon="🎬", color="#6366f1",
                cypher="MATCH (m:MediaItem) WHERE m.type = 'movie' AND m.tenant_id = $tid RETURN m AS f",
                columns=[Column("title","Title",220,"text"), Column("year","Year",60,"num"), Column("genre","Genre",100,"badge"), Column("director","Director",140,"text"), Column("rating","Rating",70,"num")],
                tags=["media","movies"]),
            Category(id="media-tv", name="TV Shows", group="Knowledge Graph", parent_id="media-items",
                description="TV show/series MediaItems",
                icon="📺", color="#7c3aed",
                cypher="MATCH (m:MediaItem) WHERE m.type = 'tv' AND m.tenant_id = $tid RETURN m AS f",
                columns=[Column("title","Title",220,"text"), Column("year","Year",60,"num"), Column("genre","Genre",100,"badge"), Column("rating","Rating",70,"num")],
                tags=["media","tv"]),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Software Graph
    # ═══════════════════════════════════════════════════════════════════════════

    Category(
        id="applications", name="Applications", group="Software Graph",
        description="Installed applications tracked as Application nodes",
        icon="🖥️", color="#8b5cf6",
        cypher="MATCH (a:Application) WHERE a.tenant_id = $tid RETURN a AS f",
        columns=[Column("name","Name",200,"text"), Column("version_string","Version",90,"text"), Column("eol_status","EOL",80,"badge"), Column("cve_count","CVEs",60,"num"), Column("signed","Signed",70,"bool"), Column("update_available","Update",80,"bool")],
        tags=["software","applications"],
        subcategories=[
            Category(id="apps-update-available", name="Update Available", group="Software Graph", parent_id="applications",
                description="Applications where a newer version exists",
                icon="🔄", color="#7c3aed",
                cypher="MATCH (a:Application) WHERE a.update_available = true AND a.tenant_id = $tid RETURN a AS f",
                columns=[Column("name","Name",200,"text"), Column("version_string","Current",90,"text"), Column("latest_version","Latest",90,"text"), Column("version_behind","Behind",70,"num")],
                tags=["software","updates"]),
            Category(id="apps-licensed", name="Has License", group="Software Graph", parent_id="applications",
                description="Applications with LICENSED_UNDER → License",
                icon="📜", color="#a78bfa",
                cypher="MATCH (a:Application)-[:LICENSED_UNDER]->(l:License) WHERE a.tenant_id = $tid RETURN DISTINCT a AS f",
                columns=[Column("name","Name",200,"text"), Column("version_string","Version",90,"text"), Column("eol_status","EOL",80,"badge")],
                tags=["software","license"]),
        ],
    ),

    Category(
        id="vendors", name="Vendors", group="Software Graph",
        description="Software vendors linked to applications via MADE_BY",
        icon="🏭", color="#a78bfa",
        cypher="MATCH (v:Vendor) WHERE v.tenant_id = $tid RETURN v AS f",
        columns=[Column("name","Vendor",200,"text"), Column("website","Website",200,"text")],
        tags=["software","vendor"],
    ),

    Category(
        id="licenses", name="Licenses", group="Software Graph",
        description="Software licenses (SPDX) applied to applications and files",
        icon="📜", color="#6ee7b7",
        cypher="MATCH (l:License) WHERE l.tenant_id = $tid RETURN l AS f",
        columns=[Column("name","License",200,"text"), Column("spdx","SPDX ID",100,"badge"), Column("type","Type",90,"badge")],
        tags=["software","license","compliance"],
        subcategories=[
            Category(id="licenses-copyleft", name="Copyleft Licenses", group="Software Graph", parent_id="licenses",
                description="GPL, LGPL, AGPL and other copyleft licenses",
                icon="⚠️", color="#f59e0b",
                cypher="MATCH (l:License) WHERE l.type = 'copyleft' AND l.tenant_id = $tid RETURN l AS f",
                columns=[Column("name","License",200,"text"), Column("spdx","SPDX ID",100,"badge")],
                tags=["license","copyleft","compliance"]),
        ],
    ),

    Category(
        id="dependencies", name="Dependencies", group="Software Graph",
        description="Software dependency graph (DEPENDS_ON relationships)",
        icon="🧩", color="#67e8f9",
        cypher="MATCH (d:Dependency) WHERE d.tenant_id = $tid RETURN d AS f",
        columns=[Column("name","Package",200,"text"), Column("version","Version",90,"text")],
        tags=["software","dependencies"],
        subcategories=[
            Category(id="deps-vulnerable", name="Vulnerable Dependencies", group="Software Graph", parent_id="dependencies",
                description="Dependencies with known CVEs via HAS_VULNERABILITY",
                icon="🛡️", color="#f87171",
                cypher="MATCH (d:Dependency)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE d.tenant_id = $tid RETURN DISTINCT d AS f",
                columns=[Column("name","Package",200,"text"), Column("version","Version",90,"text")],
                tags=["dependencies","cve","security"]),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Storage
    # ═══════════════════════════════════════════════════════════════════════════

    Category(
        id="duplicates", name="Duplicate Files", group="Storage",
        description="Files sharing identical SHA-256 hashes (DUPLICATE_OF)",
        icon="♻️", color="#6b7280",
        cypher="MATCH (f:File)-[:DUPLICATE_OF]->(g:File) WHERE f.tenant_id = $tid RETURN DISTINCT f",
        columns=_base() + [Column("sha256","Hash",160,"mono"), Column("file_category","Type",90,"badge")],
        tags=["storage","cleanup","duplicates"],
    ),

    Category(
        id="large-files", name="Large Files (>1 GB)", group="Storage",
        description="Files over 1 GB consuming significant storage",
        icon="💾", color="#6b7280",
        cypher="MATCH (f:File) WHERE f.size > 1073741824 AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("file_category","Type",90,"badge"), Column("size","Size",90,"size")],
        tags=["storage","large"],
    ),

    Category(
        id="directories", name="Directories", group="Storage",
        description="Directory nodes in the filesystem graph",
        icon="📁", color="#fbbf24",
        cypher="MATCH (d:Directory) WHERE d.tenant_id = $tid RETURN d AS f",
        columns=[Column("name","Name",200,"text"), Column("path","Path",300,"path"), Column("file_count","Files",70,"num"), Column("total_bytes","Total Size",100,"size")],
        tags=["storage","filesystem"],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: AI Analysis
    # ═══════════════════════════════════════════════════════════════════════════

    Category(
        id="ai-enriched", name="AI Enriched", group="AI Analysis",
        description="All files processed by local Ollama models",
        icon="🤖", color="#c084fc",
        cypher="MATCH (f:File) WHERE f.summary IS NOT NULL AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("file_category","Type",90,"badge"), Column("summary","Summary",260,"text"), Column("sentiment","Sentiment",90,"badge"), Column("language","Language",80,"badge")],
        tags=["ai"],
        subcategories=[
            Category(id="ai-negative-sentiment", name="Negative Sentiment", group="AI Analysis", parent_id="ai-enriched",
                description="Files with negative tone detected by LLM",
                icon="😟", color="#a855f7",
                cypher="MATCH (f:File) WHERE f.sentiment = 'negative' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_category","Type",90,"badge"), Column("document_type","Doc Type",90,"badge"), Column("summary","Summary",260,"text")],
                tags=["ai","sentiment"]),
            Category(id="ai-inferred-relationships", name="Semantically Related", group="AI Analysis", parent_id="ai-enriched",
                description="Files connected by SIMILAR_TO or REFERENCES relationships",
                icon="🔗", color="#9333ea",
                cypher="MATCH (f:File)-[r:SIMILAR_TO|REFERENCES]->(g:File) WHERE f.tenant_id = $tid RETURN DISTINCT f",
                columns=_base() + [Column("summary","Summary",260,"text"), Column("file_category","Type",90,"badge")],
                tags=["ai","relationships"]),
            Category(id="ai-action-items", name="Has Action Items", group="AI Analysis", parent_id="ai-enriched",
                description="Files with AI-detected tasks or todos",
                icon="✅", color="#7c3aed",
                cypher="MATCH (f:File) WHERE f.action_items IS NOT NULL AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("action_items","Action Items",300,"text"), Column("document_type","Type",90,"badge")],
                tags=["ai","actions"]),
            Category(id="ai-pending-enrichment", name="Pending Enrichment", group="AI Analysis", parent_id="ai-enriched",
                description="Files not yet processed by AI enrichers",
                icon="⏳", color="#a78bfa",
                cypher="MATCH (f:File) WHERE f.summary IS NULL AND f.enrichment_status <> 'skipped' AND f.tenant_id = $tid RETURN f",
                columns=_base() + [Column("file_category","Type",90,"badge"), Column("enrichment_status","Status",100,"badge")],
                tags=["ai","enrichment"]),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GROUP: Design & Engineering
    # ═══════════════════════════════════════════════════════════════════════════

    Category(
        id="3d-models", name="3D Models & CAD", group="Design & Engineering",
        description="STL, OBJ, FBX, STEP, DWG, DXF files",
        icon="🧊", color="#67e8f9",
        cypher="MATCH (f:File) WHERE f.file_category = '3d_model' AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("mime_type","Format",110,"badge")],
        tags=["3d","cad","design"],
    ),

    Category(
        id="calendar-contacts", name="Calendar & Contacts", group="Documents & Text",
        description=".ics calendar files and .vcf contact cards",
        icon="📅", color="#a3e635",
        cypher="MATCH (f:File) WHERE f.file_category IN ['calendar','contact'] AND f.tenant_id = $tid RETURN f",
        columns=_base() + [Column("file_category","Type",90,"badge")],
        tags=["calendar","contacts"],
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
