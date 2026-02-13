# tests/test_audio_archiver.py

"""Tests for piapia/sinks/audio_archiver.py"""

import wave
from pathlib import Path

import pytest

from piapia.sinks.audio_archiver import AudioArchiver


@pytest.fixture
def archiver(tmp_path):
    """AudioArchiver configured for tests."""
    return AudioArchiver(
        base_dir=str(tmp_path),
        session_id="test-session",
        channels=2,
        sample_width=2,
        sample_rate=48000,
    )


@pytest.fixture
def pcm_data():
    """Test PCM data (1 second of 48kHz 16-bit stereo silence)."""
    # 48000 samples * 2 channels * 2 bytes = 192000 bytes
    return b"\x00" * 192000


# =============================================================================
# Initialization
# =============================================================================
class TestArchiverInit:
    def test_creates_session_directory(self, tmp_path):
        """The constructor creates the session directory."""
        archiver = AudioArchiver(
            base_dir=str(tmp_path),
            session_id="new-session",
            channels=2,
            sample_width=2,
            sample_rate=48000,
        )
        
        assert (tmp_path / "new-session").exists()
        assert (tmp_path / "new-session").is_dir()

    def test_stores_audio_parameters(self, tmp_path):
        """Audio parameters are stored."""
        archiver = AudioArchiver(
            base_dir=str(tmp_path),
            session_id="session",
            channels=1,
            sample_width=4,
            sample_rate=44100,
        )
        
        assert archiver.channels == 1
        assert archiver.sample_width == 4
        assert archiver.sample_rate == 44100

    def test_bytes_written_starts_at_zero(self, archiver):
        """bytes_written starts at 0."""
        assert archiver.bytes_written == 0


# =============================================================================
# append
# =============================================================================
class TestArchiverAppend:
    def test_creates_wav_file_for_user(self, archiver, pcm_data, tmp_path):
        """append creates a WAV file for the user."""
        archiver.append(user_id=12345, data=pcm_data)
        archiver.close()
        
        wav_path = tmp_path / "test-session" / "user_12345.wav"
        assert wav_path.exists()

    def test_tracks_bytes_written(self, archiver, pcm_data):
        """append increments bytes_written."""
        archiver.append(user_id=1, data=pcm_data)
        
        assert archiver.bytes_written == len(pcm_data)

    def test_multiple_appends_accumulate(self, archiver, pcm_data):
        """Multiple appends accumulate."""
        archiver.append(user_id=1, data=pcm_data)
        archiver.append(user_id=1, data=pcm_data)
        archiver.append(user_id=2, data=pcm_data)
        
        assert archiver.bytes_written == 3 * len(pcm_data)

    def test_different_users_different_files(self, archiver, pcm_data, tmp_path):
        """Each user gets their own file."""
        archiver.append(user_id=100, data=pcm_data)
        archiver.append(user_id=200, data=pcm_data)
        archiver.close()
        
        assert (tmp_path / "test-session" / "user_100.wav").exists()
        assert (tmp_path / "test-session" / "user_200.wav").exists()


# =============================================================================
# close
# =============================================================================
class TestArchiverClose:
    def test_creates_valid_wav_files(self, archiver, pcm_data, tmp_path):
        """close produces valid WAV files."""
        archiver.append(user_id=1, data=pcm_data)
        archiver.close()
        
        wav_path = tmp_path / "test-session" / "user_1.wav"
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 48000
            assert wf.getnframes() == 48000  # 1 second

    def test_wav_format_no_conversion(self, archiver, pcm_data, tmp_path):
        """WAV format: no conversion; files are preserved."""
        archiver.append(user_id=1, data=pcm_data)
        archiver.close()
        
        wav_path = tmp_path / "test-session" / "user_1.wav"
        assert wav_path.exists()

    def test_double_close_is_safe(self, archiver, pcm_data):
        """Calling close() twice does not raise an error."""
        archiver.append(user_id=1, data=pcm_data)
        archiver.close()
        archiver.close()  # Should be idempotent

    def test_close_without_data(self, archiver):
        """close() without any data does not fail."""
        archiver.close()  # No exception


# =============================================================================
# Audio parameters
# =============================================================================
class TestArchiverAudioParams:
    def test_mono_audio(self, tmp_path, pcm_data):
        """Mono audio support."""
        archiver = AudioArchiver(
            base_dir=str(tmp_path),
            session_id="mono-session",
            channels=1,
            sample_width=2,
            sample_rate=48000,
        )
        # Mono data (half the size of stereo)
        mono_data = b"\x00" * 96000
        archiver.append(user_id=1, data=mono_data)
        archiver.close()
        
        wav_path = tmp_path / "mono-session" / "user_1.wav"
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 1

    def test_different_sample_rate(self, tmp_path):
        """Support for different sample rates."""
        archiver = AudioArchiver(
            base_dir=str(tmp_path),
            session_id="44k-session",
            channels=2,
            sample_width=2,
            sample_rate=44100,
        )
        # 1 second at 44.1kHz stereo 16-bit
        data = b"\x00" * (44100 * 2 * 2)
        archiver.append(user_id=1, data=data)
        archiver.close()
        
        wav_path = tmp_path / "44k-session" / "user_1.wav"
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getframerate() == 44100
