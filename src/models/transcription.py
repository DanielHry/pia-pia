# src/models/transcription.py

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TranscriptionEvent(BaseModel):
    guild_id: int
    user_id: int
    player: Optional[str]
    character: Optional[str]
    event_source: str = "Discord"

    start: datetime
    end: datetime

    text: str
    is_noise: bool = False
    error: Optional[str] = None
