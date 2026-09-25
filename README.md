# claude-tab-tracking

[中文文档](README_CN.md)

> Know what every Claude Code session is doing — at a glance.

![demo](assets/demo.svg)

Live task tracking for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Shows what each session is working on — updated automatically as the conversation progresses.

If you run multiple Claude Code sessions simultaneously, this tells you at a glance what each one is doing.

## What it looks like

```
[WIP]  Fix authentication bug in api/routes.py
[DONE] Deploy model to production server
[DONE] Refactor database schema
       my-project  |  ctx 14%  |  23min
```

**Status badges:**
- `[---]` — session just started, showing directory and git branch
- `[WIP]` — task in progress, auto-updated each turn
- `[DONE]` — task completed (detected automatically)
- `[SET]` — task manually set with `/task`

When you finish one task and start another, the previous tasks stay visible as dimmed `[DONE]` lines beneath the current task (up to 2 previous tasks displayed, 3 stored).

## How it works

Four Claude Code hooks work together:

| Hook | What it does |
|------|-------------|
| `SessionStart` | Writes `dir [branch]` as initial task label |
| `Stop` | After each assistant response: reads transcript, updates task description, detects completion |
| `TaskCompleted` | Marks task as `[DONE]` when Claude explicitly completes a task |
| `SessionEnd` | Cleans up session state files |

The statusline script reads the task file for the current session and renders the display.

### Summarization backends

The plugin picks the best available backend automatically:

| Priority | Backend | Quality | Speed | Cost |
|----------|---------|---------|-------|------|
| 1 | Claude API (`ANTHROPIC_API_KEY` set) | Best | ~2s | ~$1/month |
| 2 | Ollama (local model running) | Good | ~2s | Free |
| 3 | Claude Code CLI (Max subscription) | Best | ~10s (async) | Included in subscription |
| 4 | Keyword heuristics | Basic | instant | Free |

No setup needed — it works out of the box with any of the above.

#### Choosing a backend

Set the `CLAUDE_TAB_BACKEND` environment variable to pick a specific backend:

```bash
# Use only Claude Code CLI (Max subscription, no API key needed)
export CLAUDE_TAB_BACKEND=cli

# Use only the Anthropic API
export CLAUDE_TAB_BACKEND=api

# Use only local Ollama
export CLAUDE_TAB_BACKEND=ollama

# Use only keyword heuristics (zero network calls)
export CLAUDE_TAB_BACKEND=keyword

# Auto-detect best available (default)
export CLAUDE_TAB_BACKEND=auto
```

When set to a specific backend, no fallback is attempted — if that backend fails, the task description is not updated. When set to `auto` (or unset), all backends are tried in order.

### Token Budget

Control how much context `/recall` injects and how memo entries are deduplicated.

Add to `~/.claude/memos/config.yaml`:

```yaml
# Max tokens loaded per /recall invocation (default: 8000, 0 = unlimited)
recall_token_budget: 8000

# Merge similar memo entries within this window in seconds (default: 300, 0 = disabled)
memo_merge_window: 300

# Title similarity threshold for merging (0.0-1.0, default: 0.6)
memo_merge_threshold: 0.6
```

**Recall loading modes:**
- **Full**: file fits within budget → loaded as-is
- **Summary**: file exceeds budget → only headers + conclusions loaded
- **Truncated**: summary exceeds budget → most recent entries loaded up to budget

Override per-invocation: `/recall --budget 4000` or `/recall --full` (no limit).

## Install

