"""
Unit tests — NL search resolves to data TYPE categories (format-based taxonomy).

The Data Inventory is organized by file format / data type:
  Video → MKV / MP4 / MOV / AVI / TS / WMV / WebM
  Audio → FLAC / MP3 / AAC / WAV / DSD / Opus
  Images → JPEG / PNG / RAW / TIFF / WebP
  Documents → PDF / Word / Excel / PowerPoint / Text / Data
  Code → Python / JS / Go / Rust / Java / C# / Shell / Config / SQL
  etc.

NOT organized by attributes (4K, HDR, lossless, etc.) — those are filters.
"""
import pytest
from src.dgraphai.api.inventory_search import resolve_query, _score_all

pytestmark = pytest.mark.unit


def cat(q: str) -> str | None:
    return resolve_query(q).get("matched_category")

def conf(q: str) -> float:
    return resolve_query(q).get("confidence", 0.0)


# ── Video format types ────────────────────────────────────────────────────────

class TestVideoFormats:
    def test_mkv(self):         assert cat("mkv files")              == "video-mkv"
    def test_mkv_video(self):   assert cat("mkv video")              == "video-mkv"
    def test_mp4(self):         assert cat("mp4 files")              == "video-mp4"
    def test_mp4_video(self):   assert cat("mp4 video")              == "video-mp4"
    def test_mov(self):         assert cat("mov files")              == "video-mov"
    def test_quicktime(self):   assert cat("quicktime")              == "video-mov"
    def test_avi(self):         assert cat("avi files")              == "video-avi"
    def test_wmv(self):         assert cat("wmv files")              == "video-wmv"
    def test_webm(self):        assert cat("webm files")             == "video-webm"
    def test_ts(self):          assert cat("transport stream")       == "video-ts"
    def test_m2ts(self):        assert cat("m2ts")                   == "video-ts"
    def test_video_generic(self): assert cat("videos")               == "video"
    def test_movies(self):      assert cat("movies")                 == "video"
    def test_recordings(self):  assert cat("recordings")             == "video"
    def test_exact(self):       assert conf("Video")                 == 1.0


# ── Audio format types ────────────────────────────────────────────────────────

class TestAudioFormats:
    def test_flac(self):        assert cat("flac files")             == "audio-flac"
    def test_flac_music(self):  assert cat("flac music")             == "audio-flac"
    def test_mp3(self):         assert cat("mp3 files")              == "audio-mp3"
    def test_mp3_music(self):   assert cat("mp3 music")              == "audio-mp3"
    def test_aac(self):         assert cat("aac files")              == "audio-aac"
    def test_m4a(self):         assert cat("m4a files")              == "audio-aac"
    def test_wav(self):         assert cat("wav files")              == "audio-wav"
    def test_pcm(self):         assert cat("pcm audio")              == "audio-wav"
    def test_dsd(self):         assert cat("dsd files")              == "audio-dsd"
    def test_sacd(self):        assert cat("sacd")                   == "audio-dsd"
    def test_ogg(self):         assert cat("ogg files")              == "audio-opus"
    def test_opus(self):        assert cat("opus files")             == "audio-opus"
    def test_audio_generic(self): assert cat("audio files")          == "audio"
    def test_music(self):       assert cat("music")                  == "audio"
    def test_songs(self):       assert cat("songs")                  == "audio"


# ── Image format types ────────────────────────────────────────────────────────

class TestImageFormats:
    def test_jpeg(self):        assert cat("jpeg files")             == "images-jpeg"
    def test_jpg(self):         assert cat("jpg files")              == "images-jpeg"
    def test_png(self):         assert cat("png files")              == "images-png"
    def test_raw(self):         assert cat("raw photos")             == "images-raw"
    def test_cr2(self):         assert cat("cr2 files")              == "images-raw"
    def test_nef(self):         assert cat("nef files")              == "images-raw"
    def test_heic(self):        assert cat("heic files")             == "images-raw"
    def test_heif(self):        assert cat("heif files")             == "images-raw"
    def test_dng(self):         assert cat("dng files")              == "images-raw"
    def test_tiff(self):        assert cat("tiff files")             == "images-tiff"
    def test_bmp(self):         assert cat("bmp files")              == "images-tiff"
    def test_webp(self):        assert cat("webp files")             == "images-webp"
    def test_gif(self):         assert cat("gif files")              == "images-webp"
    def test_photos(self):      assert cat("photos")                 == "images"
    def test_pictures(self):    assert cat("pictures")               == "images"


# ── Document format types ─────────────────────────────────────────────────────

class TestDocumentFormats:
    def test_pdf(self):         assert cat("pdf files")              == "docs-pdf"
    def test_pdfs(self):        assert cat("pdfs")                   == "docs-pdf"
    def test_word(self):        assert cat("word files")             == "docs-word"
    def test_docx(self):        assert cat("docx files")             == "docs-word"
    def test_excel(self):       assert cat("excel files")            == "docs-excel"
    def test_spreadsheets(self):assert cat("spreadsheets")           == "docs-excel"
    def test_csv(self):         assert cat("csv files")              == "docs-excel"
    def test_pptx(self):        assert cat("powerpoint files")       == "docs-powerpoint"
    def test_presentations(self):assert cat("presentations")         == "docs-powerpoint"
    def test_txt(self):         assert cat("text files")             == "docs-text"
    def test_markdown(self):    assert cat("markdown files")         == "docs-text"
    def test_json(self):        assert cat("json files")             == "docs-data"
    def test_xml(self):         assert cat("xml files")              == "docs-data"
    def test_yaml(self):        assert cat("yaml files")             == "docs-data"
    def test_docs_generic(self):assert cat("documents")              == "documents"


