import pytest
from mze.main import parse_template

def test_parse_template_automatic():
    assert parse_template("echo {}") == 1
    assert parse_template("echo {} {}") == 2
    assert parse_template("echo {} {} {}") == 3
    assert parse_template("no placeholders") == 0

def test_parse_template_explicit():
    assert parse_template("echo {0}") == 1
    assert parse_template("echo {1} {0}") == 2
    assert parse_template("echo {2} {0}") == 3

def test_parse_template_mix_fail():
    with pytest.raises(ValueError, match="Cannot mix automatic and explicit"):
        parse_template("echo {} {0}")

def test_parse_template_invalid_name():
    with pytest.raises(ValueError, match="Invalid field name"):
        parse_template("echo {name}")

def test_parse_template_syntax_error():
    with pytest.raises(ValueError, match="Invalid template syntax"):
        parse_template("{ { }")
