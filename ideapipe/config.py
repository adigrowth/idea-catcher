"""All settings come from .env so nothing secret lives in code."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".state"
load_dotenv(ROOT / ".env")

AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".ogg", ".opus", ".aac", ".webm", ".flac", ".mp4", ".amr", ".3gp"}
TEXT_EXTS = {".txt"}


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    inbox_dir: Path = field(default_factory=lambda: Path(os.path.expanduser(os.getenv("INBOX_DIR", "~/IdeaInbox"))))
    archive_dir: Path | None = field(default_factory=lambda: Path(os.path.expanduser(os.environ["ARCHIVE_DIR"])) if os.getenv("ARCHIVE_DIR") else None)
    settle_seconds: int = int(os.getenv("SETTLE_SECONDS", "20"))
    poll_seconds: int = int(os.getenv("POLL_SECONDS", "60"))

    # transcription
    backend: str = os.getenv("TRANSCRIBE_BACKEND", "local").lower()      # local | groq | openai
    whisper_model: str = os.getenv("WHISPER_MODEL", "medium")
    whisper_language: str | None = os.getenv("WHISPER_LANGUAGE", "en") or None  # blank = auto-detect
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")

    # extraction
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

    # notion
    notion_token: str | None = os.getenv("NOTION_TOKEN")
    notion_parent_page_id: str | None = os.getenv("NOTION_PARENT_PAGE_ID")

    dry_run: bool = _bool(os.getenv("DRY_RUN"))

    @property
    def vocab(self) -> str:
        """Names Whisper keeps mishearing. One per line in vocab.txt."""
        p = ROOT / "vocab.txt"
        if not p.exists():
            return ""
        words = [w.strip() for w in p.read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")]
        return ", ".join(words)

    # Notion database ids are written by `setup` and read back here
    def notion_ids(self) -> dict:
        p = STATE_DIR / "notion.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def save_notion_ids(self, ids: dict) -> None:
        STATE_DIR.mkdir(exist_ok=True)
        (STATE_DIR / "notion.json").write_text(json.dumps(ids, indent=2))


settings = Settings()