# ── Code format types ─────────────────────────────────────────────────────────

class TestCodeFormats:
    def test_python(self):      assert cat("python files")           == "code-python"
    def test_py(self):          assert cat("py files")               == "code-python"
    def test_javascript(self):  assert cat("javascript files")       == "code-javascript"
    def test_typescript(self):  assert cat("typescript files")       == "code-javascript"
    def test_js(self):          assert cat("js files")               == "code-javascript"
    def test_go(self):          assert cat("go files")               == "code-go"
    def test_golang(self):      assert cat("golang files")           == "code-go"
    def test_rust(self):        assert cat("rust files")             == "code-rust"
    def test_java(self):        assert cat("java files")             == "code-java"
    def test_kotlin(self):      assert cat("kotlin files")           == "code-java"
    def test_csharp(self):      assert cat("c# files")               == "code-csharp"
    def test_cpp(self):         assert cat("c++ files")              == "code-csharp"
    def test_shell(self):       assert cat("shell scripts")          == "code-shell"
    def test_bash(self):        assert cat("bash scripts")           == "code-shell"
    def test_powershell(self):  assert cat("powershell scripts")     == "code-shell"
    def test_config(self):      assert cat("config files")           == "code-config"
    def test_env(self):         assert cat("env files")              == "code-config"
    def test_sql(self):         assert cat("sql files")              == "code-sql"
    def test_code_generic(self):assert cat("source code")            == "code"


# ── Executable format types ───────────────────────────────────────────────────

class TestExecutableFormats:
    def test_exe(self):         assert cat("exe files")              == "exe-pe"
    def test_dll(self):         assert cat("dll files")              == "exe-pe"
    def test_windows_exe(self): assert cat("windows executables")    == "exe-pe"
    def test_elf(self):         assert cat("elf files")              == "exe-elf"
    def test_linux(self):       assert cat("linux binaries")         == "exe-elf"
    def test_macho(self):       assert cat("macho files")            == "exe-macho"
    def test_macos(self):       assert cat("macos binaries")         == "exe-macho"
    def test_msi(self):         assert cat("msi files")              == "exe-msi"
    def test_installers(self):  assert cat("installers")             == "exe-msi"
    def test_deb(self):         assert cat("deb files")              == "exe-msi"
    def test_exe_generic(self): assert cat("executables")            == "executables"
    def test_binaries(self):    assert cat("binaries")               == "executables"


# ── Archive format types ──────────────────────────────────────────────────────

class TestArchiveFormats:
    def test_zip(self):         assert cat("zip files")              == "archives-zip"
    def test_jar(self):         assert cat("jar files")              == "archives-zip"
    def test_7z(self):          assert cat("7z files")               == "archives-7z"
    def test_rar(self):         assert cat("rar files")              == "archives-7z"
    def test_tar(self):         assert cat("tar files")              == "archives-tar"
    def test_tgz(self):         assert cat("tgz files")              == "archives-tar"
    def test_iso(self):         assert cat("iso files")              == "archives-iso"
    def test_disk_images(self): assert cat("disc images")            == "archives-iso"
    def test_archive_generic(self): assert cat("archives")           == "archives"
    def test_compressed(self):  assert cat("compressed files")       == "archives"


# ── Other types ───────────────────────────────────────────────────────────────

class TestOtherTypes:
    def test_pem(self):         assert cat("pem files")              == "certs-pem"
    def test_ssl_certs(self):   assert cat("ssl certificates")       == "certs-pem"
    def test_p12(self):         assert cat("p12 files")              == "certs-pkcs12"
    def test_pfx(self):         assert cat("pfx files")              == "certs-pkcs12"
    def test_key_files(self):   assert cat("private key files")      == "certs-keys"
    def test_certs_generic(self): assert cat("certificates")         == "certificates"
    def test_stl(self):         assert cat("stl files")              == "3d-stl"
    def test_cad(self):         assert cat("cad files")              == "3d-cad"
    def test_dwg(self):         assert cat("dwg files")              == "3d-cad"
    def test_blend(self):       assert cat("blender files")          == "3d-blend"
    def test_ics(self):         assert cat("ics files")              == "calendar-ics"
    def test_vcf(self):         assert cat("vcf files")              == "contacts-vcf"
    def test_emails(self):      assert cat("emails")                 == "emails"
    def test_eml(self):         assert cat("eml files")              == "emails-eml"
    def test_msg(self):         assert cat("msg files")              == "emails-msg"
    def test_people(self):      assert cat("people")                 == "people"
    def test_duplicates(self):  assert cat("duplicate files")        == "duplicates"
    def test_folders(self):     assert cat("folders")                == "directories"


# ── No-match & edge cases ─────────────────────────────────────────────────────

class TestEdgeCases:
    def test_gibberish_no_match(self):
        r = resolve_query("xyzblorgwumpf999")
        assert r["matched_category"] is None

    def test_no_match_has_escape(self):
        r = resolve_query("xyzblorgwumpf999")
        assert "no_match_query_url" in r

    def test_suggestions_present(self):
        r = resolve_query("random data thing")
        assert "suggestions" in r

    def test_exact_name_confidence_1(self):
        assert conf("Video") == 1.0
        assert conf("Audio") == 1.0
        assert conf("Images") == 1.0

    def test_case_insensitive(self):
        assert cat("MKV Files")     == cat("mkv files")
        assert cat("PDF DOCUMENTS") == cat("pdf documents")
        assert cat("Python Files")  == cat("python files")

    def test_suggestions_ranked(self):
        sugs = _score_all("video")
        assert len(sugs) > 0
        scores = [s["score"] for s in sugs]
        assert scores == sorted(scores, reverse=True)
