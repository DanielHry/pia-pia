# tests/test_session_paths.py

"""Tests for piapia/utils/session_paths.py"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from piapia.domain.sessions import AudioSessionInfo
from piapia.utils.session_paths import (
    apply_paths_to_session,
    build_session_paths,
)


@pytest.fixture
def mock_settings():
    """Mocked settings with default values."""
    settings = MagicMock()
    settings.logs_dir = ".logs"
    settings.audio_sessions_subdir = "audio"
    return settings


# =============================================================================
# build_session_paths
# =============================================================================
class TestBuildSessionPaths:
    def test_returns_expected_keys(self, mock_settings):
        """The returned dict contains the expected keys."""
        paths = build_session_paths(mock_settings, "test-session", create=False)
        
        assert "base_dir" in paths
        assert "audio_dir" in paths
        assert "meta_path" in paths

    def test_paths_use_settings_values(self, mock_settings):
        """Paths use values from settings."""
        mock_settings.logs_dir = "/custom/logs"
        mock_settings.audio_sessions_subdir = "recordings"
        
        paths = build_session_paths(mock_settings, "my-session", create=False)
        
        # Cross-platform: check path components, not separators
        assert "custom" in paths["base_dir"]
        assert "logs" in paths["base_dir"]
        assert "recordings" in paths["base_dir"]
        assert "my-session" in paths["base_dir"]

    def test_paths_structure(self, mock_settings):
        """Paths follow the expected structure."""
        paths = build_session_paths(mock_settings, "2025-01-01_12-00-00_g123", create=False)
        
        expected_base = Path(".logs") / "audio" / "2025-01-01_12-00-00_g123"
        assert paths["base_dir"] == str(expected_base)
        assert paths["audio_dir"] == str(expected_base)
        assert paths["meta_path"] == str(expected_base / "session_meta.json")

    def test_creates_directory_when_create_true(self, mock_settings, tmp_path):
        """Creates the directory if create=True."""
        mock_settings.logs_dir = str(tmp_path)
        
        paths = build_session_paths(mock_settings, "new-session", create=True)
        
        assert Path(paths["base_dir"]).exists()
        assert Path(paths["base_dir"]).is_dir()

    def test_does_not_create_directory_when_create_false(self, mock_settings, tmp_path):
        """Does not create the directory if create=False."""
        mock_settings.logs_dir = str(tmp_path)
        
        paths = build_session_paths(mock_settings, "no-create-session", create=False)
        
        assert not Path(paths["base_dir"]).exists()

    def test_nested_directory_creation(self, mock_settings, tmp_path):
        """Creates parent directories if needed."""
        mock_settings.logs_dir = str(tmp_path / "deep" / "nested")
        
        paths = build_session_paths(mock_settings, "session", create=True)
        
        assert Path(paths["base_dir"]).exists()


# =============================================================================
# apply_paths_to_session
# =============================================================================
class TestApplyPathsToSession:
    @pytest.fixture
    def session(self):
        """Test session."""
        return AudioSessionInfo(
            session_id="2025-01-01_00-00-00_g111",
            guild_id=111,
            mode="record_only",
            started_at=datetime(2025, 1, 1, 0, 0, 0),
        )

    def test_sets_all_paths(self, session, mock_settings):
        """Populates base_dir, audio_dir, and meta_path."""
        apply_paths_to_session(session, mock_settings, create=False)
        
        assert session.base_dir != ""
        assert session.audio_dir != ""
        assert session.meta_path != ""

    def test_paths_match_build_session_paths(self, session, mock_settings):
        """Paths match build_session_paths."""
        expected = build_session_paths(mock_settings, session.session_id, create=False)
        
        apply_paths_to_session(session, mock_settings, create=False)
        
        assert session.base_dir == expected["base_dir"]
        assert session.audio_dir == expected["audio_dir"]
        assert session.meta_path == expected["meta_path"]

    def test_returns_session(self, session, mock_settings):
        """Returns the modified session."""
        result = apply_paths_to_session(session, mock_settings, create=False)
        
        assert result is session

    def test_creates_directory_when_create_true(self, session, mock_settings, tmp_path):
        """Creates the directory if create=True."""
        mock_settings.logs_dir = str(tmp_path)
        
        apply_paths_to_session(session, mock_settings, create=True)
        
        assert Path(session.base_dir).exists()

    def test_does_not_create_when_create_false(self, session, mock_settings, tmp_path):
        """Does not create the directory if create=False."""
        mock_settings.logs_dir = str(tmp_path)
        
        apply_paths_to_session(session, mock_settings, create=False)
        
        assert not Path(session.base_dir).exists()
