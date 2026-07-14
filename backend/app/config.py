from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_prefix="INBOX_", extra="ignore"
    )

    # Root scanned recursively for .eml files; every mailbox folder under it
    # is indexed. Pointing it at a single folder's cur/ dir still works.
    maildir: Path = Path("~/.thunderbird/xxxxxxxx.default-release").expanduser()
    # Folder names skipped during the scan (comma-separated, case-insensitive).
    # "All Mail" is the Gmail label archive: pure duplicates of other folders.
    exclude_folders: str = "Trash,Junk,Spam,Drafts,Unsent Messages,All Mail"
    window_days: int = 90
    extraction_window_days: int = 14
    extraction_max_emails: int = 300

    ollama_url: str = "http://localhost:11434"
    chat_model: str = "qwen3.6"
    embed_model: str = "nomic-embed-text"

    # Claude cloud support is a later step; key is read but unused for now.
    anthropic_api_key: str = ""

    db_path: Path = DATA_DIR / "inbox.db"
    chroma_path: Path = DATA_DIR / "chroma"

    chunk_size: int = 1200
    chunk_overlap: int = 150
    rag_top_k: int = 6


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
