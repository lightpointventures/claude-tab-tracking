#!/bin/bash
# Notification hook (opt-in): desktop notification that carries the session's
# current task, so you know which tab wants you back. Enabled by the plugin's
# `notifications` option (CLAUDE_PLUGIN_OPTION_NOTIFICATIONS=true) or
# CLAUDE_TAB_NOTIFY=1. macOS uses osascript; Linux uses notify-send if present.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ENABLED="${CLAUDE_PLUGIN_OPTION_NOTIFICATIONS:-${CLAUDE_TAB_NOTIFY:-false}}"
case "$ENABLED" in
  true|1|yes|on) ;;
  *) exit 0 ;;
esac

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
KIND=$(echo "$INPUT" | jq -r '.notification_type // .type // .matcher // ""' 2>/dev/null)
MESSAGE=$(echo "$INPUT" | jq -r '.message // .title // ""' 2>/dev/null)
CWD=$(echo "$INPUT" | jq -r '.cwd // ""' 2>/dev/null)

TASK=""
if [ -n "$SESSION_ID" ] && [ -f "$HOME/.claude/session-tasks/${SESSION_ID}.txt" ]; then
  TASK=$(head -1 "$HOME/.claude/session-tasks/${SESSION_ID}.txt" | sed -E 's/^(WIP|DONE|MANUAL|INIT)://')
fi

case "$KIND" in
  permission_prompt) TITLE="Claude Code needs approval" ;;
  idle_prompt)       TITLE="Claude Code is waiting for you" ;;
  agent_completed)   TITLE="Background agent finished" ;;
  *)                 TITLE="Claude Code" ;;
esac
SUBTITLE="${CWD##*/}"
BODY="${TASK:-$MESSAGE}"
[ -z "$BODY" ] && BODY="$MESSAGE"

if command -v osascript >/dev/null 2>&1; then
  # Escape double quotes and backslashes for AppleScript string literals
  esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
  osascript -e "display notification \"$(esc "$BODY")\" with title \"$(esc "$TITLE")\" subtitle \"$(esc "$SUBTITLE")\"" >/dev/null 2>&1 || true
elif command -v notify-send >/dev/null 2>&1; then
  notify-send "$TITLE · $SUBTITLE" "$BODY" >/dev/null 2>&1 || true
fi
exit 0
