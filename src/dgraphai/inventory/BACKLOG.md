# Inventory Taxonomy — Feature Backlog

Categories and enrichers that require new capabilities not yet in archon.
Each item notes what needs to be built before the category can go live.

---

## Requires New Archon Enrichers

### Audio
| Category | What's Needed | Archon Work |
|---|---|---|
| Genre Clustering | AcousticID fingerprinting + MusicBrainz lookup | New `acoustid_enricher.py` |
| BPM Bands (<80, 80–120, 120–160, 160+) | BPM extraction from audio stream | Already extracts `bpm` — just needs taxonomy entry |
| Mood (energetic / calm / melancholic) | LLM or audio-ML model | New enricher or LLM prompt |
| Podcast Episodes | RSS metadata + episode detection | New `podcast_enricher.py` |
| Live Recordings | Heuristic: crowd noise, variable bitrate | ML or LLM signal |

### Video
| Category | What's Needed | Archon Work |
|---|---|---|
| Scene Change Density | ffprobe scene detection pass | `ffprobe -vf "select=gt(scene\,0.4)"` |
| Has Burned-in Subtitles | OCR frame sample | Tesseract on sampled frames |
| Contains Text / Titles | Vision model on keyframes | LLaVA keyframe pass |
| Dolby Atmos Audio | ffprobe stream detection | Add `audio_format` to metadata |
| Multi-episode / Season | File naming heuristic (S01E01 pattern) | Simple regex enricher |

### Images
| Category | What's Needed | Archon Work |
|---|---|---|
| Contains Text (OCR) | Tesseract OCR pass | New `ocr_enricher.py` |
| Dominant Color Palette | PIL k-means clustering | Already in LLaVA response — surface as node property |
| Document Photos (whiteboard, receipt, etc.) | LLaVA `is_document` already extracted | Add to taxonomy — just needs column wiring |
| NSFW Detection | Dedicated NSFW classifier model | New local model (e.g., Falconsai) |
| Image Quality Score | BRISQUE / NIQE no-reference quality | New `quality_enricher.py` |
| Landscape / Wildlife | Object detection (YOLO/OWL-ViT) | New `object_detection_enricher.py` |

### Documents
| Category | What's Needed | Archon Work |
|---|---|---|
| Financial Statements | AI doc type already extracts — needs `financial_statement` type | Add to LLM prompt |
| Medical Records | AI doc type + HIPAA PII patterns | Add to LLM prompt + PII patterns |
| Legal Filings | AI doc type | Add `legal_filing` to doc types |
| Regulatory Filings | AI doc type | Add `regulatory` to doc types |
| Has Embedded Macros | `has_macros` already in schema | Add taxonomy entry |
| Digitally Signed Docs | `is_signed` already in schema | Add taxonomy entry |
| Encrypted Documents | `is_encrypted` already in schema | Add taxonomy entry |
| Named Entity Relationships | Build Person→Organization, Person→Location graph edges | New `entity_relationship_builder.py` |

### Code
| Category | What's Needed | Archon Work |
|---|---|---|
| Language Breakdown (Python / JS / Go) | `code_language` already extracted | Add per-language sub-categories |
| Open Source Licenses (detected in code) | License header scanning | New `license_scanner.py` (e.g., SPDX-like) |
| Test Coverage Estimate | Parse coverage.xml / .coverage files | New `coverage_enricher.py` |
| Dead Code | LLM assessment or static analysis | Extend code LLM prompt |
| Dependency Manifest Files | package.json, requirements.txt, go.mod detection | New `dependency_parser.py` → builds DEPENDS_ON edges |

### Executables
| Category | What's Needed | Archon Work |
|---|---|---|
| Known Malware Hash | VirusTotal / NSRL hash lookup | New `hash_reputation_enricher.py` |
| Import Table Analysis (suspicious APIs) | lief import table already available | Surface `suspicious_imports` property |
| Packers Identified | Detect UPX, MPRESS, Themida | `pefile` packer detection |
| Version History | Track version changes over scans | New `version_delta_tracker.py` |

---

## Requires New Relationship Types

