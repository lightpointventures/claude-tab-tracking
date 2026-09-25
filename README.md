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
- `[SET]` — task manually set with `/tab:task`

When you finish one task and start another, the previous tasks stay visible as dimmed `[DONE]` lines beneath the current task (up to 2 previous tasks displayed, 3 stored).

## How it works

Five Claude Code hooks work together:

| Hook | What it does |
|------|-------------|
| `SessionStart` | Writes `dir [branch]` as the initial label (kept on resume/compact); refreshes the statusline launcher |
| `Stop` | After each assistant response: reads the transcript, updates the task description, detects completion |
| `SubagentStop` | Files a finished subagent (type, description, duration) under the current task in today's memo |
| `Notification` | Optional desktop notification carrying the session's task (off by default) |
| `SessionEnd` | Cleans up session state files |

Completion is detected from the conversation itself (the summarizer marks a task `[完成]`/done), not from Claude Code's `TaskCompleted` event, which fires for individual background tasks rather than the session.

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

Control how much context `/tab:recall` injects and how memo entries are deduplicated.

Add to `~/.claude/memos/config.yaml`:

```yaml
# Max tokens loaded per /tab:recall invocation (default: 8000, 0 = unlimited)
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

Override per-invocation: `/tab:recall --budget 4000` or `/tab:recall --full` (no limit).

## Install

Requires [jq](https://jqlang.github.io/jq/) (`brew install jq` on macOS, `apt install jq` on Debian/Ubuntu) and Python 3 (preinstalled on macOS and most Linux).

### From the plugin marketplace (recommended)

Inside Claude Code:

```
/plugin marketplace add lightpointventures/claude-tab-tracking
/plugin install claude-tab-tracking@claude-tab-tracking
/tab:setup
```

Or from your shell:

```bash
claude plugin marketplace add lightpointventures/claude-tab-tracking
claude plugin install claude-tab-tracking@claude-tab-tracking
```

then run `/tab:setup` once inside Claude Code. Plugins cannot change the `statusLine` setting themselves, so that command writes it for you (with a backup of `settings.json`). Task tracking and memos are active as soon as the plugin is installed; `/tab:setup` only controls what you see.

Updates: bump-free. The statusline entry points at a launcher in the plugin's data directory that always resolves to the installed version, so `claude plugin update claude-tab-tracking` needs no re-setup.

### Embed in another statusline

Already using [ccstatusline](https://github.com/sirmalloc/ccstatusline), [claude-powerline](https://github.com/Owloops/claude-powerline) or [claude-hud](https://github.com/jarrodwatts/claude-hud)? Keep it. The launcher has a `--segment` mode that prints only the `[WIP] …` line, so you can add it as a custom command segment:

```bash
~/.claude/plugins/data/claude-tab-tracking-claude-tab-tracking/statusline.sh --segment
```

`/tab:setup` detects an existing statusline and shows this path for you.

### Manual install (no marketplace)

```bash
git clone https://github.com/lightpointventures/claude-tab-tracking.git
cd claude-tab-tracking && ./install.sh
```

This copies the scripts into `~/.claude/scripts/`, registers the hooks and statusline in `~/.claude/settings.json`, and installs the commands as `/task`, `/memo` and `/recall` (no `tab:` prefix). Do not combine it with the plugin install; `/tab:setup` offers to remove a manual install it finds.

## All sessions at a glance

`/tab:sessions` lists every live Claude Code session on this machine, whether it was started from a terminal or the desktop app:

```
5 live session(s) · 2 busy
▶ [busy] plugin release  ·  task-tracking  ·  3m ago
      [WIP]  Ship the marketplace install and update the README
      agents 1 running / 6 total
        ◐ general-purpose: Searching GitHub for tmux/notify repos
      memo   8 entries today · last: Decide plugin command namespace
  [idle] GluGlu 项目梳理与进展  ·  xinguanying · desktop  ·  1h10m ago
      [WIP]  筹备明日 Hillsdale 周边零售门店线下调研走访
