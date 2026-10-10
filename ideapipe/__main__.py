"""CLI:  python -m ideapipe {check|setup|run|watch|process FILE}"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import settings


def main() -> int:
    ap = argparse.ArgumentParser(prog="ideapipe", description="Voice notes -> ideas -> Notion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="verify keys, folder and Notion access")
    sub.add_parser("setup", help="create the Voice Notes + Idea Inbox databases in Notion")
    r = sub.add_parser("run", help="process every new file in the inbox once")
    r.add_argument("--dry-run", action="store_true", help="print ideas, don't write to Notion")
    sub.add_parser("watch", help="keep running and pick up new files as they sync")
    p = sub.add_parser("process", help="process one file")
    p.add_argument("file", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="redo extraction even if already processed")
    a = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")

    if a.cmd == "check":
        return _check()
    if a.cmd == "setup":
        from .notion_sink import setup
        ids = setup()
        print("Notion is ready.\n  Idea Inbox:  ", ids.get("ideas_url"), "\n  Voice Notes: ", ids.get("notes_url"))
        return 0

    from . import pipeline
    if a.cmd == "run":
        ok, failed = pipeline.run_once(dry_run=a.dry_run or settings.dry_run)
        print(f"Processed {ok}, failed {failed}.")
        return 1 if failed else 0
    if a.cmd == "watch":
        pipeline.watch()
        return 0
    if a.cmd == "process":
        if not a.file.exists():
            print(f"No such file: {a.file}"); return 1
        pipeline.process(a.file, dry_run=a.dry_run or settings.dry_run, force=a.force)
        return 0
    return 1


def _check() -> int:
    problems = 0
    def line(ok: bool, msg: str):
        nonlocal problems
        problems += 0 if ok else 1
        print(("  ok   " if ok else "  FIX  ") + msg)

    print("Idea pipeline check")
    line(settings.inbox_dir.exists(), f"Inbox folder: {settings.inbox_dir}")
    line(bool(settings.anthropic_api_key), "ANTHROPIC_API_KEY set")
    if settings.backend == "local":
        try:
            import faster_whisper  # noqa: F401
            line(True, f"Local Whisper installed (model '{settings.whisper_model}', downloads on first use)")
        except ImportError:
            line(False, "faster-whisper not installed: pip install faster-whisper")
    else:
        key = settings.groq_api_key if settings.backend == "groq" else settings.openai_api_key
        line(bool(key), f"{settings.backend} API key set")
    line(bool(settings.vocab), f"vocab.txt has names ({settings.vocab[:60]}…)" if settings.vocab else "vocab.txt is empty; add brand names for better accuracy")
    try:
        from .notion_sink import check
        line(True, f"Notion token works ({check()})")
        ids = settings.notion_ids()
        line(bool(ids.get("ideas_db")), "Notion databases created" if ids.get("ideas_db") else "Notion databases missing: run  python -m ideapipe setup")
    except Exception as e:
        line(False, f"Notion: {e}")
    print("\nAll good." if not problems else f"\n{problems} thing(s) to fix.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
