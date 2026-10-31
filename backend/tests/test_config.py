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


def test_default_models():
    # extraction default chosen by the 2026-10-31 benchmark (README "Changing models")
    defaults = Settings(_env_file=None)
    assert defaults.extraction_model == "gemma4:12b"
    assert defaults.chat_model == "qwen3:8b"
