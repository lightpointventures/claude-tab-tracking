#!/bin/bash
# claude-tab-tracking manual installer (no marketplace).
# Copies scripts into ~/.claude/scripts, commands into ~/.claude/commands, and
# registers hooks + statusline in ~/.claude/settings.json.
# Preferred install is the plugin marketplace; see README.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
SCRIPTS_DIR="$CLAUDE_DIR/scripts"
COMMANDS_DIR="$CLAUDE_DIR/commands"
TASKS_DIR="$CLAUDE_DIR/session-tasks"
MEMO_DIR="$CLAUDE_DIR/memos"
SETTINGS="$CLAUDE_DIR/settings.json"

echo "Installing claude-tab-tracking..."

# --- Check dependencies ---
if ! command -v jq &>/dev/null; then
  echo "Error: jq is required. Install with: brew install jq (macOS) or apt install jq (Debian/Ubuntu)"
  exit 1
fi

# Fixed interpreter paths first so PATH shims/virtualenvs cannot intercept.
PYTHON3=""
for candidate in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$candidate" ]; then
    PYTHON3="$candidate"
    break
  fi
done
[ -z "$PYTHON3" ] && PYTHON3=$(command -v python3 2>/dev/null || true)
if [ -z "$PYTHON3" ]; then
  echo "Error: python3 is required but not found."
  exit 1
fi

# --- Create directories ---
mkdir -p "$SCRIPTS_DIR" "$COMMANDS_DIR" "$TASKS_DIR" "$MEMO_DIR"

# --- Copy scripts ---
cp "$REPO_DIR/scripts/"*.sh "$SCRIPTS_DIR/"
cp "$REPO_DIR/scripts/"*.py "$SCRIPTS_DIR/"
chmod +x "$SCRIPTS_DIR/"*.sh "$SCRIPTS_DIR/"*.py
# Commands reference ${CLAUDE_PLUGIN_ROOT} (substituted only for plugin installs);
# point them at the copied scripts instead. /tabtrack:setup is plugin-only.
for cmd in task memo recall; do
  sed "s|\${CLAUDE_PLUGIN_ROOT}/scripts|$SCRIPTS_DIR|g" "$REPO_DIR/commands/$cmd.md" > "$COMMANDS_DIR/$cmd.md"
done

echo "Scripts installed to $SCRIPTS_DIR"

# --- Update settings.json ---
if [ ! -f "$SETTINGS" ]; then
  echo '{}' > "$SETTINGS"
fi

# Backup
cp "$SETTINGS" "${SETTINGS}.bak-$(date +%Y%m%d%H%M%S)"

# Merge new config using Python (avoids jq for complex nested merges)
"$PYTHON3" - "$SETTINGS" << 'PYEOF'
import json, os, sys

path = sys.argv[1]
try:
    with open(path) as f:
        d = json.load(f)
except json.JSONDecodeError as e:
    print(f"Error: {path} is not valid JSON: {e}", file=sys.stderr)
    print("Please fix or delete it and re-run install.sh", file=sys.stderr)
    sys.exit(1)

hooks = d.setdefault("hooks", {})

new_hooks = {
    "SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": "~/.claude/scripts/session_start.sh", "timeout": 10}]}],
    "Stop":         [{"hooks": [{"type": "command", "command": "~/.claude/scripts/dynamic_task_update.sh", "timeout": 15}]}],
    "SessionEnd":   [{"matcher": "", "hooks": [{"type": "command", "command": "~/.claude/scripts/session_end.sh", "timeout": 5}]}],
}

def script_name(command):
    """Compare hooks by script file name so '~/x.sh' and '/home/u/.claude/scripts/x.sh' match."""
    return os.path.basename(command.split()[0]) if command.strip() else ""

for event, config in new_hooks.items():
    existing = hooks.get(event, [])
    existing_cmds = set()
    for rule in existing:
        for h in rule.get("hooks", []):
            existing_cmds.add(script_name(h.get("command", "")))
    for rule in config:
        new_cmds = [h for h in rule["hooks"] if script_name(h["command"]) not in existing_cmds]
        if new_cmds:
            new_rule = dict(rule)
            new_rule["hooks"] = new_cmds
            existing.append(new_rule)
    hooks[event] = existing

sl = d.get("statusLine")
if not (isinstance(sl, dict) and "session_statusline.sh" in sl.get("command", "")):
    d["statusLine"] = {"type": "command", "command": "~/.claude/scripts/session_statusline.sh"}

with open(path, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")

print("settings.json updated")
PYEOF

# --- Report which summarization backend will be used ---
echo ""
echo "Summarization backend check:"
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo "  Claude API        available (ANTHROPIC_API_KEY set)"
else
  echo "  Claude API        not configured (ANTHROPIC_API_KEY unset)"
fi
if command -v curl &>/dev/null && curl -s -m 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "  Ollama            running on localhost:11434"
else
  echo "  Ollama            not running"
fi
if command -v claude &>/dev/null; then
  echo "  Claude Code CLI   found ($(command -v claude)) — used when the above are unavailable"
else
  echo "  Claude Code CLI   not on PATH — keyword heuristics will be used"
fi
echo "  Errors, if any, are written to $TASKS_DIR/_errors.log"

echo ""
echo "Done. Open a new Claude Code session to see live task tracking in the statusline."
echo "Use /task <description> to manually set a session task."
echo "Use /memo to view conversation memos, /recall to load past context."
