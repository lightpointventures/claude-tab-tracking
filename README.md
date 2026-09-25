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
- `[SET]` — task manually set with `/tabtrack:task`

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
| 1 | Anthropic API (plugin option `anthropic_api_key`; `ANTHROPIC_API_KEY` for manual installs) | Best | ~2s | ~$1/month |
| 2 | Ollama (local model running) | Good | ~2s | Free |
| 3 | Claude Code CLI (Max subscription) | Best | ~10s (async) | Included in subscription |
| 4 | Keyword heuristics | Basic | instant | Free |

No setup needed — it works out of the box with any of the above.

#### Choosing a backend

Set the `CLAUDE_TAB_BACKEND` environment variable to pick a specific backend:

```bash
# Use only Claude Code CLI (Max subscription, no API key needed)
export CLAUDE_TAB_BACKEND=cli

# Use only the Anthropic API (set the anthropic_api_key plugin option first)
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

Control how much context `/tabtrack:recall` injects and how memo entries are deduplicated.

Add to `~/.claude/memos/config.yaml`:

```yaml
# Max tokens loaded per /tabtrack:recall invocation (default: 8000, 0 = unlimited)
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

Override per-invocation: `/tabtrack:recall --budget 4000` or `/tabtrack:recall --full` (no limit).

## Install

