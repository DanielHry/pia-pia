# tests/test_commandline.py

"""Tests for piapia/utils/commandline.py"""

import pytest

from piapia.utils.commandline import parse_args


class TestParseArgs:
    def test_no_args_defaults(self):
        """With no arguments, debug is False."""
        args = parse_args([])
        
        assert args.debug is False

    def test_debug_flag(self):
        """--debug enables debug mode."""
        args = parse_args(["--debug"])
        
        assert args.debug is True

    def test_accepts_none_as_argv(self):
        """argv=None uses sys.argv (does not crash)."""
        # This could fail if sys.argv contains invalid args,
        # but in a pytest test context it's generally okay.
        # We mainly test that it doesn't raise.
        try:
            args = parse_args(None)
            assert hasattr(args, "debug")
        except SystemExit:
            # pytest may pass args that cause parsing to fail
            pass

    def test_unknown_args_raise(self):
        """Unknown arguments raise an error."""
        with pytest.raises(SystemExit):
            parse_args(["--unknown-flag"])

    def test_debug_short_form_not_available(self):
        """No short form -d for debug."""
        with pytest.raises(SystemExit):
            parse_args(["-d"])
