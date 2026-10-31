import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ask", "ask"),
        ("ALWAYS", "always"),
        ("never", "never"),
        ("true", "always"),  # earlier boolean form
        ("false", "never"),
    ],
)
def test_auto_pull_values(raw, expected):
    assert Settings(_env_file=None, auto_pull=raw).auto_pull == expected


def test_auto_pull_defaults_to_ask():
    assert Settings(_env_file=None).auto_pull == "ask"


def test_auto_pull_rejects_unknown_value():
    with pytest.raises(ValueError):
        Settings(_env_file=None, auto_pull="sometimes")
