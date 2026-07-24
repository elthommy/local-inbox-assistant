from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


def _detect_thunderbird_profile() -> Path:
    """Return the newest Thunderbird profile directory, e.g. ~/.thunderbird/xxxxxxxx.default-release."""
    root = Path("~/.thunderbird").expanduser()
    profiles = sorted(
        (
            p
            for pattern in ("*.default-release", "*.default")
            for p in root.glob(pattern)
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return profiles[0] if profiles else root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_prefix="INBOX_", extra="ignore"
    )

    # Root scanned recursively for .eml files; every mailbox folder under it
    # is indexed. Pointing it at a single folder's cur/ dir still works.
    maildir: Path = Field(default_factory=_detect_thunderbird_profile)
    # Folder names skipped during the scan (comma-separated, case-insensitive).
    # "All Mail" is the Gmail label archive: pure duplicates of other folders.
    exclude_folders: str = "Trash,Junk,Spam,Drafts,Unsent Messages,All Mail"
    window_days: int = 90
    extraction_window_days: int = 14
    extraction_max_emails: int = 300

    ollama_url: str = "http://localhost:11434"
    chat_model: str = "qwen3:8b"
    # Extraction can run a different (typically lighter) model than chat;
    # picked from scripts/benchmark_extraction.py results.
    extraction_model: str = "qwen3:8b"
    embed_model: str = "nomic-embed-text"

    # Claude cloud chat (opt-in): with a key set, "Claude" becomes selectable
    # in the chat dropdown. Extraction and embeddings always stay local.
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5"
    # Which backend answers chat: "ollama" (local) or "claude" (cloud).
    chat_provider: str = "ollama"

    db_path: Path = DATA_DIR / "inbox.db"
    chroma_path: Path = DATA_DIR / "chroma"

    chunk_size: int = 1200
    chunk_overlap: int = 150
    rag_top_k: int = 6


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
