# piapia/config/logging_config.py

import logging
import logging.config
import logging.handlers
import os

from piapia.config.settings import Settings


def configure_logging(settings: Settings) -> None:
    """
    Configure le logging global de l'application à partir des Settings.

    - Root logger : console + fichier app (.logs/app/pia-pia.log)
    """

    # ------------------------------------------------------------------ #
    # 1) Répertoires de logs
    # ------------------------------------------------------------------ #
    logs_dir = settings.logs_dir
    app_dir = os.path.join(logs_dir, "app")
    os.makedirs(app_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 2) Fichiers de logs
    # ------------------------------------------------------------------ #
    app_log_file = os.path.join(app_dir, "pia-pia.log")

    # ------------------------------------------------------------------ #
    # 3) Niveau de log global
    # ------------------------------------------------------------------ #
    level = logging.DEBUG if settings.debug else logging.INFO
    logging.captureWarnings(True)

    # ------------------------------------------------------------------ #
    # 4) dictConfig
    # ------------------------------------------------------------------ #
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
            # Log général du bot : tout ce qui passe par le root + libs
            "app_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": level,
                "formatter": "standard",
                "filename": app_log_file,
                "mode": "a",
                "maxBytes": 10_000_000,   # 10 MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            # Réduire le bruit de certaines libs
            "discord": {
                "handlers": ["console", "app_file"],
                "level": "WARNING",
                "propagate": False,
            },
            "asyncio": {
                "handlers": ["console", "app_file"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpx": {
                "handlers": ["console", "app_file"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["console", "app_file"],
                "level": "WARNING",
                "propagate": False,
            },
            "py.warnings": {
                "handlers": ["console", "app_file"],
                "level": "WARNING",
                "propagate": False,
            },
        },
        # Root : tout le reste (ton code) → console + app_file
        "root": {
            "handlers": ["console", "app_file"],
            "level": level,
        },
    }

    logging.config.dictConfig(config)
