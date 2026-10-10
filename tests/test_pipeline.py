"""Offline tests: no API keys or network needed.  Run:  python -m pytest -q"""
import json
import os
import time
from pathlib import Path

import pytest

from ideapipe import extract as ext
from ideapipe import notion_sink, pipeline
from ideapipe.config import settings


# ---------- parsing ----------
def test_parse_handles_fences_and_prose():
    raw = 'Sure!\n```json\n{"title":"Walk thoughts","ideas":[{"idea":"A","quote":"a","score":"4.6","category":"Content","next_step":"x"},{"idea":"","score":5}]}\n```'
    r = ext.parse(raw)
    assert r.title == "Walk thoughts"
    assert len(r.ideas) == 1 and r.ideas[0].score == 5


def test_parse_clamps_and_sorts():
    raw = json.dumps({"title": "t", "ideas": [
        {"idea": "weak", "score": -3}, {"idea": "strong", "score": 99, "category": ""}]})
    r = ext.parse(raw)
    assert [i.idea for i in r.ideas] == ["strong", "weak"]
    assert r.ideas[0].score == 5 and r.ideas[1].score == 1
    assert r.ideas[0].category == "Uncategorised"


def test_parse_rejects_non_json():
    with pytest.raises(ValueError):
        ext.parse("I couldn't find any ideas.")


def test_prompt_reuses_categories():
    p = ext.build_prompt("hello there friend", ["Content", "Product"])
    assert "Content, Product" in p and "hello there friend" in p


# ---------- notion payloads ----------
def test_long_text_is_chunked_under_notion_limits():
    parts = notion_sink._rt("x" * 4500)
    assert [len(p["text"]["content"]) for p in parts] == [2000, 2000, 500]
    blocks = notion_sink._paragraphs(("This is a sentence. " * 400))
    assert all(len(b["paragraph"]["rich_text"][0]["text"]["content"]) <= 2000 for b in blocks)


# ---------- pipeline end to end (mocked services) ----------
@pytest.fixture
def env(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"; inbox.mkdir()
    monkeypatch.setattr(settings, "inbox_dir", inbox)
    monkeypatch.setattr(settings, "archive_dir", None)
    monkeypatch.setattr(settings, "settle_seconds", 0)
    monkeypatch.setattr(pipeline, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(pipeline, "LEDGER", tmp_path / "state" / "ledger.json")
    monkeypatch.setattr(pipeline, "CACHE", tmp_path / "state" / "cache")

    calls = {"extract": 0, "notion": 0, "fail_notion": False}

    def fake_extract(transcript, cats):
        calls["extract"] += 1
        return ext.parse(json.dumps({"title": "Content ideas", "ideas": [
            {"idea": "Start a weekly newsletter of reading notes.", "quote": "weekly newsletter", "score": 4, "category": "Content", "next_step": "Draft issue 1"}]}))

    def fake_write(result, transcript, recorded, source):
        calls["notion"] += 1
        if calls["fail_notion"]:
            raise notion_sink.NotionError("Notion 503")
        return "page-123"

    monkeypatch.setattr(ext, "extract", fake_extract)
    monkeypatch.setattr(notion_sink, "write", fake_write)
    monkeypatch.setattr(notion_sink, "existing_categories", lambda: ["Content"])
    return inbox, calls


def test_processes_once_and_never_twice(env):
    inbox, calls = env
    (inbox / "walk.txt").write_text("new idea start a weekly newsletter of reading notes")
    assert pipeline.run_once() == (1, 0)
    assert pipeline.run_once() == (0, 0)          # already done: skipped
    assert calls == {"extract": 1, "notion": 1, "fail_notion": False}


def test_notion_failure_does_not_repeat_extraction(env):
    inbox, calls = env
    (inbox / "walk.txt").write_text("another thing record a short podcast episode")
    calls["fail_notion"] = True
    assert pipeline.run_once() == (0, 1)
    calls["fail_notion"] = False
    assert pipeline.run_once() == (1, 0)
    assert calls["extract"] == 1                   # cached; the paid step ran once
    assert calls["notion"] == 2


def test_silent_recording_is_skipped(env):
    inbox, calls = env
    (inbox / "pocket.txt").write_text("um")
    pipeline.run_once()
    assert calls["extract"] == 0 and calls["notion"] == 0
    assert pipeline.run_once() == (0, 0)


def test_waits_for_sync_to_finish(env, monkeypatch):
    inbox, calls = env
    monkeypatch.setattr(settings, "settle_seconds", 60)
    (inbox / "fresh.txt").write_text("a brand new idea about a reading tracker")
    assert pipeline.candidates() == []             # still "syncing"
    old = time.time() - 120
    os.utime(inbox / "fresh.txt", (old, old))
    assert len(pipeline.candidates()) == 1


def test_ignores_unrelated_files(env):
    inbox, _ = env
    (inbox / "photo.jpg").write_bytes(b"x"); (inbox / ".DS_Store").write_bytes(b"x")
    assert pipeline.candidates() == []
