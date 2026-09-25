#!/bin/bash
# claude-tab-tracking uninstaller
# Removes hooks, scripts, and commands installed by install.sh.
# Does NOT remove user data (~/.claude/memos/, ~/.claude/session-tasks/).

set -euo pipefail

CLAUDE_DIR="$HOME/.claude"
SCRIPTS_DIR="$CLAUDE_DIR/scripts"
COMMANDS_DIR="$CLAUDE_DIR/commands"
SETTINGS="$CLAUDE_DIR/settings.json"

echo "Uninstalling claude-tab-tracking..."

# --- Check dependencies ---
PYTHON3=""
for candidate in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$candidate" ]; then
    PYTHON3="$candidate"
    break
  fi
done
[ -z "$PYTHON3" ] && PYTHON3=$(command -v python3 2>/dev/null || true)
if [ -z "$PYTHON3" ]; then
  echo "Error: python3 is required for settings.json cleanup."
  exit 1
fi

# --- Remove installed scripts ---
SCRIPT_FILES=(
  "claude_cli_common.py"
  "cli_background.py"
  "dynamic_task_update.py"
  "dynamic_task_update.sh"
  "memo_search.py"
  "session_end.sh"
  "session_start.sh"
  "session_statusline.sh"
  "task_completed.sh"
)

removed_scripts=0
for f in "${SCRIPT_FILES[@]}"; do
  target="$SCRIPTS_DIR/$f"
  if [ -f "$target" ]; then
    rm "$target"
    removed_scripts=$((removed_scripts + 1))
  fi
done
echo "Removed $removed_scripts script(s) from $SCRIPTS_DIR"

# --- Remove installed commands ---
COMMAND_FILES=("task.md" "memo.md" "recall.md")

removed_commands=0
for f in "${COMMAND_FILES[@]}"; do
  target="$COMMANDS_DIR/$f"
  if [ -f "$target" ]; then
    rm "$target"
    removed_commands=$((removed_commands + 1))
  fi
done
echo "Removed $removed_commands command(s) from $COMMANDS_DIR"

# --- Clean up settings.json (remove hooks and statusLine) ---
if [ -f "$SETTINGS" ]; then
  # Backup before modifying
  cp "$SETTINGS" "${SETTINGS}.bak-$(date +%Y%m%d%H%M%S)"

  "$PYTHON3" - "$SETTINGS" << 'PYEOF'
import json, os, sys

path = sys.argv[1]
try:
    with open(path) as f:
        d = json.load(f)
except (json.JSONDecodeError, FileNotFoundError):
    print("Warning: could not parse settings.json, skipping hook removal.", file=sys.stderr)
    sys.exit(0)

# Scripts registered by install.sh (matched by file name, so absolute and
# tilde-prefixed paths are both recognised)
OUR_SCRIPTS = {
    "session_start.sh",
    "dynamic_task_update.sh",
    "task_completed.sh",
    "session_end.sh",
}

def script_name(command):
    return os.path.basename(command.split()[0]) if command.strip() else ""

hooks = d.get("hooks", {})
changed = False

for event in list(hooks.keys()):
    rules = hooks[event]
    new_rules = []
    for rule in rules:
        new_hooks = [h for h in rule.get("hooks", []) if script_name(h.get("command", "")) not in OUR_SCRIPTS]
        if new_hooks:
            rule["hooks"] = new_hooks
            new_rules.append(rule)
        else:
            changed = True
    if new_rules:
        hooks[event] = new_rules
    else:
        del hooks[event]
        changed = True

# Remove statusLine if it points to our script
sl = d.get("statusLine", {})
if isinstance(sl, dict) and "session_statusline.sh" in sl.get("command", ""):
    del d["statusLine"]
    changed = True

if not hooks:
    d.pop("hooks", None)

if changed:
    with open(path, "w") as f:
        json.dump(d, f, indent=2)
        f.write("\n")
    print("Hooks and statusLine removed from settings.json")
else:
    print("No claude-tab-tracking hooks found in settings.json")
PYEOF
else
  echo "No settings.json found, skipping hook removal."
fi

# --- Warn about user data (do NOT delete) ---
echo ""
echo "User data preserved (not deleted):"
if [ -d "$CLAUDE_DIR/memos" ]; then
  echo "  $CLAUDE_DIR/memos/  (conversation memos)"
fi
if [ -d "$CLAUDE_DIR/session-tasks" ]; then
  echo "  $CLAUDE_DIR/session-tasks/  (session task files)"
fi
echo ""
echo "To remove user data manually:"
echo "  rm -rf ~/.claude/memos/ ~/.claude/session-tasks/"

echo ""
echo "Uninstall complete."
