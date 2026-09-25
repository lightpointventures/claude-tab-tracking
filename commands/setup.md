---
description: "Show the session task line in your statusline (one-time setup)"
allowed-tools: Bash, Read, AskUserQuestion
---

Wire the claude-tab-tracking task line into the user's statusline. Plugins cannot change the `statusLine` setting themselves, so this command does it once, explicitly, with a backup.

Follow these steps in order. Substitute real values for placeholders in `{braces}`. Never build JSON by string concatenation: always go through the Python merge script below.

## Step 1: Find the stable launcher

The plugin's SessionStart hook writes a launcher at a path that survives plugin updates:

```bash
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
ls "$CLAUDE_DIR"/plugins/data/*/statusline.sh 2>/dev/null
```

- Exactly one result: that is `{LAUNCHER}`.
- No result: the SessionStart hook has not run in this session yet. Tell the user to run `/reload-plugins` (or restart Claude Code) and then `/tab:setup` again. Stop here.

## Step 2: Clean up a manual (pre-plugin) install, if present

Earlier versions were installed by copying scripts into `~/.claude/scripts/` and registering hooks directly in `settings.json`. If both the plugin and that manual install are active, every hook runs twice.

```bash
grep -c '\.claude/scripts/session_start\.sh\|\.claude/scripts/dynamic_task_update\.sh' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json" 2>/dev/null
```

If the count is greater than 0, tell the user a manual install was found and ask (AskUserQuestion) whether to remove it now. On yes, run the bundled cleanup, which removes only this plugin's legacy hooks, scripts and commands and never touches `~/.claude/memos/` or `~/.claude/session-tasks/`:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/uninstall.sh"
```

## Step 3: Read the current statusline setting

```bash
jq -r '.statusLine.command // ""' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json" 2>/dev/null
```

Decide by the result:

- **Empty**, or it already contains `session_statusline` or `claude-tab-tracking`: proceed to Step 4 (full statusline).
- **Anything else**: the user runs another statusline tool. Ask them (AskUserQuestion) which they prefer:
  1. *Replace it* with this plugin's statusline: proceed to Step 4.
  2. *Keep it and embed the task line as a segment*: skip Step 4 and show the instructions in Step 5.

## Step 4: Write the statusLine entry

Back up and merge with a real JSON serializer. Prefer a fixed interpreter path so shims on PATH cannot intercept:

```bash
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CLAUDE_DIR/settings.json"
PY=""; for c in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do [ -x "$c" ] && PY="$c" && break; done
[ -z "$PY" ] && PY=$(command -v python3)
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
cp "$SETTINGS" "$SETTINGS.bak-$(date +%Y%m%d%H%M%S)"
"$PY" - "$SETTINGS" "{LAUNCHER}" <<'PYEOF'
import json, sys
path, launcher = sys.argv[1], sys.argv[2]
with open(path) as f:
    d = json.load(f)
d["statusLine"] = {"type": "command", "command": launcher}
with open(path, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")
print("statusLine set to", launcher)
PYEOF
```

Then confirm to the user: "Statusline configured. It appears below the input box from the next response on; no restart needed." Also mention: "Use /tab:task to pin a description, /tab:memo and /tab:recall for conversation memos."

## Step 5: Segment mode (only if the user kept another statusline)

The launcher accepts `--segment`, which prints just the `[WIP] …` line with ANSI colors and nothing else. Show the user the exact command and where to put it:

```
{LAUNCHER} --segment
```

- **ccstatusline**: add a *Custom Command* widget and paste the command above.
- **claude-powerline**: add a custom segment that runs the command above.
- **claude-hud**: set `display.customLine` to the command above (or its output).
- Any other tool that accepts a shell command for a segment: same command. It reads the standard statusline JSON from stdin.

Do not edit `settings.json` in this branch.