| Relationship | From → To | Use Case |
|---|---|---|
| `COLOCATED_WITH` | File → File | Files in same directory / share |
| `CREATED_BY` | File → Person | Document author → Person node |
| `MODIFIED_BY` | File → Person | Last modifier → Person node |
| `SHARED_WITH` | File → Organization | Document shared to org (from SharePoint/GCS ACLs) |
| `DERIVED_FROM` | File → File | Exported/converted file traces to source |
| `SUPERSEDES` | Application → Application | Upgrade path tracking |
| `FOUND_ON` | Application → Location | Where an app was discovered |
| `INSTALLED_ON` | Application → Directory | Install path as Directory node |
| `AFFECTS` | Vulnerability → Version | CVE affects specific version range |
| `PATCHED_BY` | Vulnerability → Version | Resolved in this version |
| `TOPIC_OF` | Collection → Topic | Collection grouped by topic |
| `GEOGRAPHICALLY_NEAR` | Location → Location | Proximity relationship (computed) |
| `TEMPORALLY_NEAR` | Event → Event | Events within time window |

---

## Requires External Data Sources

| Category | External Source | Notes |
|---|---|---|
| CVE Data | NVD API / OSV.dev | Already planned — needs scheduled sync job |
| EOL Dates | endoflife.date API | Cron enricher — free API |
| TMDB Matching | TMDB API | Already `MATCHED_TO` schema — needs enricher |
| Malware Hash Reputation | VirusTotal / NSRL | Rate-limited; needs caching layer |
| License SPDX | SPDX license list | Static dataset, bundled |
| MusicBrainz | MusicBrainz API | AcousticID → MBID → metadata |
| IP Geolocation | MaxMind GeoIP2 | For connector location data |

---

## Requires New Node Types (schema additions needed)

| Node Type | Purpose | Linked Via |
|---|---|---|
| `NetworkEndpoint` | IP/domain observed in files | `REFERENCES` from File |
| `EmailAddress` | Extracted email entities | `MENTIONS` from File |
| `PhoneNumber` | Extracted phone entities | `MENTIONS` from File |
| `URL` | URLs found in documents/code | `REFERENCES` from File |
| `Secret` | Individual secret instance with context | `CONTAINS` from File |
| `Hash` | Known hash (NSRL/VT) with reputation | `MATCHED_TO` from File |
| `Scanner` | Scanner agent that found the file | `DISCOVERED_BY` from File |
| `ScanRun` | A single indexing run | `INDEXED_IN` from File |

---

## Already In Schema — Just Needs Taxonomy Entries

These properties are already written by archon but not yet surfaced as categories:

| Property | On Node | Suggested Category |
|---|---|---|
| `has_macros` | File (Office) | Office docs with macros |
| `is_encrypted` | File (PDF/Office) | Encrypted documents |
| `is_signed` | File (PDF) | Digitally signed documents |
| `bpm` | File (audio) | BPM-based music categories |
| `acoustid` | File (audio) | AcousticID matched audio |
| `musicbrainz_id` | File (audio) | MusicBrainz linked tracks |
| `version_behind` | Application | Apps N versions behind latest |
| `update_available` | Application | Apps with available updates ← already in taxonomy |
| `is_universal` | File (binary) | Universal/fat binaries (macOS) |
| `architectures` | File (binary) | Multi-arch binaries |
| `subtitle_languages` | File (video) | Videos with specific subtitle languages |
| `color_space` | File (video) | BT.2020 / Rec.709 video |
| `fps` | File (video) | Frame rate categories (24p, 60p, etc.) |
| `bit_depth` | File (video/image) | 10-bit / 12-bit content |
| `gps_altitude` | File (image) | Altitude-tagged photos |
| `lens` | File (image) | Lens model grouping |
| `focal_length` | File (image) | Wide vs telephoto |
| `aperture` | File (image) | Aperture grouping |
| `place_type` | Location | Location type filtering |
| `is_ca` | Certificate | CA certificates |
| `key_size` | Certificate | Weak key size (<2048 bit) |
| `cert_key_algorithm` | Certificate | RSA vs EC vs Ed25519 |
| `compression_method` | Archive | Archive compression method |
| `enrichment_status` | File | Already in taxonomy (pending enrichment) |
