"""Transcript -> structured ideas, using the same rules as the Idea Catcher app."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict

from .config import settings


@dataclass
class Idea:
    idea: str
    quote: str
    score: int
    category: str
    next_step: str


@dataclass
class Extraction:
    title: str
    ideas: list[Idea]

    def to_dict(self) -> dict:
        return {"title": self.title, "ideas": [asdict(i) for i in self.ideas]}


def build_prompt(transcript: str, categories: list[str]) -> str:
    cat_rule = f" Reuse one of these existing categories when it fits: {', '.join(categories[:25])}." if categories else ""
    return f"""You help someone who records rambling voice notes while walking. Below is a raw speech-to-text transcript. Expect filler, restarts, mis-heard words (especially brand names and acronyms) and Hinglish.

Rules:
1. Extract every distinct idea worth keeping: business, product, marketing, content, tooling, personal. Merge repeats within the note. Skip filler, logistics chatter and throwaway remarks.
2. If the speaker says things like "new idea", "next", "another thing" or "note to self", treat that as a boundary between ideas.
3. Rewrite each idea as ONE clear, specific sentence in the speaker's voice. Fix obvious transcription errors from context. Never add facts, numbers or claims they did not say.
4. "quote": the shortest verbatim fragment (max 12 words) from the transcript that the idea came from.
5. "score" 1-5: 5 = specific and worth acting on this week; 3 = promising but needs thought; 1 = vague passing thought. Be strict; most notes have at most one or two 5s.
6. "category": 1-2 words.{cat_rule}
7. "next_step": one concrete, small action for ideas scoring 3+; empty string otherwise.
8. "title": 3-6 words for the whole note.

Return ONLY JSON, strongest idea first, no prose and no code fences:
{{"title":"...","ideas":[{{"idea":"...","quote":"...","score":4,"category":"...","next_step":"..."}}]}}
If there are no real ideas, return an empty ideas array.

Transcript:
\"\"\"{transcript}\"\"\""""


def parse(text: str) -> Extraction:
    """Tolerates code fences or stray prose around the JSON."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in model output")
    data = json.loads(cleaned[start:end + 1])
    ideas = []
    for raw in data.get("ideas") or []:
        if not isinstance(raw, dict) or not str(raw.get("idea", "")).strip():
            continue
        try:
            score = int(round(float(raw.get("score", 1))))
        except (TypeError, ValueError):
            score = 1
        ideas.append(Idea(
            idea=str(raw["idea"]).strip()[:500],
            quote=str(raw.get("quote", "")).strip()[:160],
            score=max(1, min(5, score)),
            category=str(raw.get("category", "")).strip()[:40] or "Uncategorised",
            next_step=str(raw.get("next_step", "")).strip()[:300],
        ))
    ideas.sort(key=lambda i: -i.score)
    return Extraction(title=str(data.get("title") or "Voice note").strip()[:100], ideas=ideas)


def extract(transcript: str, categories: list[str] | None = None) -> Extraction:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing in .env")
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.claude_model,
        max_tokens=4000,
        messages=[{"role": "user", "content": build_prompt(transcript, categories or [])}],
    )
    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    try:
        return parse(text)
    except (ValueError, json.JSONDecodeError):
        # one repair attempt: ask for the JSON again rather than failing the note
        fix = client.messages.create(
            model=settings.claude_model, max_tokens=4000,
            messages=[
                {"role": "user", "content": build_prompt(transcript, categories or [])},
                {"role": "assistant", "content": text},
                {"role": "user", "content": "That was not valid JSON. Return only the JSON object, nothing else."},
            ],
        )
        return parse("".join(b.text for b in fix.content if getattr(b, "type", "") == "text"))
