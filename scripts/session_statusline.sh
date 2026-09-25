#!/bin/bash
# Statusline: shows session task (WIP/DONE), context usage, and session duration

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

INPUT=$(cat)
if ! command -v jq &>/dev/null; then
  printf '[---] jq not found (brew install jq)\n'
  exit 0
fi
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)

# Context usage: prefer the percentage Claude Code computes; fall back to
# summing the current-usage token counts for older versions.
PCT=$(echo "$INPUT" | jq -r '.context_window.used_percentage // empty' 2>/dev/null | cut -d. -f1 2>/dev/null)
if [ -z "$PCT" ]; then
  USED_TOKENS=$(echo "$INPUT" | jq -r '
    ((.context_window.current_usage.input_tokens // 0) +
     (.context_window.current_usage.cache_creation_input_tokens // 0) +
     (.context_window.current_usage.cache_read_input_tokens // 0))
  ' 2>/dev/null | cut -d. -f1 2>/dev/null)
  USED_TOKENS=${USED_TOKENS:-0}
  WINDOW_SIZE=$(echo "$INPUT" | jq -r '.context_window.context_window_size // 200000' 2>/dev/null | cut -d. -f1 2>/dev/null)
  WINDOW_SIZE=${WINDOW_SIZE:-200000}
  if [ "$WINDOW_SIZE" -gt 0 ] 2>/dev/null; then
    PCT=$(( USED_TOKENS * 100 / WINDOW_SIZE ))
  else
    PCT=0
  fi
fi
[ "$PCT" -ge 0 ] 2>/dev/null || PCT=0
DURATION_MS=$(echo "$INPUT" | jq -r '.cost.total_duration_ms // 0' 2>/dev/null | cut -d. -f1 2>/dev/null)
DURATION_MS=${DURATION_MS:-0}
[ "$DURATION_MS" -ge 0 ] 2>/dev/null || DURATION_MS=0
DIR=$(echo "$INPUT" | jq -r '.workspace.current_dir // .cwd // ""' 2>/dev/null)
DIR_NAME="${DIR##*/}"
MODEL=$(echo "$INPUT" | jq -r '.model.display_name // empty' 2>/dev/null)

# Format duration: show as "5min" or "1h23m"
DURATION_MIN=$(( DURATION_MS / 60000 ))
if [ "$DURATION_MIN" -ge 60 ]; then
  DURATION_FMT="$(( DURATION_MIN / 60 ))h$(( DURATION_MIN % 60 ))m"
else
  DURATION_FMT="${DURATION_MIN}min"
fi

# ANSI colors
RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
CYAN='\033[36m'

# --- Line 1: Task status badge + description ---
TASK_FILE="$HOME/.claude/session-tasks/${SESSION_ID}.txt"

if [ -f "$TASK_FILE" ]; then
  RAW=$(head -1 "$TASK_FILE" | tr -d '\n')
  if [[ "$RAW" == DONE:* ]]; then
    BADGE="${GREEN}[DONE]${RESET}"
    TASK="${RAW#DONE:}"
  elif [[ "$RAW" == MANUAL:* ]]; then
    BADGE="${BOLD}[SET] ${RESET}"
    TASK="${RAW#MANUAL:}"
  elif [[ "$RAW" == WIP:* ]]; then
    BADGE="${YELLOW}[WIP] ${RESET}"
    TASK="${RAW#WIP:}"
  elif [[ "$RAW" == INIT:* ]]; then
    BADGE="${DIM}[---]${RESET}"
    TASK="${RAW#INIT:}"
  else
    BADGE="${DIM}[---]${RESET}"
    TASK="$RAW"
  fi
  # Truncate to 60 chars
  if [ ${#TASK} -gt 60 ]; then
    TASK="${TASK:0:57}..."
  fi
  printf '%b %s\n' "$BADGE" "$TASK"

  # --- Lines 2-3 (optional): Previous tasks (PREV:1 and PREV:2 only) ---
  # Supports both old format (PREV:task) and new format (PREV:N:task)
  PREV1="" PREV2=""
  while IFS= read -r line; do
    if [[ "$line" == PREV:* ]]; then
      REST="${line#PREV:}"
      if [[ "$REST" =~ ^1:(.*)$ ]]; then
        PREV1="${BASH_REMATCH[1]}"
      elif [[ "$REST" =~ ^2:(.*)$ ]]; then
        PREV2="${BASH_REMATCH[1]}"
      elif [[ ! "$REST" =~ ^[0-9]+: ]]; then
        # Old format: PREV:task — treat as PREV:1
        [ -z "$PREV1" ] && PREV1="$REST"
      fi
    fi
  done < "$TASK_FILE"
  if [ -n "$PREV1" ]; then
    if [ ${#PREV1} -gt 60 ]; then PREV1="${PREV1:0:57}..."; fi
    printf '%b %s%b\n' "${DIM}${GREEN}[DONE]${RESET} ${DIM}" "$PREV1" "$RESET"
  fi
  if [ -n "$PREV2" ]; then
    if [ ${#PREV2} -gt 60 ]; then PREV2="${PREV2:0:57}..."; fi
    printf '%b %s%b\n' "${DIM}${GREEN}[DONE]${RESET} ${DIM}" "$PREV2" "$RESET"
  fi
else
  printf '%b\n' "${DIM}[---] starting...${RESET}"
fi

# --- Last line: Directory | context% | duration ---
# Color context % based on usage
if [ "$PCT" -lt 50 ]; then
  PCT_COLOR="$GREEN"
elif [ "$PCT" -lt 80 ]; then
  PCT_COLOR="$YELLOW"
else
  PCT_COLOR="$RED"
fi

FOOTER="${DIM}${DIR_NAME}${RESET}  |  ctx ${PCT_COLOR}${PCT}%${RESET}  |  ${DIM}${DURATION_FMT}${RESET}"
if [ -n "$MODEL" ]; then
  FOOTER="${FOOTER}  |  ${DIM}${MODEL}${RESET}"
fi
printf '%b\n' "$FOOTER"
