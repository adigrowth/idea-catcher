# Idea Catcher

**Talk while you walk. Find your ideas waiting in Notion.**

Record a voice note on your phone. A few minutes later, your ideas are in Notion, each one scored, categorised, given a next step and linked to the full transcript.

### Why I built this
My best ideas show up on walks, and most of them used to disappear. Typing on a phone breaks the flow, and raw voice memos pile up unheard. This pipeline turns a rambling, half-Hinglish recording into a short list of specific, scored ideas I can act on.

It started as a browser app. Real use exposed its limits (blocked mic access, flaky sync, duplicate transcripts), so I rebuilt it as this local Python pipeline, designed to fail safely and run on an ordinary CPU-only laptop.

**What it shows:** speech-to-text with Whisper, structured extraction with an LLM, a Notion integration, and reliability patterns (idempotency, per-stage caching, retries) applied to a real personal workflow.

**Status:** v0.1. All 10 offline tests pass (Whisper, Claude and Notion are mocked). A live end-to-end run with real keys is next, and I'll note fixes here as I find them.

```
Phone recorder ──► Google Drive "Idea Inbox" folder ──► your laptop (Drive for desktop mirrors it)
                                                            │
                                   Whisper (local or Groq)  ▼  transcript, with names from vocab.txt as hints
                                   Claude                   ▼  ideas: score, category, quote, next step
                                   Notion                   ▼  💡 Idea Inbox  ⇄  🎙️ Voice Notes
```

It runs on your laptop, so there's no server to host. The trade-off is that notes are processed only while the laptop is on. Anything recorded while it's off gets picked up the next time it runs.

## Setup (about 20 minutes)

### 1. Install
```bash
git clone https://github.com/adigrowth/idea-catcher.git
cd idea-catcher
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
cp vocab.example.txt vocab.txt                          # then add your own names
```
Or open the folder in **Claude Code** and say: *"Set this project up and walk me through the .env."* The `CLAUDE.md` file gives it the context it needs.

### 2. The inbox folder
1. Install **Google Drive for desktop** if you don't have it.
2. Create a folder called `Idea Inbox` in My Drive.
3. Put its local path in `INBOX_DIR`. On a Mac it looks like `~/Library/CloudStorage/GoogleDrive-<you>/My Drive/Idea Inbox`.

### 3. Keys
| Key | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API keys |
| `NOTION_TOKEN` | notion.so/profile/integrations → New integration (internal) → copy the secret |
| `NOTION_PARENT_PAGE_ID` | Create a page, e.g. "Ideas", and copy the 32-character id at the end of its URL. **Then open the page, go to ••• → Connections, and add your integration.** Most setup failures come from skipping this step. |
| `GROQ_API_KEY` (optional) | console.groq.com. Needed only if `TRANSCRIBE_BACKEND=groq`. |

### 4. Create the Notion databases and verify
```bash
python -m ideapipe setup     # creates 💡 Idea Inbox and 🎙️ Voice Notes, linked to each other
python -m ideapipe check     # every line should say ok
```

### 5. Test before you trust it
```bash
echo "New idea: start a weekly newsletter of my reading notes. Another thing, record a short podcast episode about it." > "$INBOX_DIR/test.txt"
python -m ideapipe run --dry-run      # prints the ideas, writes nothing
python -m ideapipe run                # writes to Notion
```
Then record a real voice note and run `python -m ideapipe process path/to/note.m4a --dry-run`.

### 6. Keep it running
- **Mac:** edit the paths in `scheduling/com.ideapipe.watch.plist`, then load it. It starts at login and restarts itself if it crashes.
- **Windows:** run `scheduling/run-every-10-min-windows.bat` from Task Scheduler.
- **Manual:** run `python -m ideapipe watch` in a terminal.

## Phone side: make capture one tap

**Android:** record in any voice recorder app, then Share → Drive → `Idea Inbox`. For zero taps after recording, set up FolderSync (or a similar app) to auto-upload your recorder's folder to `Idea Inbox`.

**iPhone:** build a Shortcut with two actions: **Record Audio** → **Save File** (destination: Google Drive › Idea Inbox, "Ask where to save" turned off). Put it on your Home Screen, the Action button or Back Tap. That gives you tap, talk, tap, done.

Text works too. Any `.txt` file dropped in the folder, such as keyboard dictation saved from Notes, goes through the same idea extraction.

## Choosing the transcription backend
| | `local` (default) | `groq` |
|---|---|---|
| Privacy | Audio never leaves your laptop | Audio is sent to Groq |
| Cost | Free | Pay per use |
| Speed on a laptop CPU | Roughly as long as the recording itself with `medium`; slower with `large-v3` | A few seconds |
| Hinglish and accents | Good with `medium`, better with `large-v3` | Uses large-v3 |
| First run | Downloads the model (about 1.5 GB for `medium`) | Nothing to download |

Start with `local` + `medium`. If you often mix in a lot of Hindi, try `large-v3` or `groq` and compare the same recording with `process --force --dry-run`.

`vocab.txt` is the biggest accuracy lever. Add every name Whisper gets wrong. It is git-ignored, so names you add stay on your machine.

## Reliability
- **Never processed twice:** every file is tracked by a fingerprint of its content in `.state/ledger.json`.
- **A failure never repeats paid steps:** transcripts and extracted ideas are cached, so a Notion outage only retries the Notion write.
- **No half-synced files:** a file is ignored until it has been unchanged for `SETTLE_SECONDS`, so it isn't read while Drive is still copying it.
- **Accidental recordings are skipped:** anything under 3 words (a silent or pocket recording) is skipped and logged.

## Commands
```
python -m ideapipe check                  verify setup
python -m ideapipe setup                  create the Notion databases
python -m ideapipe run [--dry-run]        process new files once
python -m ideapipe watch                  keep processing as files arrive
python -m ideapipe process FILE [--dry-run] [--force]
python -m pytest -q                       offline tests, no keys needed
```

## Privacy
- Keys live only in `.env`, which is git-ignored.
- With the default `local` backend, audio never leaves your laptop. Only the transcript text goes to Claude for extraction.
- Your transcripts and ideas go to your own Notion workspace, nowhere else.

## License
MIT
