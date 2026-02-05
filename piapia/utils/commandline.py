# piapia/utils/commandline.py

import argparse
from typing import Optional, Sequence


def parse_args(argv: Optional[Sequence[str]] = None):
    """
    Parse command-line arguments.

    For now, we mainly handle:
      --debug : enable debug mode (more verbose logs)
    """

    parser = argparse.ArgumentParser(
        description="Pia-Pia Bot - Discord voice recorder."
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG-level logs (more verbose).",
    )

    # You can add more options here later, e.g.:
    # parser.add_argument("--config", type=str, help="Path to a config file...")

    args = parser.parse_args(argv)
    return args
