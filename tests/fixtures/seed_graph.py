"""
Graph seed data for integration tests.
Populates a test Neo4j instance with representative nodes and relationships.
Run directly: uv run python tests/fixtures/seed_graph.py
"""
from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone

# ── Sample nodes ───────────────────────────────────────────────────────────────

def make_tid():
    return "00000000-0000-0000-0000-000000000001"   # fixed test tenant

SEED_NODES = [

    # Video files
    {"id": "f-video-4k-hdr",  "labels": ["File"], "props": {"name": "Oppenheimer.mkv",   "file_category": "video",    "height": 2160,  "hdr_format": "Dolby Vision", "video_codec": "H.265", "duration_secs": 10800.0, "size": 45_000_000_000, "tenant_id": make_tid(), "summary": "Epic historical drama"}},
    {"id": "f-video-1080p",   "labels": ["File"], "props": {"name": "The Boys S05E01.mkv","file_category": "video",    "height": 1080,  "audio_codec": "eac3",        "video_codec": "H.264", "duration_secs": 3600.0,  "size":  8_000_000_000, "tenant_id": make_tid()}},

    # Audio files
    {"id": "f-audio-flac",    "labels": ["File"], "props": {"name": "DarkSide.flac",      "file_category": "audio",    "audio_codec": "flac",     "sample_rate": 44100, "bit_depth": 16, "artist": "Pink Floyd", "album": "Dark Side of the Moon", "title": "Money", "year": 1973, "tenant_id": make_tid()}},
    {"id": "f-audio-mp3",     "labels": ["File"], "props": {"name": "unknown.mp3",        "file_category": "audio",    "audio_codec": "mp3",      "tenant_id": make_tid()}},

    # Images
    {"id": "f-image-gps",     "labels": ["File"], "props": {"name": "vacation.jpg",       "file_category": "image",    "gps_latitude": 48.8566, "gps_longitude": 2.3522, "face_count": 2, "camera_model": "iPhone 15 Pro", "tenant_id": make_tid(), "summary": "Outdoor portrait near Eiffel Tower", "scene_type": "outdoor"}},
    {"id": "f-image-raw",     "labels": ["File"], "props": {"name": "portrait.cr2",       "file_category": "image",    "mime_type": "image/x-canon-cr2", "focal_length": 85.0, "aperture": 1.4, "iso": 400, "tenant_id": make_tid()}},

    # Documents
    {"id": "f-doc-invoice",   "labels": ["File"], "props": {"name": "Invoice_2024_Q3.pdf","file_category": "document", "mime_type": "application/pdf", "pii_detected": True, "sensitivity_level": "high", "document_type": "invoice", "page_count": 2, "tenant_id": make_tid(), "summary": "Q3 invoice from ACME Corp for $12,500"}},
    {"id": "f-doc-report",    "labels": ["File"], "props": {"name": "Q3_Report.docx",     "file_category": "document", "document_type": "report", "sentiment": "positive", "language": "en", "page_count": 24, "tenant_id": make_tid(), "summary": "Q3 financial report showing 15% growth"}},
    {"id": "f-doc-encrypted", "labels": ["File"], "props": {"name": "Private.pdf",        "file_category": "document", "is_encrypted": True, "tenant_id": make_tid()}},
    {"id": "f-doc-macro",     "labels": ["File"], "props": {"name": "Template.xlsm",      "file_category": "document", "has_macros": True, "tenant_id": make_tid()}},

    # Code
    {"id": "f-code-secrets",  "labels": ["File"], "props": {"name": ".env",               "file_category": "code",     "code_language": "env", "contains_secrets": True, "secret_types": "api_key,password", "line_count": 15, "tenant_id": make_tid()}},
    {"id": "f-code-clean",    "labels": ["File"], "props": {"name": "utils.py",            "file_category": "code",     "code_language": "Python", "line_count": 120, "function_count": 8, "code_quality": "good", "has_tests": False, "tenant_id": make_tid()}},

    # Executables
    {"id": "f-exe-eol",       "labels": ["File"], "props": {"name": "app_v1.exe",          "file_category": "executable","binary_format": "PE", "eol_status": "eol", "signed": False, "company_name": "ACME Corp", "file_version": "1.0.0", "tenant_id": make_tid()}},
    {"id": "f-exe-packed",    "labels": ["File"], "props": {"name": "suspicious.exe",      "file_category": "executable","binary_format": "PE", "is_packed": True, "entropy": 7.8, "signed": False, "risk_assessment": "high", "tenant_id": make_tid()}},

    # Archive
    {"id": "f-archive-exe",   "labels": ["File"], "props": {"name": "update.zip",          "file_category": "archive",  "file_count_in_archive": 12, "contains_executables": True, "compression_ratio": 0.72, "tenant_id": make_tid()}},

    # Certificate
    {"id": "f-cert-expired",  "labels": ["File"], "props": {"name": "old.crt",             "file_category": "certificate","cert_subject": "CN=example.com", "cert_issuer": "CN=Let's Encrypt", "cert_is_expired": True, "days_until_expiry": -30, "tenant_id": make_tid()}},
    {"id": "f-cert-expiring", "labels": ["File"], "props": {"name": "server.crt",          "file_category": "certificate","cert_subject": "CN=api.company.com", "days_until_expiry": 12, "cert_is_expired": False, "tenant_id": make_tid()}},

    # People
    {"id": "p-alice",         "labels": ["Person"], "props": {"name": "Alice Smith", "known": True,  "face_count": 5, "tenant_id": make_tid()}},
    {"id": "p-unknown",       "labels": ["FaceCluster"], "props": {"label": "Unknown-001", "known": False, "face_count": 3, "tenant_id": make_tid()}},

    # Vulnerability
    {"id": "vuln-cve",        "labels": ["Vulnerability"], "props": {"cve_id": "CVE-2024-12345", "cvss_score": 9.8, "cvss_severity": "critical", "exploit_available": True, "actively_exploited": True, "description": "Remote code execution in LibSSL", "tenant_id": make_tid()}},
    {"id": "app-affected",    "labels": ["Application"],   "props": {"name": "OpenSSL", "version_string": "1.0.2", "eol_status": "eol", "cve_count": 3, "critical_cve_count": 1, "signed": True, "tenant_id": make_tid()}},

    # Directory
    {"id": "dir-root",        "labels": ["Directory"], "props": {"name": "Media", "path": "/mnt/nas/Media", "file_count": 1247, "total_bytes": 5_000_000_000_000, "tenant_id": make_tid()}},

    # Location
    {"id": "loc-paris",       "labels": ["Location"], "props": {"name": "Paris", "city": "Paris", "country": "France", "latitude": 48.8566, "longitude": 2.3522, "place_type": "city", "tenant_id": make_tid()}},

    # Collection
    {"id": "col-movies",      "labels": ["Collection"], "props": {"name": "Movies 4K", "type": "media", "description": "4K UHD movie collection", "tenant_id": make_tid()}},
]

