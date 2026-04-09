"""
Unit tests — natural language inventory category search.

The Data Inventory is a category browser, not a query engine.
These tests verify that NL queries resolve to the correct data categories.
No Cypher synthesis tested here — that belongs in the Graph/Query area.
"""
import pytest
from src.dgraphai.api.inventory_search import resolve_query, _score_all

pytestmark = pytest.mark.unit


# ── Helper ─────────────────────────────────────────────────────────────────────

def cat(q: str) -> str | None:
    return resolve_query(q).get("matched_category")

def conf(q: str) -> float:
    return resolve_query(q).get("confidence", 0.0)

def cats(*queries: str) -> list[str | None]:
    return [cat(q) for q in queries]


# ── Video ──────────────────────────────────────────────────────────────────────

class TestVideoCategories:
    def test_4k_hdr(self):         assert cat("4k hdr movies")         == "video-4k-hdr"
    def test_dolby_vision_4k(self):assert cat("dolby vision 4k")       == "video-4k-hdr"
    def test_uhd_hdr(self):        assert cat("uhd hdr")               == "video-4k-hdr"
    def test_4k_av1(self):         assert cat("4k av1")                == "video-4k-av1"
    def test_4k_generic(self):     assert cat("4k videos")             == "video-4k"
    def test_uhd_generic(self):    assert cat("uhd content")           == "video-4k"
    def test_hdr_video(self):      assert cat("hdr video")             == "video-hdr"
    def test_dolby_vision(self):   assert cat("dolby vision")          == "video-hdr"
    def test_1080p(self):          assert cat("1080p video")           == "video-1080p"
    def test_feature_films(self):  assert cat("feature films")         == "video-long"
    def test_movies(self):         assert cat("movies")                in ("video-long", "media-movies")
    def test_subtitles(self):      assert cat("subtitled video")       == "video-subtitles"
    def test_wide_color(self):     assert cat("bt.2020 wide color")    == "video-wide-color"
    def test_10bit(self):          assert cat("10-bit video")          == "video-bit-depth"
    def test_video_generic(self):  assert cat("mkv files")             == "video"
    def test_exact_name(self):     assert conf("Video")                == 1.0


# ── Audio ──────────────────────────────────────────────────────────────────────

class TestAudioCategories:
    def test_lossless(self):       assert cat("lossless audio")        == "audio-lossless"
    def test_flac(self):           assert cat("flac music")            == "audio-lossless"
    def test_flac_files(self):     assert cat("flac files")            == "audio-lossless"
    def test_hires(self):          assert cat("hi-res audio")          == "audio-hires"
    def test_untagged(self):       assert cat("untagged music")        == "audio-untagged"
    def test_missing_tags(self):   assert cat("missing tags")          == "audio-untagged"
    def test_musicbrainz(self):    assert cat("musicbrainz")           == "audio-musicbrainz"
    def test_slow_bpm(self):       assert cat("slow bpm")              == "audio-slow"
    def test_fast_bpm(self):       assert cat("high bpm")              == "audio-fast"
    def test_bpm(self):            assert cat("bpm")                   == "audio-bpm"
    def test_audio_generic(self):  assert cat("mp3")                   == "audio"


# ── Images ─────────────────────────────────────────────────────────────────────

class TestImageCategories:
    def test_photos_with_faces(self): assert cat("photos with faces")  == "images-with-faces"
    def test_faces(self):          assert cat("faces")                 == "images-with-faces"
    def test_identified(self):     assert cat("identified people")     == "images-identified-people"
    def test_group_photos(self):   assert cat("group photos")          == "images-group-shots"
    def test_geotagged(self):      assert cat("geotagged photos")      == "images-geotagged"
    def test_raw_files(self):      assert cat("raw photos")            == "images-raw"
    def test_cr2(self):            assert cat("cr2 files")             == "images-raw"
    def test_heic(self):           assert cat("heic images")           == "images-raw"
    def test_screenshots(self):    assert cat("screenshots")           == "images-screenshots"
    def test_telephoto(self):      assert cat("telephoto photos")      == "images-telephoto"
    def test_wide_angle(self):     assert cat("wide angle photos")     == "images-wide-angle"
    def test_high_iso(self):       assert cat("high iso photos")       == "images-high-iso"
    def test_long_exposure(self):  assert cat("long exposure")         == "images-long-exposure"
    def test_images_generic(self): assert cat("jpg files")             == "images"


# ── Documents ──────────────────────────────────────────────────────────────────

