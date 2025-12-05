# src/utils/commandline.py

import argparse
from typing import Optional, Sequence


def parse_args(argv: Optional[Sequence[str]] = None):
    """
    Parse les arguments de la ligne de commande.

    Pour l'instant, on gère surtout :
      --debug : active le mode debug (logs plus verbeux)
    """

    parser = argparse.ArgumentParser(
        description="Pia-Pia Bot - transcription Discord pour JDR"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Active les logs en niveau DEBUG (plus verbeux).",
    )

    # Tu pourras ajouter d'autres options ici plus tard, par ex :
    # parser.add_argument("--config", type=str, help="Chemin vers un fichier de config...")

    args = parser.parse_args(argv)
    return args