Requires [jq](https://jqlang.github.io/jq/):
```bash
brew install jq  # macOS
apt install jq   # Debian/Ubuntu
```

Then:
```bash
git clone https://github.com/lightpointventures/claude-tab-tracking.git
cd claude-tab-tracking && ./install.sh
```

Open a new Claude Code session — the statusline appears immediately.

## Conversation memory

The plugin automatically extracts key decisions, conclusions, and TODOs from each conversation and saves them as structured memos.

### How it works

After each assistant response (when the conversation has 3+ turns), the plugin extracts tagged items:

- **Decisions** — architectural and design choices made
- **Data** — facts, statistics, findings
- **Conclusions** — root cause analysis, outcomes
- **TODOs** — action items for follow-up

Memos are saved to `~/.claude/memos/{project}/{YYYY-MM-DD}.md`, organized by project and date.

### Recalling past context

Use `/recall` to load memos from previous sessions:

```
/recall              # list recent projects, pick one interactively
/recall my-project   # skip to date selection for a specific project
/recall 3-20         # load all memos from that date
```

On session start, the plugin shows a hint if memos exist:
```
[memo] Recent projects: my-app (today, 3 entries) | api-server (3-20, 5 entries)
Type /recall for details
```

### Viewing memos

Use `/memo` to browse memos without loading them into context:

```
/memo                # show today's memos
/memo 3-20           # show memos from a specific date
/memo my-project     # list recent memo files for a project
/memo keyword        # search across all memos
```

## Manual task override

Use the `/task` slash command to set a custom description for the current session:

```
/task Reviewing Q1 strategy report
```

This writes a `MANUAL:` prefix that pins the description and stops auto-updates for this session. The badge shows `[SET]`.

## Files installed

| File | Purpose |
|------|---------|
| `~/.claude/scripts/session_start.sh` | SessionStart hook |
| `~/.claude/scripts/dynamic_task_update.sh` | Stop hook (bash wrapper) |
| `~/.claude/scripts/dynamic_task_update.py` | Stop hook (transcript parser + LLM summarization) |
| `~/.claude/scripts/cli_background.py` | Background helper for Claude Code CLI backend |
| `~/.claude/scripts/claude_cli_common.py` | Shared `claude -p` invocation helpers |
| `~/.claude/scripts/memo_search.py` | Full-text memo search (`/memo search`) |
| `~/.claude/scripts/task_completed.sh` | TaskCompleted hook |
| `~/.claude/scripts/session_statusline.sh` | Statusline renderer |
| `~/.claude/scripts/session_end.sh` | SessionEnd cleanup |
| `~/.claude/commands/task.md` | `/task` slash command |
| `~/.claude/commands/memo.md` | `/memo` slash command |
| `~/.claude/commands/recall.md` | `/recall` slash command |
| `~/.claude/session-tasks/` | Session state (auto-cleaned after 7 days) |
| `~/.claude/session-tasks/_errors.log` | Backend failures, if any (hooks themselves never fail) |
| `~/.claude/memos/` | Conversation memos (organized by project/date) |

## Uninstall

```bash
rm -f ~/.claude/scripts/session_start.sh \
      ~/.claude/scripts/dynamic_task_update.sh \
      ~/.claude/scripts/dynamic_task_update.py \
      ~/.claude/scripts/cli_background.py \
      ~/.claude/scripts/claude_cli_common.py \
      ~/.claude/scripts/memo_search.py \
      ~/.claude/scripts/task_completed.sh \
      ~/.claude/scripts/session_statusline.sh \
      ~/.claude/scripts/session_end.sh \
      ~/.claude/commands/task.md \
      ~/.claude/commands/memo.md \
      ~/.claude/commands/recall.md
rm -rf ~/.claude/session-tasks/
rm -rf ~/.claude/memos/
```

Or use the uninstall script:
```bash
cd claude-tab-tracking && ./uninstall.sh
```

## Changelog

### 2026-09-25

- **Fix: CLI backend never ran (sessions stuck at `[---]`)** — The `CLAUDE_TAB_SKIP_HOOK` recursion guard ran at import time in `dynamic_task_update.py`, but the background helper is launched with that variable set and imports the module, so it exited before calling `claude -p`. On machines without `ANTHROPIC_API_KEY` or Ollama this silently disabled task updates and memos. The guard now lives in `main()`.
- **Fix: stale statusline on CLI failure** — If `claude -p` fails, times out, or returns a login banner, the helper now falls back to the keyword summary instead of leaving the previous description in place. Failures are recorded in `~/.claude/session-tasks/_errors.log`.
- **Fix: out-of-order background results** — Each Stop hook stamps a generation token; a slower helper from an earlier turn no longer overwrites a newer result. Helpers also respect a `/task` pin set while they were running.
- **Fix: injected transcript entries polluted summaries** — Slash-command echoes, `<system-reminder>` blocks, task notifications, subagent messages and interrupted requests are now skipped when reading the transcript, so they can no longer become the "first user message" anchor.
- **Fix: resume/compact reset the task** — `SessionStart` fires on resume, `/clear` and auto-compact; the placeholder is now written only on a fresh start or when no task file exists. The memo overview is printed only on startup.
- **Fix: `session_start.sh` integer error** — Memo files with zero entries produced `integer expression expected` on stderr.
- **Fix: Stop hook output** — `dynamic_task_update.sh` prints `{"continue":true,"suppressOutput":true}` on every exit path and pins a sane `PATH`.
- **Improvement: statusline** — Uses `context_window.used_percentage` when Claude Code provides it (token-count fallback kept), shows the model name, renders task text with `printf` so backslashes are shown verbatim, and stays quiet on malformed input.
- **Improvement: installer** — Re-running `install.sh` no longer duplicates hooks that were registered with absolute paths; it prints which summarization backend will be used. `uninstall.sh` now removes `memo_search.py` and `claude_cli_common.py` and uses the same interpreter resolution as the installer.
- **Improvement: sidecar cleanup** — `.lock`/`.gen` files are removed at session end and swept with the 7-day cleanup.
- **Tests** — 125 tests, including end-to-end runs of every shell hook against a temporary `HOME`.

### 2026-03-26

- **New: Multi-layer task history** — Up to 3 previous completed tasks stored (`PREV:1/2/3` format), top 2 displayed in statusline. Backward compatible with old `PREV:` format.
- **Removed: API cost display** — Initially added but removed; the field shows estimated API-equivalent cost which is misleading for Max subscribers.
- **New: Memo full-text search** — `/memo search <keyword>` searches all memos across projects. New `memo_search.py` backend.
- **New: Uninstall script** — `./uninstall.sh` cleanly reverses installation (hooks, scripts, commands). Preserves user data.
- **Fix: duplicated parse logic** — `cli_background.py` now imports from `dynamic_task_update` instead of duplicating 33 lines.
- **Fix: missing logging import** — `archive_old_memos()` no longer silently swallows errors.
- **Fix: INIT: prefix not stripped** — `task_completed.sh` now handles all 5 task prefixes.
- **Fix: temp file leak** — Background CLI helper uses `try/finally` for cleanup.
- **Improvement: configurable Ollama timeout** — Default raised from 10s to 15s, configurable via `config.yaml`.
- **Improvement: memo file locking** — `fcntl` prevents concurrent write corruption.
- **Improvement: cleanup safety** — Session task cleanup no longer deletes `current_*.txt` lookup files.

### 2026-03-22

- **Fix: CLI backend infinite loop** — Child `claude -p` sessions now run with `disableAllHooks` + env-var guard to prevent recursive Stop-hook execution. Thanks to [@GP2P](https://github.com/GP2P) for PR #3.
- **Fix: crash on prompt file read failure** — `cli_background.py` no longer throws `UnboundLocalError` when the temp prompt file can't be read.
- **Fix: installer error on malformed settings.json** — Now shows a clear error message instead of a Python traceback.
- **Fix: memo overview breaks on paths with spaces** — `session_start.sh` no longer word-splits project directory paths.
- **Fix: `/task` command drops previous task history** — PREV line is now preserved when manually setting a task.
- **Fix: memo archival skips all projects on single directory error** — Per-directory error handling added.
- **Fix: task file race condition** — File locking prevents concurrent background processes from corrupting task state.
- **Fix: Linux compatibility** — Falls back to PATH `python3` when `/usr/bin/python3` doesn't exist.

### 2026-03-21

- **New: Conversation memory** — Automatically extracts decisions, conclusions, and TODOs from conversations. Saved as structured memos organized by project and date.
- **New: `/recall` command** — Interactively load past memos into current session context.
- **New: `/memo` command** — Browse and search memos without loading them.
- **New: Session start memo hint** — Shows recent project memo counts on session start.

## Author

Built by [Lightpoint Ventures](https://github.com/lightpointventures)

## License

MIT
