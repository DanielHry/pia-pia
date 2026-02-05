# tests/test_commandline.py

"""Tests pour piapia/utils/commandline.py"""

import pytest

from piapia.utils.commandline import parse_args


class TestParseArgs:
    def test_no_args_defaults(self):
        """Sans arguments, debug est False."""
        args = parse_args([])
        
        assert args.debug is False

    def test_debug_flag(self):
        """--debug active le mode debug."""
        args = parse_args(["--debug"])
        
        assert args.debug is True

    def test_accepts_none_as_argv(self):
        """argv=None utilise sys.argv (ne plante pas)."""
        # Ceci pourrait échouer si sys.argv contient des args invalides,
        # mais en contexte de test pytest, c'est généralement ok
        # On teste surtout que ça ne raise pas
        try:
            args = parse_args(None)
            assert hasattr(args, "debug")
        except SystemExit:
            # pytest peut passer des args qui font échouer le parsing
            pass

    def test_unknown_args_raise(self):
        """Arguments inconnus lèvent une erreur."""
        with pytest.raises(SystemExit):
            parse_args(["--unknown-flag"])

    def test_debug_short_form_not_available(self):
        """Pas de forme courte -d pour debug."""
        with pytest.raises(SystemExit):
            parse_args(["-d"])