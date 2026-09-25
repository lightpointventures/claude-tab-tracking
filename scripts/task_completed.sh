#!/bin/bash
# TaskCompleted hook: marks session task as DONE (strong completion signal)

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)

if [ -z "$SESSION_ID" ]; then
  exit 0
fi

TASK_FILE="$HOME/.claude/session-tasks/${SESSION_ID}.txt"

if [ ! -f "$TASK_FILE" ]; then
  exit 0
fi

# Read current description (line 1 only), strip any existing prefix
CURRENT=$(head -1 "$TASK_FILE")
DESC="${CURRENT#WIP:}"
DESC="${DESC#AUTO:}"
DESC="${DESC#DONE:}"
DESC="${DESC#MANUAL:}"
DESC="${DESC#INIT:}"
DESC=$(echo "$DESC" | tr -d '\n')

# Nothing meaningful to mark as done yet
if [ -z "$DESC" ]; then
  exit 0
fi

# Write DONE status, preserving all PREV lines (up to 3)
{
  echo "DONE:${DESC}"
  while IFS= read -r line; do
    if [[ "$line" == PREV:* ]]; then
      echo "$line"
    fi
  done < "$TASK_FILE"
} > "${TASK_FILE}.tmp" && mv "${TASK_FILE}.tmp" "$TASK_FILE"

exit 0
