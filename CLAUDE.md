# Context for Claude Code

Personal pipeline: phone voice notes → Whisper → Claude idea extraction → Notion. Recordings are often Hinglish and full of names, which is why `vocab.txt` matters.

## Layout
- `ideapipe/config.py`: every setting comes from `.env`. Notion database ids are kept in `.state/notion.json`.
- `ideapipe/transcribe.py`: `local` (faster-whisper) | `groq` | `openai` backends. `vocab.txt` is passed as the Whisper prompt.
- `ideapipe/extract.py`: the extraction prompt and a tolerant JSON parser.
- `ideapipe/notion_sink.py`: raw REST calls to Notion API version 2022-06-28. `setup()` creates two linked databases.
- `ideapipe/pipeline.py`: finds files, runs the stages with caching per stage, and records a ledger.
- `tests/`: offline tests with mocked services. They must pass before any change is done: `python -m pytest -q`.

## Rules
- Never commit `.env`, `.state/` or `vocab.txt`. Never print API keys.
- Recordings can contain private details. Don't add any backend that sends audio or text to a new third party without asking.
- Keep a failure in one stage from re-running earlier paid stages. Preserve the caching.
- Notion limits: 2000 characters per text object and 100 blocks per request. Use `_rt()` and `_paragraphs()`.

## Backlog (ask before building)
1. Weekly digest: the top unacted ideas (Status = Inbox, Score ≥ 4, older than 7 days), posted as a Notion page or email.
2. Theme clustering across all ideas.
3. Auto-route ideas to project pages through a `Project` select.
4. Speaker cue: saying "urgent" sets Score to 5 and flags the idea.