SEED_RELS = [
    # Filesystem
    {"from": "f-video-4k-hdr", "to": "dir-root",    "type": "CHILD_OF"},
    {"from": "f-video-4k-hdr", "to": "col-movies",  "type": "PART_OF"},

    # Image → Location (GPS resolved)
    {"from": "f-image-gps", "to": "loc-paris", "type": "LOCATED_AT"},

    # Image → Person (face recognition)
    {"from": "f-image-gps",    "to": "p-alice",   "type": "DEPICTS"},
    {"from": "f-image-gps",    "to": "p-unknown", "type": "CONTAINS_FACE", "props": {"confidence": 0.94}},
    {"from": "p-unknown",      "to": "p-alice",   "type": "SAME_PERSON_AS","props": {"confidence": 0.87}},

    # Document → entity mentions
    {"from": "f-doc-invoice", "to": "f-doc-report", "type": "REFERENCES"},

    # Application → Vulnerability
    {"from": "app-affected",  "to": "vuln-cve",    "type": "HAS_VULNERABILITY"},

    # AI similarity
    {"from": "f-doc-invoice", "to": "f-doc-report", "type": "SIMILAR_TO", "props": {"score": 0.78}},
]


async def seed(neo4j_uri: str, user: str, password: str):
    """Seed the test graph with representative data."""
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(user, password))
    async with driver.session() as session:
        # Clear test tenant data first
        await session.run(
            "MATCH (n) WHERE n.tenant_id = $tid DETACH DELETE n",
            tid=make_tid()
        )
        # Create nodes
        for node in SEED_NODES:
            labels = ":".join(node["labels"])
            await session.run(
                f"CREATE (n:{labels} $props) SET n.id = $id",
                props=node["props"], id=node["id"]
            )
        # Create relationships
        for rel in SEED_RELS:
            props = rel.get("props", {})
            await session.run(
                f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) "
                f"CREATE (a)-[r:{rel['type']} $props]->(b)",
                from_id=rel["from"], to_id=rel["to"], props=props
            )
    await driver.close()
    print(f"Seeded {len(SEED_NODES)} nodes, {len(SEED_RELS)} relationships")


if __name__ == "__main__":
    import os
    asyncio.run(seed(
        os.getenv("NEO4J_URI",      "bolt://localhost:7687"),
        os.getenv("NEO4J_USER",     "neo4j"),
        os.getenv("NEO4J_PASSWORD", "fsgraph-local"),
    ))
