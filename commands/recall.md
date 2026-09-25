---
description: "Load past conversation memos into context, within a token budget"
allowed-tools: Bash, AskUserQuestion
---

Load past memos from `~/.claude/memos/` into this conversation, without blowing the context. All selection and budgeting is done by a script; your job is to run it and show its output.

The script: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/memo_recall.py"`. It scores every entry (decisions and open TODOs count most; data decays fastest; a decision that a later, similar decision replaced is down-weighted; hand-written notes outrank hook-written ones) and picks the most valuable entries that fit `recall_token_budget` from `~/.claude/memos/config.yaml` (default 8000).

Decide by the argument:

1. **No argument** (`/tab:recall`) — budgeted auto-load for the current project, last 14 days:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/memo_recall.py" auto
   ```
   Show the output verbatim in a code block. It ends with an index of entries that did not fit; if the user wants one of those, run `show` with its id (step 4).

2. **Project name** (`/tab:recall my-project`, or `all` for every project):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/memo_recall.py" auto --project <name>
   ```

3. **Index only** (`/tab:recall index`, optionally with a project and `--days N`): list entries one per line without loading their content:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/memo_recall.py" index [--project <name>] [--days N]
   ```
   Then ask which ids to load (AskUserQuestion is fine for short lists).

4. **Specific entries** (`/tab:recall general/2026-09-25#3,general/2026-09-25#5`): ids as printed by the index:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/memo_recall.py" show <id>[,<id>...]
   ```

5. **Budget override**: append `--budget N` to any `auto` call; `--full` disables the budget.

After loading, do not restate the memos; continue with the user's work using them as context. Superseded decisions are marked in the output; treat the newer one as current.
