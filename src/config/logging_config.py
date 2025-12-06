# src/config/logging_config.py

import logging
import logging.config
import os

from src.config.settings import Settings


def configure_logging(settings: Settings) -> None:
    """
    Configure le logging global de l'application à partir des Settings.

    - Root logger : console (niveau INFO ou DEBUG selon settings.debug)
    - Logger 'transcription' : plus de handler par défaut, il est configuré
      dynamiquement par DiscordSink pour écrire dans un fichier par session.
    """

    # Répertoires de base
    logs_dir = settings.logs_dir
    transcripts_dir = os.path.join(logs_dir, settings.transcripts_subdir)
    pdf_dir = os.path.join(logs_dir, settings.pdf_subdir)
    audio_dir = os.path.join(logs_dir, settings.audio_archive_subdir)

    os.makedirs(transcripts_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    # Niveau de log global
    level = logging.DEBUG if settings.debug else logging.INFO

    # Config dictConfig
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "standard",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            # Logger dédié aux transcriptions JSON.
            # -> Pas de handler par défaut : DiscordSink ajoute/retire
            #    son propre FileHandler par session.
            "transcription": {
                "handlers": [],
                "level": "INFO",
                "propagate": False,  # on évite que le JSON aille dans la console
            },
            # Réduire le bruit de certaines libs
            "discord": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "asyncio": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpx": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": level,
        },
    }

    logging.config.dictConfig(config)
