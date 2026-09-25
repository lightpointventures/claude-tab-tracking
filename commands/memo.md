---
description: "View or search conversation memos"
---

View or search conversation memos stored in `~/.claude/memos/`.

When this command is invoked, determine what the user wants based on the argument:

1. **No argument** (`/memo`):
   - Run: `date +%Y-%m-%d` to get today's date
   - Use Glob to find: `~/.claude/memos/*/YYYY-MM-DD.md`
   - Read and display all matching files, grouped by project

2. **Date argument** (matches pattern like `3-20`, `03-20`, or `2026-03-20`):
   - Convert to `YYYY-MM-DD` format (assume current year if not specified)
   - Use Glob to find: `~/.claude/memos/*/YYYY-MM-DD.md`
   - Read and display all matching files

3. **Project name** (matches a directory under `~/.claude/memos/`):
   - Use Glob to check if `~/.claude/memos/{argument}/` exists
   - If yes, list the last 7 `.md` files in that directory
   - Read and display them

4. **`search <keyword>`** (`/memo search JWT`):
   - Call the search helper: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/memo_search.py" "<keyword>"`
   - This performs full-text search across all memo files (case-insensitive)
   - Displays matching entries with project name, date, time, and the matching line
   - Supports `--max N` to limit results (default 10)

5. **`add <text>`** (`/tabtrack:memo add 决定用 sqlite 存索引`):
   - File a hand-written note under the current task. Find the task first:
     `CWD_HASH=$(echo "$PWD" | (command -v md5 &>/dev/null && md5 || md5sum) | cut -c1-8); SID=$(cat ~/.claude/session-tasks/current_${CWD_HASH}.txt 2>/dev/null); TASK=$(head -1 ~/.claude/session-tasks/$SID.txt 2>/dev/null | sed -E 's/^(WIP|DONE|MANUAL|INIT)://')`
   - Then: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/memo_recall.py" add --task "$TASK" "<text>"`
   - Hand-written notes are tagged 【手记】 and rank above hook-written bullets in `/tabtrack:recall`.

6. **Keyword** (anything else):
   - Use Grep to search for the keyword across all files in `~/.claude/memos/`
   - Display matching entries with their project and date context

Resolution order: check date pattern first, then project directory, then the "search" and "add" prefixes, then treat as keyword.

Format the output cleanly — show project name as a header, entries as bullet lists.
