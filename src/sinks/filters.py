# src/sinks/filters.py

import re

# Patterns pour les hallucinations type "Sous-titrage ..."
NOISE_PATTERNS = [
    r"^sous-?titrage st'? 501$",
    r"^sous-?titrage fr \?$",
    r"^sous-?titrage société radio-canada$",
    r"^sous-?titres par jérémy diaz$",
    r"^– sous-?titrage fr 2021$",
]


def is_subtitle_noise(text: str) -> bool:
    """
    Retourne True si le texte ressemble à une hallucination de type
    "Sous-titrage ..." qu'on souhaite filtrer.
    """
    if not text:
        return False

    t = text.strip().lower()
    for pattern in NOISE_PATTERNS:
        if re.match(pattern, t):
            return True
    return False
