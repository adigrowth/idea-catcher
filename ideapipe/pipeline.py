"""Finds new recordings, runs each through transcribe -> extract -> Notion, never twice.

Each stage is cached by file hash, so a failure at stage 3 never repeats
the slow or paid stages 1-2 on the next run.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import shutil
import time
from pathlib import Path

from . import extract as ext
from . import notion_sink
from .config import AUDIO_EXTS, STATE_DIR, TEXT_EXTS, settings
from .transcribe import transcribe

log = logging.getLogger("ideapipe")
LEDGER = STATE_DIR / "ledger.json"
CACHE = STATE_DIR / "cache"


def _ledger() -> dict:
    return json.loads(LEDGER.read_text()) if LEDGER.exists() else {}


def _save_ledger(d: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2))
    tmp.replace(LEDGER)  # atomic: a crash can't corrupt the ledger


def _hash(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:20]


def _cached(key: str, kind: str) -> str | None:
    p = CACHE / f"{key}.{kind}"
    return p.read_text(encoding="utf-8") if p.exists() else None


def _cache(key: str, kind: str, text: str) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{key}.{kind}").write_text(text, encoding="utf-8")


def candidates() -> list[Path]:
    """Files that are finished syncing: untouched for SETTLE_SECONDS."""
    if not settings.inbox_dir.exists():
        raise FileNotFoundError(f"Inbox folder not found: {settings.inbox_dir}")
    now = time.time()
    out = []
    for p in sorted(settings.inbox_dir.iterdir(), key=lambda x: x.stat().st_mtime):
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in AUDIO_EXTS | TEXT_EXTS:
            if now - p.stat().st_mtime >= settings.settle_seconds:
                out.append(p)
    return out


def process(path: Path, dry_run: bool = False, force: bool = False) -> dict:
    key = _hash(path)
    ledger = _ledger()
    if not force and ledger.get(key, {}).get("status") == "done":
        return ledger[key]

    recorded = dt.datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    entry = {"file": path.name, "status": "started", "at": dt.datetime.now().isoformat(timespec="seconds")}

    # 1. transcribe (cached)
    transcript = _cached(key, "txt")
    if transcript is None:
        log.info("Transcribing %s (%s backend)…", path.name, settings.backend)
        t0 = time.time()
        transcript = transcribe(path)
        log.info("  %d words in %.0fs", len(transcript.split()), time.time() - t0)
        _cache(key, "txt", transcript)
    if len(transcript.split()) < 3:
        entry.update(status="skipped", reason="too short or silent")
        if not dry_run:
            ledger[key] = entry; _save_ledger(ledger)
        log.info("  skipped: nothing said")
        return entry

    # 2. extract (cached)
    raw = _cached(key, "json")
    if raw is None or force:
        cats = [] if dry_run else _safe_categories()
        log.info("Extracting ideas…")
        result = ext.extract(transcript, cats)
        _cache(key, "json", json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        result = ext.parse(raw)
    log.info("  %d ideas: %s", len(result.ideas), result.title)

    if dry_run:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return {**entry, "status": "dry-run"}

    # 3. Notion
    note_id = notion_sink.write(result, transcript, recorded, path.name)
    entry.update(status="done", title=result.title, ideas=len(result.ideas), notion_note=note_id)
    ledger[key] = entry
    _save_ledger(ledger)

    if settings.archive_dir:
        settings.archive_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), settings.archive_dir / path.name)
    return entry


def _safe_categories() -> list[str]:
    try:
        return notion_sink.existing_categories()
    except Exception as e:  # categories are a nicety; never block a note on them
        log.warning("Couldn't read categories from Notion: %s", e)
        return []


def run_once(dry_run: bool = False) -> tuple[int, int]:
    ok = failed = 0
    ledger = _ledger()
    for p in candidates():
        try:
            if ledger.get(_hash(p), {}).get("status") in {"done", "skipped"}:
                continue
            process(p, dry_run=dry_run)
            ok += 1
        except Exception as e:
            failed += 1
            log.error("Failed on %s: %s", p.name, e)
    return ok, failed


def watch() -> None:
    log.info("Watching %s every %ss. Ctrl+C to stop.", settings.inbox_dir, settings.poll_seconds)
    while True:
        try:
            ok, failed = run_once()
            if ok or failed:
                log.info("Processed %d, failed %d", ok, failed)
        except Exception as e:
            log.error("%s", e)
        time.sleep(settings.poll_seconds)
