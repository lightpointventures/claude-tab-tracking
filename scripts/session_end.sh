#!/bin/bash
# SessionEnd hook: removes cwd lookup file when session terminates.
# Must stay fast: SessionEnd hooks share a ~1.5s budget.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)

if [ -z "$CWD" ]; then
  exit 0
fi

cwd_hash() {
  if command -v md5 &>/dev/null; then
    echo "$1" | md5 | cut -c1-8
  else
    echo "$1" | md5sum | cut -c1-8
  fi
}
CWD_HASH=$(cwd_hash "$CWD")
TASKS_DIR="$HOME/.claude/session-tasks"
LOOKUP="$TASKS_DIR/current_${CWD_HASH}.txt"

# Only remove if this session owns the lookup (not a different session)
if [ -f "$LOOKUP" ] && [ "$(cat "$LOOKUP")" = "$SESSION_ID" ]; then
  rm -f "$LOOKUP"
fi

# Sidecar files are only useful while the session is live
if [ -n "$SESSION_ID" ]; then
  rm -f "$TASKS_DIR/${SESSION_ID}.txt.lock" "$TASKS_DIR/${SESSION_ID}.txt.gen"
fi

exit 0
