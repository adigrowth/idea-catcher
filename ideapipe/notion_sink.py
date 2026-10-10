"""Writes notes and ideas into two linked Notion databases.

Voice Notes  - one page per recording, full transcript in the page body
Idea Inbox   - one page per idea, linked back to its voice note
"""
from __future__ import annotations

import datetime as dt
import time

import requests

from .config import settings
from .extract import Extraction

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"
STATUS_OPTIONS = [("Inbox", "yellow"), ("Doing", "blue"), ("Done", "green"), ("Dropped", "gray")]


class NotionError(RuntimeError):
    pass


def _h() -> dict:
    if not settings.notion_token:
        raise NotionError("NOTION_TOKEN missing in .env")
    return {"Authorization": f"Bearer {settings.notion_token}", "Notion-Version": VERSION, "Content-Type": "application/json"}


def _req(method: str, path: str, body: dict | None = None) -> dict:
    for attempt in range(4):
        r = requests.request(method, API + path, headers=_h(), json=body, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:   # rate limit / transient
            time.sleep(float(r.headers.get("Retry-After", 2 ** attempt)))
            continue
        if r.status_code >= 400:
            msg = r.json().get("message", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
            if r.status_code == 404:
                msg += "  (Is the page/database shared with your integration? In Notion: ••• > Connections > add it.)"
            raise NotionError(f"Notion {r.status_code}: {msg}")
        return r.json()
    raise NotionError("Notion kept rate-limiting; try again later.")


def _rt(text: str) -> list[dict]:
    """Notion caps a text object at 2000 chars."""
    text = text or ""
    return [{"type": "text", "text": {"content": text[i:i + 2000]}} for i in range(0, len(text), 2000)] or []


def _paragraphs(text: str) -> list[dict]:
    chunks, buf = [], ""
    for sentence in text.replace("\n", " ").split(". "):
        piece = (sentence + ". ") if not sentence.endswith(".") else sentence + " "
        if len(buf) + len(piece) > 1800:
            chunks.append(buf.strip()); buf = ""
        buf += piece
    if buf.strip():
        chunks.append(buf.strip())
    return [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rt(c)}} for c in chunks]


# ---------- setup ----------
def setup() -> dict:
    pid = settings.notion_parent_page_id
    if not pid:
        raise NotionError("Set NOTION_PARENT_PAGE_ID in .env to the page that should hold the databases.")
    existing = settings.notion_ids()
    if existing.get("notes_db") and existing.get("ideas_db"):
        return existing

    notes = _req("POST", "/databases", {
        "parent": {"type": "page_id", "page_id": pid},
        "title": _rt("Voice Notes"),
        "icon": {"type": "emoji", "emoji": "🎙️"},
        "properties": {
            "Title": {"title": {}},
            "Recorded": {"date": {}},
            "Ideas": {"number": {}},
            "Source file": {"rich_text": {}},
        },
    })
    ideas = _req("POST", "/databases", {
        "parent": {"type": "page_id", "page_id": pid},
        "title": _rt("Idea Inbox"),
        "icon": {"type": "emoji", "emoji": "💡"},
        "properties": {
            "Idea": {"title": {}},
            "Score": {"number": {}},
            "Category": {"select": {"options": []}},
            "Status": {"select": {"options": [{"name": n, "color": c} for n, c in STATUS_OPTIONS]}},
            "Next step": {"rich_text": {}},
            "Quote": {"rich_text": {}},
            "Captured": {"date": {}},
            "Voice note": {"relation": {"database_id": notes["id"], "single_property": {}}},
        },
    })
    ids = {"notes_db": notes["id"], "ideas_db": ideas["id"],
           "notes_url": notes.get("url"), "ideas_url": ideas.get("url")}
    settings.save_notion_ids(ids)
    return ids


def _ids() -> dict:
    ids = settings.notion_ids()
    if not ids.get("ideas_db"):
        raise NotionError("Notion databases not set up. Run: python -m ideapipe setup")
    return ids


def existing_categories() -> list[str]:
    """Feeds Claude the category names already in use so the taxonomy stays stable."""
    db = _req("GET", f"/databases/{_ids()['ideas_db']}")
    return [o["name"] for o in db["properties"]["Category"]["select"].get("options", [])]


# ---------- write ----------
def write(ex: Extraction, transcript: str, recorded: dt.datetime, source: str) -> str:
    ids = _ids()
    note = _req("POST", "/pages", {
        "parent": {"database_id": ids["notes_db"]},
        "properties": {
            "Title": {"title": _rt(ex.title)},
            "Recorded": {"date": {"start": recorded.isoformat()}},
            "Ideas": {"number": len(ex.ideas)},
            "Source file": {"rich_text": _rt(source)},
        },
        "children": _paragraphs(transcript)[:100],
    })
    for i in ex.ideas:
        props = {
            "Idea": {"title": _rt(i.idea)},
            "Score": {"number": i.score},
            "Status": {"select": {"name": "Inbox"}},
            "Next step": {"rich_text": _rt(i.next_step)},
            "Quote": {"rich_text": _rt(i.quote)},
            "Captured": {"date": {"start": recorded.isoformat()}},
            "Voice note": {"relation": [{"id": note["id"]}]},
        }
        if i.category:
            props["Category"] = {"select": {"name": i.category.replace(",", " ")}}  # commas are invalid in select names
        _req("POST", "/pages", {"parent": {"database_id": ids["ideas_db"]}, "properties": props})
    return note["id"]


def check() -> str:
    me = _req("GET", "/users/me")
    return me.get("name") or me.get("bot", {}).get("owner", {}).get("type", "integration")