class TestDocumentCategories:
    def test_pii_docs(self):       assert cat("gdpr documents")        == "docs-pii"
    def test_sensitive_docs(self): assert cat("confidential documents") == "docs-pii-high"
    def test_contracts(self):      assert cat("contracts")             == "docs-contracts"
    def test_nda(self):            assert cat("nda")                   == "docs-contracts"
    def test_invoices(self):       assert cat("invoices")              == "docs-invoices"
    def test_billing(self):        assert cat("billing documents")     == "docs-invoices"
    def test_reports(self):        assert cat("quarterly reports")     == "docs-reports"
    def test_pdf(self):            assert cat("pdf files")             == "docs-pdf"
    def test_spreadsheets(self):   assert cat("spreadsheets")          in ("docs-spreadsheet", "documents")
    def test_office(self):         assert cat("word documents")        == "docs-office"
    def test_encrypted(self):      assert cat("encrypted documents")   == "docs-encrypted"
    def test_macros(self):         assert cat("documents with macros") == "docs-with-macros"
    def test_signed(self):         assert cat("digitally signed documents") == "docs-digitally-signed"
    def test_multilingual(self):   assert cat("multilingual")          == "docs-multilingual"
    def test_action_items(self):   assert cat("documents with action items") == "docs-has-action-items"


# ── Security ───────────────────────────────────────────────────────────────────

class TestSecurityCategories:
    def test_code_secrets(self):   assert cat("source code with secrets")   == "code-secrets"
    def test_exposed_passwords(self): assert cat("exposed passwords")       == "secrets-passwords"
    def test_api_keys(self):       assert cat("api keys in files")          == "secrets-api-keys"
    def test_auth_tokens(self):    assert cat("auth tokens")                == "secrets-tokens"
    def test_pii_high(self):       assert cat("high sensitivity pii")       == "pii-high"
    def test_ssn(self):            assert cat("ssn")                        == "pii-ssn"
    def test_pii_emails(self):     assert cat("email addresses in files")   == "pii-emails-phones"
    def test_pii_generic(self):    assert cat("personal data")              == "pii"
    def test_expired_certs(self):  assert cat("expired certificates")       == "certs-expired"
    def test_expiring_certs(self): assert cat("certs expiring soon")        == "certs-expiring-30"
    def test_self_signed(self):    assert cat("self-signed certificates")   == "certs-self-signed"
    def test_weak_keys(self):      assert cat("weak key certificates")      == "certs-weak-keys"
    def test_ca_certs(self):       assert cat("certificate authorities")    == "certs-ca"
    def test_private_keys(self):   assert cat("private keys")               == "private-keys"
    def test_critical_cve(self):   assert cat("critical cve")               == "cve-critical"
    def test_exploited(self):      assert cat("actively exploited cve")     == "cve-exploited"
    def test_eol_software(self):   assert cat("end of life software")       == "exe-eol"
    def test_unsigned(self):       assert cat("unsigned executables")       == "exe-unsigned"
    def test_high_risk(self):      assert cat("high risk binaries")         == "exe-high-risk"
    def test_packed(self):         assert cat("packed executables")         == "exe-packed"


# ── People & AI ────────────────────────────────────────────────────────────────

class TestPeopleAndAI:
    def test_identified_people(self):  assert cat("identified people")      in ("people-identified", "images-identified-people")
    def test_unknown_faces(self):      assert cat("unknown faces")          == "people-unknown-clusters"
    def test_negative_sentiment(self): assert cat("negative sentiment")     == "ai-negative-sentiment"
    def test_pending(self):            assert cat("pending enrichment")     == "ai-pending-enrichment"
    def test_ai_action_items(self):    assert cat("files with action items") == "ai-action-items"
    def test_duplicates(self):         assert cat("duplicate files")        == "duplicates"
    def test_large_files(self):        assert cat("large files")            == "large-files"


# ── No-match behavior ──────────────────────────────────────────────────────────

class TestNoMatch:
    def test_gibberish_returns_no_category(self):
        r = resolve_query("xyzblorgwumpf123abc")
        assert r["matched_category"] is None

    def test_no_match_has_escape_hatch(self):
        r = resolve_query("xyzblorgwumpf123abc")
        assert "no_match_query_url" in r or "suggestions" in r

    def test_no_match_has_suggestions(self):
        r = resolve_query("some random data thing")
        # Should suggest something even if no exact match
        assert "suggestions" in r

    def test_suggestions_are_ranked(self):
        sugs = _score_all("certificates")
        assert len(sugs) > 0
        scores = [s["score"] for s in sugs]
        assert scores == sorted(scores, reverse=True)


# ── Confidence & quality ───────────────────────────────────────────────────────

class TestConfidence:
    def test_exact_name_is_1(self):
        assert conf("Video") == 1.0
        assert conf("Audio") == 1.0

    def test_keyword_match_high_confidence(self):
        assert conf("4k hdr movies")      >= 0.85
        assert conf("expired certificates") >= 0.85
        assert conf("invoices")           >= 0.7

    def test_case_insensitive(self):
        assert cat("4K HDR MOVIES")  == cat("4k hdr movies")
        assert cat("EXPIRED SSL")    == cat("expired ssl")
        assert cat("Private Keys")   == cat("private keys")
