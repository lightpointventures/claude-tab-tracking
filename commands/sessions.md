---
description: "Overview of every live Claude Code session: what each one is doing right now"
allowed-tools: Bash
---

Show what every running Claude Code session on this machine is working on.

1. Find this session's id so it can be marked in the list:

```bash
CWD_HASH=$(echo "$PWD" | (command -v md5 &>/dev/null && md5 || md5sum) | cut -c1-8)
SELF=$(cat ~/.claude/session-tasks/current_${CWD_HASH}.txt 2>/dev/null)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sessions_overview.py" ${SELF:+--self "$SELF"}
```

2. Show the script's output to the user verbatim inside a code block. Do not rewrite, summarize or reorder it. The `▶` marks this session.

3. If the user passed `json` as the argument, run the script with `--json` instead and show the raw JSON. If they passed `all`, add `--all` to include sessions whose process has already exited.

Each session shows, in order: native session name and busy/idle state (from Claude Code's own registry), the plugin's current task line (`[WIP]`, `[DONE]`, `[SET]`), running subagents with their one-line descriptions, and how many memo entries were written for that project today.