```

Per session: the native session name and busy/idle state (read from Claude Code's own registry in `~/.claude/sessions/`), this plugin's task line, subagents that are still running with their one-line descriptions, and how many memo entries that project has today. `▶` marks the session you ran it from. `/tab:sessions json` prints the same data as JSON; `/tab:sessions all` includes sessions whose process has exited. The underlying script, `scripts/sessions_overview.py`, works standalone too.

## Conversation memory

The plugin automatically extracts key decisions, conclusions, and TODOs from each conversation and saves them as structured memos.

### How it works

After each assistant response (when the conversation has 3+ turns), the plugin extracts tagged items:

- **Decisions** — architectural and design choices made
- **Data** — facts, statistics, findings
- **Conclusions** — root cause analysis, outcomes
- **TODOs** — action items for follow-up

Memos are saved to `~/.claude/memos/{project}/{YYYY-MM-DD}.md`, organized by project and date.

### Subagents in the memo

When a subagent finishes (the `SubagentStop` hook), one bullet is filed under the session's current task:

```
## 14:02 | Ship the marketplace install
- 【决策】name the plugin "tab" so commands are /tab:*
- 【子代理】general-purpose「Research statusline tools on GitHub」 · 4m13s
```

Agents that ran for less than 15 seconds are skipped. Turn this off with `memo_subagents: false` in `~/.claude/memos/config.yaml`.

### Desktop notifications (optional)

With the plugin's **Desktop notifications** option turned on (`/plugin` → configure, or `claude plugin install … --config notifications=true`), you get a system notification when a session waits for input, needs a permission, or a background agent completes. The notification carries the session's current task, so with several sessions open you know which one wants you. macOS uses `osascript`; Linux uses `notify-send` when present. Off by default.

### Recalling past context

Use `/tab:recall` to load memos from previous sessions:

```
/tab:recall              # list recent projects, pick one interactively
/tab:recall my-project   # skip to date selection for a specific project
/tab:recall 3-20         # load all memos from that date
```

On session start, the plugin shows a hint if memos exist:
```
[memo] Recent projects: my-app (today, 3 entries) | api-server (3-20, 5 entries)
Type /tab:recall for details
```

### Viewing memos

Use `/tab:memo` to browse memos without loading them into context:

```
/tab:memo                # show today's memos
/tab:memo 3-20           # show memos from a specific date
/tab:memo my-project     # list recent memo files for a project
/tab:memo search JWT     # full-text search across all memos
```

## Manual task override

Use `/tab:task` to set a custom description for the current session:

```
/tab:task Reviewing Q1 strategy report
```

This writes a `MANUAL:` prefix that pins the description and stops auto-updates for this session. The badge shows `[SET]`.

## Files

Plugin layout (marketplace install):

| Path | Purpose |
|------|---------|
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | Plugin and marketplace manifests |
| `hooks/hooks.json` | Registers the SessionStart / Stop / SessionEnd hooks |
| `commands/setup.md` | `/tab:setup`: writes the statusline entry |
| `commands/task.md`, `memo.md`, `recall.md`, `sessions.md` | `/tab:task`, `/tab:memo`, `/tab:recall`, `/tab:sessions` |
| `scripts/sessions_overview.py` | Live-session overview used by `/tab:sessions` |
| `scripts/subagent_stop.sh` + `subagent_memo.py` | SubagentStop hook: subagent bullets in the memo |
| `scripts/notify.sh` | Notification hook (opt-in desktop notifications) |
| `scripts/session_start.sh` | SessionStart hook; also writes the statusline launcher |
| `scripts/dynamic_task_update.sh` + `.py` | Stop hook: transcript parsing + summarization backends |
| `scripts/cli_background.py`, `claude_cli_common.py` | Background helper for the Claude Code CLI backend |
| `scripts/session_statusline.sh` | Statusline renderer (`--segment` for embedding) |
| `scripts/session_end.sh` | SessionEnd cleanup |
| `scripts/memo_search.py` | Full-text memo search |

Data written on your machine (identical for both install methods):

| Path | Purpose |
|------|---------|
| `~/.claude/session-tasks/` | Per-session task state (auto-cleaned after 7 days) |
| `~/.claude/session-tasks/_errors.log` | Backend failures, if any (hooks themselves never fail) |
| `~/.claude/memos/` | Conversation memos (organized by project/date) |
| `~/.claude/plugins/data/claude-tab-tracking-claude-tab-tracking/statusline.sh` | Stable statusline launcher (plugin install only) |

## Uninstall

Plugin install:

```
/plugin uninstall claude-tab-tracking@claude-tab-tracking
```

then remove the `statusLine` key from `~/.claude/settings.json` if you set it with `/tab:setup`. Memos and session state under `~/.claude/` are left in place.

Manual install: `./uninstall.sh` (removes the hooks, scripts and commands; keeps your data).

## Changelog

### 1.1.0 — 2026-09-25

- **New: `/tab:sessions`** — Overview of every live session: native name and busy/idle state, this plugin's task line, running subagents with descriptions, today's memo count. Works across terminal and desktop-app sessions; `json` and `all` arguments.
- **New: subagents in the memo** — `SubagentStop` files each finished subagent (type, description, duration) under the current task; agents under 15 s are skipped; `memo_subagents: false` disables it.
- **New: optional desktop notifications** — Plugin option `notifications` (off by default) sends a notification carrying the session's task when it waits for input, needs approval, or a background agent completes.

### 1.0.0 — 2026-09-25

- **New: official plugin format** — Install with `/plugin marketplace add lightpointventures/claude-tab-tracking` and `/plugin install claude-tab-tracking@claude-tab-tracking`. Hooks register through `hooks/hooks.json`; commands are `/tab:task`, `/tab:memo`, `/tab:recall`, plus the new `/tab:setup`.
- **New: `/tab:setup`** — Writes the `statusLine` entry (plugins cannot), pointing at a launcher in the plugin data directory that survives updates. Detects a manual (pre-plugin) install and offers to remove it so hooks do not run twice.
- **New: `--segment` mode** — The statusline prints only the task line, for embedding in ccstatusline, claude-powerline or claude-hud.
- **Removed: `TaskCompleted` hook** — In current Claude Code this event fires when a background task/subagent completes, not when the session's work is done; it was flipping sessions to `[DONE]` prematurely. Completion now comes only from the summarizer.
- **Fix: keyword backend never ran from the main path** — `keyword_fallback()` rejected the arguments the backend loop passes to every backend, so `CLAUDE_TAB_BACKEND=keyword` (and the final fallback in auto mode) silently did nothing.

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
