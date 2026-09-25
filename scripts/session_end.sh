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

# Handoff anchor: remember what this directory was working on, keyed by cwd
# and git HEAD. session_start.sh replays it when the next session starts here
# with the same HEAD (i.e. nothing was committed in between).
TASK_FILE="$TASKS_DIR/${SESSION_ID}.txt"
if [ -n "$SESSION_ID" ] && [ -f "$TASK_FILE" ]; then
  TASK_LINE=$(head -1 "$TASK_FILE" | sed -E 's/^(WIP|DONE|MANUAL)://')
  case "$(head -1 "$TASK_FILE")" in
    INIT:*|"") TASK_LINE="" ;;
  esac
  if [ -n "$TASK_LINE" ]; then
    HEAD_SHA=$(git -C "$CWD" rev-parse HEAD 2>/dev/null || echo "")
    jq -n --arg sid "$SESSION_ID" --arg task "$TASK_LINE" --arg sha "$HEAD_SHA" --arg cwd "$CWD" \
      --arg at "$(date +%s)" '{session_id:$sid, task:$task, head:$sha, cwd:$cwd, at:($at|tonumber)}' \
      > "$TASKS_DIR/handoff_${CWD_HASH}.json.tmp" 2>/dev/null \
      && mv "$TASKS_DIR/handoff_${CWD_HASH}.json.tmp" "$TASKS_DIR/handoff_${CWD_HASH}.json"
  fi
fi

# The lock file is only useful while the session is live. The generation
# token (.txt.gen) is deliberately kept: a background summarizer for the last
# turn may still be running, and it must not mistake a missing token for
# "superseded" (it would drop the final task update and memo). The 7-day sweep
# in session_start.sh removes stale tokens.
if [ -n "$SESSION_ID" ]; then
  rm -f "$TASKS_DIR/${SESSION_ID}.txt.lock"
fi

exit 0
