#!/bin/bash
# Stop hook: dynamically updates task description and detects completion

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

finish_ok() {
  printf '{"continue":true,"suppressOutput":true}\n'
  exit 0
}

INPUT=$(cat)

# Prevent infinite loops
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [ "$STOP_ACTIVE" = "true" ]; then
  finish_ok
fi

# Prevent recursion from CLI backend subprocess
if [ "${CLAUDE_TAB_SKIP_HOOK:-0}" = "1" ]; then
  finish_ok
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')

if [ -z "$SESSION_ID" ] || [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ]; then
  finish_ok
fi

TASKS_DIR="$HOME/.claude/session-tasks"
TASK_FILE="$TASKS_DIR/${SESSION_ID}.txt"

# Don't overwrite manually-pinned tasks
if [ -f "$TASK_FILE" ]; then
  CURRENT=$(head -1 "$TASK_FILE")
  if [[ "$CURRENT" == MANUAL:* ]]; then
    finish_ok
  fi
fi

# Reset DONE tasks so Python script generates fresh description
# Shift existing PREVs down and insert current DONE as PREV:1
if [ -f "$TASK_FILE" ]; then
  CURRENT2=$(head -1 "$TASK_FILE")
  if [[ "$CURRENT2" == DONE:* ]]; then
    DESC="${CURRENT2#DONE:}"
    # Collect existing PREV lines, shift numbers up by 1
    PREV_LINES=""
    while IFS= read -r line; do
      if [[ "$line" == PREV:* ]]; then
        REST="${line#PREV:}"
        # New format: PREV:N:task
        if [[ "$REST" =~ ^([0-9]+):(.*)$ ]]; then
          N="${BASH_REMATCH[1]}"
          TASK="${BASH_REMATCH[2]}"
          NEW_N=$((N + 1))
          if [ "$NEW_N" -le 3 ]; then
            PREV_LINES="${PREV_LINES}PREV:${NEW_N}:${TASK}
"
          fi
        else
          # Old format: PREV:task — treat as PREV:1, shift to PREV:2
          PREV_LINES="${PREV_LINES}PREV:2:${REST}
"
        fi
      fi
    done < "$TASK_FILE"
    # Write new file: WIP + PREV:1 (current done) + shifted PREVs
    {
      echo "WIP:"
      echo "PREV:1:${DESC}"
      printf '%s' "$PREV_LINES"
    } > "$TASK_FILE"
  fi
fi

mkdir -p "$TASKS_DIR"

# Call the Python helper script. Prefer a fixed interpreter path over
# whatever `python3` resolves to, so shims and virtualenvs on PATH cannot
# intercept the call. Errors are recorded in ~/.claude/session-tasks/_errors.log.
PYTHON3=""
for candidate in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$candidate" ]; then
    PYTHON3="$candidate"
    break
  fi
done
[ -z "$PYTHON3" ] && PYTHON3=$(command -v python3 2>/dev/null || true)
[ -z "$PYTHON3" ] && finish_ok
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$PYTHON3" "$SCRIPT_DIR/dynamic_task_update.py" "$TRANSCRIPT" "$TASK_FILE" >/dev/null 2>&1 || true

finish_ok
