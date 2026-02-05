# tests/test_sessions.py

"""Tests pour piapia/domain/sessions.py"""

import json
from datetime import datetime, timezone

import pytest

from piapia.domain.sessions import (
    AudioSessionInfo,
    PlayerSessionInfo,
    make_session_id,
)


# =============================================================================
# make_session_id
# =============================================================================
class TestMakeSessionId:
    def test_format_with_explicit_datetime(self):
        """Le session_id suit le format attendu."""
        dt = datetime(2025, 12, 9, 20, 30, 45)
        guild_id = 123456789
        
        session_id = make_session_id(guild_id, now=dt)
        
        assert session_id == "2025-12-09_20-30-45_g123456789"

    def test_uses_current_time_by_default(self):
        """Sans datetime fourni, utilise l'heure courante (UTC)."""
        guild_id = 987654321
        
        session_id = make_session_id(guild_id)
        
        # Le session_id doit contenir le guild_id
        assert f"_g{guild_id}" in session_id
        # Et commencer par une date valide au format attendu
        date_part = session_id.split("_g")[0]
        # Vérifie que le format est correct (ne lève pas d'exception)
        parsed = datetime.strptime(date_part, "%Y-%m-%d_%H-%M-%S")
        # La date doit être raisonnable (pas dans le passé lointain ni le futur)
        assert parsed.year >= 2024

    def test_different_guilds_produce_different_ids(self):
        """Deux guildes différentes ont des session_ids différents."""
        dt = datetime(2025, 1, 1, 12, 0, 0)
        
        id1 = make_session_id(111, now=dt)
        id2 = make_session_id(222, now=dt)
        
        assert id1 != id2
        assert "_g111" in id1
        assert "_g222" in id2


# =============================================================================
# PlayerSessionInfo
# =============================================================================
class TestPlayerSessionInfo:
    def test_to_dict_minimal(self):
        """Sérialisation avec seulement user_id."""
        player = PlayerSessionInfo(user_id=12345)
        
        data = player.to_dict()
        
        assert data["user_id"] == 12345
        assert data["player"] is None
        assert data["character"] is None
        assert data["first_offset_seconds"] is None
        assert data["first_spoke_at"] is None

    def test_to_dict_full(self):
        """Sérialisation avec tous les champs."""
        dt = datetime(2025, 6, 15, 14, 30, 0)
        player = PlayerSessionInfo(
            user_id=12345,
            player="Jean",
            character="Gandalf",
            first_offset_seconds=42.5,
            first_spoke_at=dt,
        )
        
        data = player.to_dict()
        
        assert data["user_id"] == 12345
        assert data["player"] == "Jean"
        assert data["character"] == "Gandalf"
        assert data["first_offset_seconds"] == 42.5
        assert data["first_spoke_at"] == dt.isoformat()

    def test_from_dict_minimal(self):
        """Désérialisation avec seulement user_id."""
        data = {"user_id": 99999}
        
        player = PlayerSessionInfo.from_dict(data)
        
        assert player.user_id == 99999
        assert player.player is None
        assert player.character is None

    def test_from_dict_full(self):
        """Désérialisation avec tous les champs."""
        data = {
            "user_id": "12345",  # string, doit être converti en int
            "player": "Marie",
            "character": "Elara",
            "first_offset_seconds": 10.0,
            "first_spoke_at": "2025-06-15T14:30:00",
        }
        
        player = PlayerSessionInfo.from_dict(data)
        
        assert player.user_id == 12345
        assert player.player == "Marie"
        assert player.character == "Elara"
        assert player.first_offset_seconds == 10.0
        assert player.first_spoke_at == datetime(2025, 6, 15, 14, 30, 0)

    def test_roundtrip(self):
        """to_dict puis from_dict conserve les données."""
        original = PlayerSessionInfo(
            user_id=42,
            player="Test",
            character="Hero",
            first_offset_seconds=5.5,
            first_spoke_at=datetime(2025, 1, 1, 0, 0, 0),
        )
        
        data = original.to_dict()
        restored = PlayerSessionInfo.from_dict(data)
        
        assert restored.user_id == original.user_id
        assert restored.player == original.player
        assert restored.character == original.character
        assert restored.first_offset_seconds == original.first_offset_seconds
        assert restored.first_spoke_at == original.first_spoke_at


