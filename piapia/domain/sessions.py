# piapia/domain/sessions.py

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Mapping, Optional


SessionMode = Literal["record_only"]


def _dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _dt_from_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


def make_session_id(guild_id: int, now: Optional[datetime] = None) -> str:
    """
    Génère un session_id stable.
    Ex: "2025-12-09_20-30-00_g941688253159968788"
    """
    now = now or datetime.now(timezone.utc)
    return f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_g{guild_id}"


@dataclass
class PlayerSessionInfo:
    user_id: int
    player: Optional[str] = None
    character: Optional[str] = None

    # V1: on privilégie un offset (plus simple pour l’offline)
    first_offset_seconds: Optional[float] = None

    # Optionnel si tu veux aussi garder une date absolue
    first_spoke_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "player": self.player,
            "character": self.character,
            "first_offset_seconds": self.first_offset_seconds,
            "first_spoke_at": _dt_to_iso(self.first_spoke_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlayerSessionInfo":
        return cls(
            user_id=int(data["user_id"]),
            player=data.get("player"),
            character=data.get("character"),
            first_offset_seconds=data.get("first_offset_seconds"),
            first_spoke_at=_dt_from_iso(data.get("first_spoke_at")),
        )


@dataclass
class AudioSessionInfo:
    session_id: str
    guild_id: int
    mode: SessionMode

    started_at: datetime
    ended_at: Optional[datetime] = None
    label: Optional[str] = None

    # Chemins (remplis à la création de session)
    base_dir: str = ""
    audio_dir: str = ""
    meta_path: str = ""

    # Infos joueurs : user_id -> info
    players: Dict[int, PlayerSessionInfo] = field(default_factory=dict)

    # Permet d’absorber des champs additionnels sans casser le parsing
    extra: Dict[str, Any] = field(default_factory=dict)

    def add_or_update_player(
        self,
        user_id: int,
        player: Optional[str] = None,
        character: Optional[str] = None,
    ) -> PlayerSessionInfo:
        info = self.players.get(user_id)
        if info is None:
            info = PlayerSessionInfo(user_id=user_id)
            self.players[user_id] = info

        if player is not None:
            info.player = player
        if character is not None:
            info.character = character

        return info

    def to_dict(self) -> Dict[str, Any]:
        # JSON n’aime pas les clés int => on force en str pour être explicite
        players_dict = {str(uid): p.to_dict() for uid, p in self.players.items()}

        data: Dict[str, Any] = {
            "session_id": self.session_id,
            "guild_id": self.guild_id,
            "mode": self.mode,
            "started_at": _dt_to_iso(self.started_at),
            "ended_at": _dt_to_iso(self.ended_at),
            "label": self.label,
            "base_dir": self.base_dir,
            "audio_dir": self.audio_dir,
            "meta_path": self.meta_path,
            "players": players_dict,
        }

        # Extra (si on veut stocker offset map, start_ts, etc.)
        if self.extra:
            data["extra"] = self.extra

        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AudioSessionInfo":
        raw_players = data.get("players") or {}
        players: Dict[int, PlayerSessionInfo] = {}

        # On accepte dict { "123": {...} } ou liste [{...}, {...}]
        if isinstance(raw_players, dict):
            for k, v in raw_players.items():
                try:
                    uid = int(k)
                except (TypeError, ValueError):
                    uid = int(v.get("user_id"))
                players[uid] = PlayerSessionInfo.from_dict(v)
        elif isinstance(raw_players, list):
            for item in raw_players:
                p = PlayerSessionInfo.from_dict(item)
                players[p.user_id] = p

        return cls(
            session_id=str(data["session_id"]),
            guild_id=int(data["guild_id"]),
            mode=data["mode"],  # type: ignore[assignment]
            started_at=_dt_from_iso(data.get("started_at")) or datetime.now(timezone.utc),
            ended_at=_dt_from_iso(data.get("ended_at")),
            label=data.get("label"),
            base_dir=data.get("base_dir", ""),
            audio_dir=data.get("audio_dir", ""),
            meta_path=data.get("meta_path", ""),
            players=players,
            extra=dict(data.get("extra") or {}),
        )

    def save_json(self, path: Optional[str] = None, indent: int = 2) -> str:
        """
        Sauvegarde la session en JSON (session_meta.json).
        Retourne le chemin écrit.
        """
        out_path = path or self.meta_path
        if not out_path:
            raise ValueError("Aucun chemin de sortie (meta_path) défini pour la session.")

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=indent)

        return out_path

    @classmethod
    def load_json(cls, path: str) -> "AudioSessionInfo":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