Requires [jq](https://jqlang.github.io/jq/) (`brew install jq` on macOS, `apt install jq` on Debian/Ubuntu) and Python 3 (preinstalled on macOS and most Linux).

### From the plugin marketplace (recommended)

Inside Claude Code:

```
/plugin marketplace add lightpointventures/claude-tab-tracking
/plugin install claude-tab-tracking@claude-tab-tracking
/tabtrack:setup
```

Or from your shell:

```bash
claude plugin marketplace add lightpointventures/claude-tab-tracking
claude plugin install claude-tab-tracking@claude-tab-tracking
```

then run `/tabtrack:setup` once inside Claude Code. Plugins cannot change the `statusLine` setting themselves, so that command writes it for you (with a backup of `settings.json`). Task tracking and memos are active as soon as the plugin is installed; `/tabtrack:setup` only controls what you see.

Updates: bump-free. The statusline entry points at a launcher in the plugin's data directory that always resolves to the installed version, so `claude plugin update claude-tab-tracking` needs no re-setup.

### Embed in another statusline

Already using [ccstatusline](https://github.com/sirmalloc/ccstatusline), [claude-powerline](https://github.com/Owloops/claude-powerline) or [claude-hud](https://github.com/jarrodwatts/claude-hud)? Keep it. The launcher has a `--segment` mode that prints only the `[WIP] …` line, so you can add it as a custom command segment:

```bash
~/.claude/plugins/data/claude-tab-tracking-claude-tab-tracking/statusline.sh --segment
```

`/tabtrack:setup` detects an existing statusline and shows this path for you.

### Manual install (no marketplace)

```bash
git clone https://github.com/lightpointventures/claude-tab-tracking.git
cd claude-tab-tracking && ./install.sh
```

This copies the scripts into `~/.claude/scripts/`, registers the hooks and statusline in `~/.claude/settings.json`, and installs the commands as `/task`, `/memo` and `/recall` (no `tab:` prefix). Do not combine it with the plugin install; `/tabtrack:setup` offers to remove a manual install it finds.

## What this plugin runs, sends and stores

Everything below is local unless stated otherwise.

- **Reads**: the current session's transcript (`~/.claude/projects/…/<session>.jsonl`), Claude Code's live-session registry (`~/.claude/sessions/`), subagent metadata next to the transcript, and the git branch/HEAD of the working directory.
- **Runs**: `jq`, `python3`, `git`; for the Claude Code CLI backend, a background `claude -p --model haiku` with hooks disabled; for notifications (opt-in), `osascript` on macOS or `notify-send` on Linux.
- **Sends**: a snippet of the conversation (first exchange plus the last 20 messages, each truncated to 300 characters) to exactly one summarizer, chosen in this order: the Anthropic API at `api.anthropic.com` if you set the `anthropic_api_key` option; a local Ollama server at `localhost:11434` if one is running; otherwise your own Claude Code login via `claude -p`. Nothing else leaves the machine. The plugin never reads credentials from your environment when installed as a plugin.
- **Stores**: task state under `~/.claude/session-tasks/`, memos under `~/.claude/memos/`, the statusline launcher under `~/.claude/plugins/data/`, and one pointer line in Claude Code's `MEMORY.md` for the project. Credential-looking strings are redacted before a memo is written.
- **Changes settings**: only `/tabtrack:setup`, which writes the `statusLine` entry in `~/.claude/settings.json` after backing the file up, and only when you run it.

## All sessions at a glance

`/tabtrack:sessions` lists every live Claude Code session on this machine, whether it was started from a terminal or the desktop app:

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

Per session: the native session name and busy/idle state (read from Claude Code's own registry in `~/.claude/sessions/`), this plugin's task line, subagents that are still running with their one-line descriptions, and how many memo entries that project has today. `▶` marks the session you ran it from. `/tabtrack:sessions json` prints the same data as JSON; `/tabtrack:sessions all` includes sessions whose process has exited. The underlying script, `scripts/sessions_overview.py`, works standalone too.

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
- 【决策】name the plugin "tab" so commands are /tabtrack:*
- 【子代理】general-purpose「Research statusline tools on GitHub」 · 4m13s
```

Agents that ran for less than 15 seconds are skipped. Turn this off with `memo_subagents: false` in `~/.claude/memos/config.yaml`.

### Desktop notifications (optional)

With the plugin's **Desktop notifications** option turned on (`/plugin` → configure, or `claude plugin install … --config notifications=true`), you get a system notification when a session waits for input, needs a permission, or a background agent completes. The notification carries the session's current task, so with several sessions open you know which one wants you. macOS uses `osascript`; Linux uses `notify-send` when present. Off by default.

### Recalling past context

`/tabtrack:recall` loads memos back into the conversation within a token budget, in two stages: the entries that fit are loaded in full, the rest appear as a one-line index you can fetch by id.

```
/tabtrack:recall                       # current project, last 14 days, budgeted
/tabtrack:recall my-project            # another project ("all" for every project)
/tabtrack:recall index                 # list entries without loading them
/tabtrack:recall general/2026-09-25#3  # load specific entries by id
/tabtrack:recall --budget 4000         # override the budget; --full disables it
```

Which entries make the cut is decided by a score, not by date alone:

| Tag | Weight | Half-life |
|-----|--------|-----------|
| 【决策】 decision | 1.0 | 90 days |
| 【TODO】 open | 1.0 | none (closed TODOs drop to 0.1) |
| 【手记】 hand-written note | 1.0 | 90 days |
| 【结论】 conclusion | 0.7 | 30 days |
| 【数据】 data | 0.4 | 14 days |
| 【子代理】 subagent | 0.3 | 7 days |

Bullets written by the hooks count half as much as notes you add yourself with `/tabtrack:memo add`. A decision that a later, similar decision in the same project replaced is marked *superseded* and weighted 0.35. The budget comes from `recall_token_budget` in `~/.claude/memos/config.yaml` (default 8000). The script behind this, `scripts/memo_recall.py`, can be used directly.

### Picking up where you left off

When a session ends, the plugin remembers what that directory was working on together with the git HEAD. The next session started in the same directory within 7 days, with HEAD unchanged, opens with:

```
[tab] Last session in this directory (2h ago, HEAD unchanged): Migrate the parser to SQLite
[tab] Continue where it left off, or run /tabtrack:recall to load that day's memos.
```

Disable with `handoff: false` in `~/.claude/memos/config.yaml`.

### Coexisting with Claude Code's auto-memory

Claude Code keeps its own auto-memory (`MEMORY.md` plus topic files per project). This plugin does not write into it. It adds exactly one line to `MEMORY.md`, once, and only when the project already has memos: a pointer saying where the daily memos live and how to load them. Disable with `memory_pointer: false`.

### What is never written

Before a memo is written, credential-looking strings are replaced with `[REDACTED]`: API keys (`sk-ant-…`, `AKIA…`, `ghp_…`, `xox…`, Google keys), JWTs, bearer tokens, private key blocks, and `password=`/`token=`/`api_key=` style pairs.

### Viewing memos

Use `/tabtrack:memo` to browse memos without loading them into context:

```
/tabtrack:memo                # show today's memos
/tabtrack:memo 3-20           # show memos from a specific date
/tabtrack:memo my-project     # list recent memo files for a project
/tabtrack:memo search JWT     # full-text search across all memos
/tabtrack:memo add <text>     # file a hand-written note under the current task
```

## Manual task override

Use `/tabtrack:task` to set a custom description for the current session:

```
/tabtrack:task Reviewing Q1 strategy report
```

This writes a `MANUAL:` prefix that pins the description and stops auto-updates for this session. The badge shows `[SET]`.

## Files

Plugin layout (marketplace install):

| Path | Purpose |
|------|---------|
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | Plugin and marketplace manifests |
| `hooks/hooks.json` | Registers the SessionStart / Stop / SessionEnd hooks |
| `commands/setup.md` | `/tabtrack:setup`: writes the statusline entry |
| `commands/task.md`, `memo.md`, `recall.md`, `sessions.md` | `/tabtrack:task`, `/tabtrack:memo`, `/tabtrack:recall`, `/tabtrack:sessions` |
| `scripts/sessions_overview.py` | Live-session overview used by `/tabtrack:sessions` |
| `scripts/subagent_stop.sh` + `subagent_memo.py` | SubagentStop hook: subagent bullets in the memo |
| `scripts/notify.sh` | Notification hook (opt-in desktop notifications) |
| `scripts/session_start.sh` | SessionStart hook; also writes the statusline launcher |
| `scripts/dynamic_task_update.sh` + `.py` | Stop hook: transcript parsing + summarization backends |
| `scripts/cli_background.py`, `claude_cli_common.py` | Background helper for the Claude Code CLI backend |
| `scripts/session_statusline.sh` | Statusline renderer (`--segment` for embedding) |
| `scripts/session_end.sh` | SessionEnd cleanup |
| `scripts/memo_search.py` | Full-text memo search |
| `scripts/memo_recall.py` | Scored, budgeted recall (`auto` / `index` / `show` / `add`) |

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

then remove the `statusLine` key from `~/.claude/settings.json` if you set it with `/tabtrack:setup`. Memos and session state under `~/.claude/` are left in place.

Manual install: `./uninstall.sh` (removes the hooks, scripts and commands; keeps your data).

## Changelog

### 1.3.1 — 2026-09-25

- **Fix: completion marker at the end of the summary** — `[完成]`/`[done]` appended after the task text is now recognized (and stripped) instead of being shown inside the `[WIP]` line. Marketplace description updated to the new command prefix.

### 1.3.0 — 2026-09-25

- **Renamed: plugin `tab` → `tabtrack`** — Commands are now `/tabtrack:task`, `/tabtrack:memo`, `/tabtrack:recall`, `/tabtrack:sessions`, `/tabtrack:setup`. The install key (`claude-tab-tracking@claude-tab-tracking`), data directory and statusline launcher are unchanged, so existing installs keep working after `claude plugin update`.
- **Changed: API key handling** — When installed as a plugin, the Anthropic API backend uses only the plugin's `anthropic_api_key` option (stored in secure storage) and never picks up `ANTHROPIC_API_KEY` from your environment. Manual installs keep the environment fallback.
- **Docs: disclosure section** — README now lists exactly what the plugin reads, runs, sends and stores.

### 1.2.1 — 2026-09-25

- **Fix: auto-memory pointer for home and temp directories** — the hook named the project after the directory while memos use `general` there, so the pointer was never added.

### 1.2.0 — 2026-09-25

- **New: scored, budgeted recall** — `/tabtrack:recall` now runs `memo_recall.py`: entries are scored by tag weight, per-tag half-life, source (hand-written vs hook-written) and status (superseded decisions, closed TODOs), the best ones are loaded within `recall_token_budget`, and the rest are listed as an index to fetch by id (`show`). `index` lists without loading; `add` files a 【手记】 note.
- **New: `/tabtrack:memo add`** — Hand-written notes under the current task, weighted above hook output.
- **New: handoff anchor** — SessionEnd records the directory's task and git HEAD; the next session there (same HEAD, within 7 days) starts with that task as context. `handoff: false` disables.
- **New: auto-memory pointer** — One idempotent line in Claude Code's `MEMORY.md` pointing at this project's memos; never content. `memory_pointer: false` disables.
- **New: secret redaction** — API keys, JWTs, bearer tokens, private keys and `password=`-style pairs are replaced with `[REDACTED]` before any memo is written.
- Not added: a `PreCompact` capture point. The Stop hook already writes memos every turn and the on-disk transcript survives compaction, so there is nothing for it to save.

### 1.1.0 — 2026-09-25

- **New: `/tabtrack:sessions`** — Overview of every live session: native name and busy/idle state, this plugin's task line, running subagents with descriptions, today's memo count. Works across terminal and desktop-app sessions; `json` and `all` arguments.
- **New: subagents in the memo** — `SubagentStop` files each finished subagent (type, description, duration) under the current task; agents under 15 s are skipped; `memo_subagents: false` disables it.
- **New: optional desktop notifications** — Plugin option `notifications` (off by default) sends a notification carrying the session's task when it waits for input, needs approval, or a background agent completes.

### 1.0.0 — 2026-09-25

- **New: official plugin format** — Install with `/plugin marketplace add lightpointventures/claude-tab-tracking` and `/plugin install claude-tab-tracking@claude-tab-tracking`. Hooks register through `hooks/hooks.json`; commands are `/tabtrack:task`, `/tabtrack:memo`, `/tabtrack:recall`, plus the new `/tabtrack:setup`.
- **New: `/tabtrack:setup`** — Writes the `statusLine` entry (plugins cannot), pointing at a launcher in the plugin data directory that survives updates. Detects a manual (pre-plugin) install and offers to remove it so hooks do not run twice.
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