# =============================================================================
# AudioSessionInfo
# =============================================================================
class TestAudioSessionInfo:
    @pytest.fixture
    def minimal_session(self):
        """Session avec les champs obligatoires uniquement."""
        return AudioSessionInfo(
            session_id="2025-01-01_00-00-00_g111",
            guild_id=111,
            mode="record_only",
            started_at=datetime(2025, 1, 1, 0, 0, 0),
        )

    @pytest.fixture
    def full_session(self):
        """Session avec tous les champs remplis."""
        session = AudioSessionInfo(
            session_id="2025-06-15_14-30-00_g222",
            guild_id=222,
            mode="record_only",
            started_at=datetime(2025, 6, 15, 14, 30, 0),
            ended_at=datetime(2025, 6, 15, 16, 0, 0),
            label="Session de test",
            base_dir="/tmp/audio/session1",
            audio_dir="/tmp/audio/session1",
            meta_path="/tmp/audio/session1/session_meta.json",
        )
        session.add_or_update_player(1001, player="Alice", character="Mage")
        session.add_or_update_player(1002, player="Bob", character="Warrior")
        session.extra = {"custom_field": "value"}
        return session

    def test_to_dict_minimal(self, minimal_session):
        """Sérialisation d'une session minimale."""
        data = minimal_session.to_dict()
        
        assert data["session_id"] == "2025-01-01_00-00-00_g111"
        assert data["guild_id"] == 111
        assert data["mode"] == "record_only"
        assert data["started_at"] == "2025-01-01T00:00:00"
        assert data["ended_at"] is None
        assert data["players"] == {}

    def test_to_dict_full(self, full_session):
        """Sérialisation d'une session complète."""
        data = full_session.to_dict()
        
        assert data["session_id"] == "2025-06-15_14-30-00_g222"
        assert data["label"] == "Session de test"
        assert "1001" in data["players"]  # clés converties en string
        assert "1002" in data["players"]
        assert data["players"]["1001"]["player"] == "Alice"
        assert data["extra"]["custom_field"] == "value"

    def test_from_dict_minimal(self):
        """Désérialisation d'une session minimale."""
        data = {
            "session_id": "test-session",
            "guild_id": 333,
            "mode": "record_only",
            "started_at": "2025-01-01T12:00:00",
        }
        
        session = AudioSessionInfo.from_dict(data)
        
        assert session.session_id == "test-session"
        assert session.guild_id == 333
        assert session.mode == "record_only"
        assert session.players == {}

    def test_from_dict_with_players_as_dict(self):
        """Désérialisation avec players en format dict."""
        data = {
            "session_id": "test",
            "guild_id": 1,
            "mode": "record_only",
            "started_at": "2025-01-01T00:00:00",
            "players": {
                "123": {"user_id": 123, "player": "Test", "character": "Hero"},
            },
        }
        
        session = AudioSessionInfo.from_dict(data)
        
        assert 123 in session.players
        assert session.players[123].player == "Test"

    def test_from_dict_with_players_as_list(self):
        """Désérialisation avec players en format liste."""
        data = {
            "session_id": "test",
            "guild_id": 1,
            "mode": "record_only",
            "started_at": "2025-01-01T00:00:00",
            "players": [
                {"user_id": 456, "player": "Alice", "character": "Mage"},
                {"user_id": 789, "player": "Bob", "character": "Tank"},
            ],
        }
        
        session = AudioSessionInfo.from_dict(data)
        
        assert 456 in session.players
        assert 789 in session.players
        assert session.players[456].character == "Mage"

    def test_from_dict_missing_started_at_uses_now(self):
        """Sans started_at, utilise datetime.now(timezone.utc)."""
        data = {
            "session_id": "test",
            "guild_id": 1,
            "mode": "record_only",
        }
        before = datetime.now(timezone.utc)
        
        session = AudioSessionInfo.from_dict(data)
        
        after = datetime.now(timezone.utc)
        # Si started_at est naive (pas de timezone), on le compare en naive
        if session.started_at.tzinfo is None:
            before = before.replace(tzinfo=None)
            after = after.replace(tzinfo=None)
        assert before <= session.started_at <= after

    def test_roundtrip(self, full_session):
        """to_dict puis from_dict conserve les données."""
        data = full_session.to_dict()
        restored = AudioSessionInfo.from_dict(data)
        
        assert restored.session_id == full_session.session_id
        assert restored.guild_id == full_session.guild_id
        assert restored.mode == full_session.mode
        assert restored.label == full_session.label
        assert len(restored.players) == len(full_session.players)
        assert restored.extra == full_session.extra

    def test_add_or_update_player_creates_new(self, minimal_session):
        """add_or_update_player crée un nouveau joueur."""
        minimal_session.add_or_update_player(999, player="New", character="Char")
        
        assert 999 in minimal_session.players
        assert minimal_session.players[999].player == "New"
        assert minimal_session.players[999].character == "Char"

    def test_add_or_update_player_updates_existing(self, minimal_session):
        """add_or_update_player met à jour un joueur existant."""
        minimal_session.add_or_update_player(999, player="First")
        minimal_session.add_or_update_player(999, character="Updated")
        
        assert minimal_session.players[999].player == "First"  # inchangé
        assert minimal_session.players[999].character == "Updated"

    def test_save_and_load_json(self, full_session, tmp_path):
        """save_json puis load_json conserve les données."""
        json_path = tmp_path / "session_meta.json"
        full_session.meta_path = str(json_path)
        
        full_session.save_json()
        loaded = AudioSessionInfo.load_json(str(json_path))
        
        assert loaded.session_id == full_session.session_id
        assert loaded.guild_id == full_session.guild_id
        assert len(loaded.players) == len(full_session.players)

    def test_save_json_creates_directory(self, minimal_session, tmp_path):
        """save_json crée le dossier parent si nécessaire."""
        deep_path = tmp_path / "a" / "b" / "c" / "meta.json"
        minimal_session.meta_path = str(deep_path)
        
        minimal_session.save_json()
        
        assert deep_path.exists()

    def test_save_json_without_path_raises(self, minimal_session):
        """save_json sans meta_path lève une erreur."""
        minimal_session.meta_path = ""
        
        with pytest.raises(ValueError, match="Aucun chemin"):
            minimal_session.save_json()

    def test_save_json_custom_path(self, minimal_session, tmp_path):
        """save_json avec chemin explicite utilise ce chemin."""
        custom_path = tmp_path / "custom.json"
        
        result = minimal_session.save_json(path=str(custom_path))
        
        assert result == str(custom_path)
        assert custom_path.exists()