# piapia/utils/session_paths.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from piapia.config.settings import Settings
    from piapia.domain.sessions import AudioSessionInfo


def build_session_paths(settings: "Settings", session_id: str, create: bool = True) -> Dict[str, str]:
    """
    Build standardized paths for a session.

    Convention:
      - Audio: .logs/audio/<session_id>/user_<id>.wav
      - Meta:  .logs/audio/<session_id>/session_meta.json

    Returns a dict of str (paths) for easy storage in AudioSessionInfo.
    """
    logs_dir = Path(settings.logs_dir)

    # Audio session folder
    base_dir = logs_dir / settings.audio_sessions_subdir / session_id

    # Here, audio_dir == base_dir (WAV files are written directly into this folder)
    audio_dir = base_dir

    # Meta
    meta_path = base_dir / "session_meta.json"

    if create:
        base_dir.mkdir(parents=True, exist_ok=True)

    return {
        "base_dir": str(base_dir),
        "audio_dir": str(audio_dir),
        "meta_path": str(meta_path),
    }


def apply_paths_to_session(
    session: "AudioSessionInfo",
    settings: "Settings",
    create: bool = True,
) -> "AudioSessionInfo":
    """
    Apply standardized paths to an AudioSessionInfo session.
    """
    paths = build_session_paths(settings, session.session_id, create=create)
    session.base_dir = paths["base_dir"]
    session.audio_dir = paths["audio_dir"]
    session.meta_path = paths["meta_path"]
    return session
