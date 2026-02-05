# tests/test_audio_archiver.py

"""Tests pour piapia/sinks/audio_archiver.py"""

import wave
from pathlib import Path

import pytest

from piapia.sinks.audio_archiver import AudioArchiver


@pytest.fixture
def archiver(tmp_path):
    """AudioArchiver configuré pour les tests."""
    return AudioArchiver(
        base_dir=str(tmp_path),
        session_id="test-session",
        channels=2,
        sample_width=2,
        sample_rate=48000,
        audio_format="wav",
    )


@pytest.fixture
def pcm_data():
    """Données PCM de test (1 seconde de silence stéréo 48kHz 16-bit)."""
    # 48000 samples * 2 channels * 2 bytes = 192000 bytes
    return b"\x00" * 192000


# =============================================================================
# Initialisation
# =============================================================================
class TestArchiverInit:
    def test_creates_session_directory(self, tmp_path):
        """Le constructeur crée le dossier de session."""
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
        """Les paramètres audio sont stockés."""
        archiver = AudioArchiver(
            base_dir=str(tmp_path),
            session_id="session",
            channels=1,
            sample_width=4,
            sample_rate=44100,
            audio_format="flac",
        )
        
        assert archiver.channels == 1
        assert archiver.sample_width == 4
        assert archiver.sample_rate == 44100
        assert archiver.audio_format == "flac"

    def test_normalizes_audio_format(self, tmp_path):
        """Le format audio est normalisé (lowercase, strip)."""
        archiver = AudioArchiver(
            base_dir=str(tmp_path),
            session_id="session",
            channels=2,
            sample_width=2,
            sample_rate=48000,
            audio_format="  MP3  ",
        )
        
        assert archiver.audio_format == "mp3"

    def test_bytes_written_starts_at_zero(self, archiver):
        """bytes_written commence à 0."""
        assert archiver.bytes_written == 0


# =============================================================================
# append
# =============================================================================
class TestArchiverAppend:
    def test_creates_wav_file_for_user(self, archiver, pcm_data, tmp_path):
        """append crée un fichier WAV pour l'utilisateur."""
        archiver.append(user_id=12345, data=pcm_data)
        archiver.close()
        
        wav_path = tmp_path / "test-session" / "user_12345.wav"
        assert wav_path.exists()

    def test_tracks_bytes_written(self, archiver, pcm_data):
        """append incrémente bytes_written."""
        archiver.append(user_id=1, data=pcm_data)
        
        assert archiver.bytes_written == len(pcm_data)

    def test_multiple_appends_accumulate(self, archiver, pcm_data):
        """Plusieurs appends s'accumulent."""
        archiver.append(user_id=1, data=pcm_data)
        archiver.append(user_id=1, data=pcm_data)
        archiver.append(user_id=2, data=pcm_data)
        
        assert archiver.bytes_written == 3 * len(pcm_data)

    def test_different_users_different_files(self, archiver, pcm_data, tmp_path):
        """Chaque utilisateur a son propre fichier."""
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
        """close produit des fichiers WAV valides."""
        archiver.append(user_id=1, data=pcm_data)
        archiver.close()
        
        wav_path = tmp_path / "test-session" / "user_1.wav"
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 48000
            assert wf.getnframes() == 48000  # 1 seconde

    def test_wav_format_no_conversion(self, archiver, pcm_data, tmp_path):
        """Format WAV : pas de conversion, fichiers conservés."""
        archiver.append(user_id=1, data=pcm_data)
        archiver.close()
        
        wav_path = tmp_path / "test-session" / "user_1.wav"
        assert wav_path.exists()

    def test_double_close_is_safe(self, archiver, pcm_data):
        """Appeler close() deux fois ne cause pas d'erreur."""
        archiver.append(user_id=1, data=pcm_data)
        archiver.close()
        archiver.close()  # Doit être idempotent

    def test_close_without_data(self, archiver):
        """close() sans données n'échoue pas."""
        archiver.close()  # Pas d'exception


# =============================================================================
# Conversion de format (nécessite ffmpeg)
# =============================================================================
class TestArchiverConversion:
    @pytest.fixture
    def mp3_archiver(self, tmp_path):
        """AudioArchiver configuré pour MP3."""
        return AudioArchiver(
            base_dir=str(tmp_path),
            session_id="mp3-session",
            channels=2,
            sample_width=2,
            sample_rate=48000,
            audio_format="mp3",
        )

    def test_mp3_conversion_removes_wav(self, mp3_archiver, pcm_data, tmp_path):
        """La conversion MP3 supprime le WAV source (si ffmpeg disponible)."""
        mp3_archiver.append(user_id=1, data=pcm_data)
        mp3_archiver.close()
        
        session_dir = tmp_path / "mp3-session"
        wav_files = list(session_dir.glob("*.wav"))
        mp3_files = list(session_dir.glob("*.mp3"))
        
        # Soit la conversion a réussi (MP3 présent, WAV supprimé)
        # Soit ffmpeg n'est pas installé (WAV conservé)
        if mp3_files:
            assert len(mp3_files) == 1
            assert len(wav_files) == 0
        else:
            # ffmpeg non disponible, WAV conservé
            assert len(wav_files) == 1

    def test_flac_conversion(self, tmp_path, pcm_data):
        """Test de conversion FLAC."""
        archiver = AudioArchiver(
            base_dir=str(tmp_path),
            session_id="flac-session",
            channels=2,
            sample_width=2,
            sample_rate=48000,
            audio_format="flac",
        )
        archiver.append(user_id=1, data=pcm_data)
        archiver.close()
        
        session_dir = tmp_path / "flac-session"
        wav_files = list(session_dir.glob("*.wav"))
        flac_files = list(session_dir.glob("*.flac"))
        
        # Même logique : si ffmpeg ok, FLAC présent
        if flac_files:
            assert len(flac_files) == 1
            assert len(wav_files) == 0


# =============================================================================
# Paramètres audio
# =============================================================================
class TestArchiverAudioParams:
    def test_mono_audio(self, tmp_path, pcm_data):
        """Support de l'audio mono."""
        archiver = AudioArchiver(
            base_dir=str(tmp_path),
            session_id="mono-session",
            channels=1,
            sample_width=2,
            sample_rate=48000,
        )
        # Données mono (moitié de la taille stéréo)
        mono_data = b"\x00" * 96000
        archiver.append(user_id=1, data=mono_data)
        archiver.close()
        
        wav_path = tmp_path / "mono-session" / "user_1.wav"
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 1

    def test_different_sample_rate(self, tmp_path):
        """Support de différents sample rates."""
        archiver = AudioArchiver(
            base_dir=str(tmp_path),
            session_id="44k-session",
            channels=2,
            sample_width=2,
            sample_rate=44100,
        )
        # 1 seconde à 44.1kHz stéréo 16-bit
        data = b"\x00" * (44100 * 2 * 2)
        archiver.append(user_id=1, data=data)
        archiver.close()
        
        wav_path = tmp_path / "44k-session" / "user_1.wav"
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getframerate() == 44100