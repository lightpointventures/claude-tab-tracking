#!/bin/bash
# SubagentStop hook: file the finished subagent under the current task in today's memo.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

if [ "${CLAUDE_TAB_SKIP_HOOK:-0}" = "1" ]; then
  exit 0
fi

PYTHON3=""
for candidate in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$candidate" ]; then
    PYTHON3="$candidate"
    break
  fi
done
[ -z "$PYTHON3" ] && PYTHON3=$(command -v python3 2>/dev/null || true)
[ -z "$PYTHON3" ] && exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$PYTHON3" "$SCRIPT_DIR/subagent_memo.py" >/dev/null 2>&1 || true
exit 0
