"""
Unit tests — metadata extraction (file categorization + secret detection).
"""
import pytest
from pathlib import Path

pytestmark = pytest.mark.unit


class TestCategorize:
    def test_video_extensions(self):
        from src.dgraphai.inventory.taxonomy import get_category
        # just confirm video category exists and has correct cypher
        cat = get_category("video")
        assert cat is not None
        assert "video" in cat.cypher

    def test_file_categorizer(self):
        try:
            from src.dgraphai.enrichers.metadata import categorize
        except ImportError:
            pytest.skip("archon not available")

        assert categorize(".mkv")  == "video"
        assert categorize(".mp4")  == "video"
        assert categorize(".flac") == "audio"
        assert categorize(".jpg")  == "image"
        assert categorize(".pdf")  == "document"
        assert categorize(".exe")  == "executable"
        assert categorize(".zip")  == "archive"
        assert categorize(".pem")  == "certificate"
        assert categorize(".py")   == "code"
        assert categorize(".stl")  == "3d_model"
        assert categorize(".xyz")  == "other"


class TestSecretDetection:
    def test_detects_api_key_pattern(self, tmp_path):
        try:
            from src.dgraphai.enrichers.metadata import _extract_code
        except ImportError:
            pytest.skip("archon not available")

        f = tmp_path / "config.py"
        f.write_text("STRIPE_KEY = 'sk_live_abcdef1234567890'\nDEBUG = True\n")
        result = _extract_code(str(f))
        assert result.get("contains_secrets") is True

    def test_clean_code_no_secrets(self, tmp_path):
        try:
            from src.dgraphai.enrichers.metadata import _extract_code
        except ImportError:
            pytest.skip("archon not available")

        f = tmp_path / "clean.py"
        f.write_text("def add(a, b):\n    return a + b\n")
        result = _extract_code(str(f))
        assert not result.get("contains_secrets")

    def test_pii_detection_in_csv(self, tmp_path):
        try:
            from src.dgraphai.enrichers.metadata import _extract_web_data
        except ImportError:
            pytest.skip("archon not available")

        f = tmp_path / "users.csv"
        f.write_text("name,email,ssn\nJohn,john@example.com,123-45-6789\n")
        result = _extract_web_data(str(f), ".csv")
        assert result.get("pii_detected") is True
        assert "email" in result.get("pii_types", "")
