"""Speech-to-text. Three interchangeable backends:

local  - faster-whisper on your laptop. Free, private, slower. Default.
groq   - Groq-hosted whisper-large-v3. Fast and strong on accents; audio leaves your machine.
openai - OpenAI whisper-1. Same trade-off as groq.

The vocab prompt (vocab.txt) is the single biggest accuracy lever for brand names.
"""
from __future__ import annotations

from pathlib import Path

import requests

from .config import settings

API_LIMIT_BYTES = 25 * 1024 * 1024  # hosted APIs reject files above ~25 MB

_local_model = None


def _prompt() -> str:
    vocab = settings.vocab
    base = "Voice note from an Indian marketing professional, mixing English and some Hindi."
    return f"{base} Names that may appear: {vocab}." if vocab else base


def _local(path: Path) -> str:
    global _local_model
    from faster_whisper import WhisperModel  # imported lazily: heavy

    if _local_model is None:
        _local_model = WhisperModel(settings.whisper_model, device="auto", compute_type="int8")
    segments, _info = _local_model.transcribe(
        str(path),
        language=settings.whisper_language,
        initial_prompt=_prompt(),
        vad_filter=True,               # drops long silences and street noise between thoughts
        beam_size=5,
    )
    return " ".join(s.text.strip() for s in segments).strip()


def _hosted(path: Path, url: str, key: str | None, model: str) -> str:
    if not key:
        raise RuntimeError(f"{settings.backend.upper()} API key missing in .env")
    if path.stat().st_size > API_LIMIT_BYTES:
        raise RuntimeError(f"{path.name} is over 25 MB. Record at a lower quality or use TRANSCRIBE_BACKEND=local.")
    data = {"model": model, "prompt": _prompt(), "response_format": "text"}
    if settings.whisper_language:
        data["language"] = settings.whisper_language
    with path.open("rb") as f:
        r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, data=data,
                          files={"file": (path.name, f)}, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"Transcription failed ({r.status_code}): {r.text[:300]}")
    return r.text.strip()


def transcribe(path: Path) -> str:
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8").strip()
    if settings.backend == "local":
        return _local(path)
    if settings.backend == "groq":
        return _hosted(path, "https://api.groq.com/openai/v1/audio/transcriptions", settings.groq_api_key, "whisper-large-v3")
    if settings.backend == "openai":
        return _hosted(path, "https://api.openai.com/v1/audio/transcriptions", settings.openai_api_key, "whisper-1")
    raise RuntimeError(f"Unknown TRANSCRIBE_BACKEND '{settings.backend}'. Use local, groq or openai.")
