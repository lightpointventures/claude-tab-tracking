#!/usr/bin/env python3
"""SubagentStop hook: record a finished subagent in today's memo.

Reads the hook payload from stdin (agent_id, agent_type, agent_transcript_path,
session_id, cwd) and appends one bullet under the session's current task:

    - 【子代理】Explore「Find auth code」 · 2m15s

Bullets from several subagents of the same task merge into one entry through
write_memo()'s merge window. Disable with `memo_subagents: false` in
~/.claude/memos/config.yaml. Never blocks: every failure path exits 0.
"""
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dynamic_task_update import (  # noqa: E402
    TASKS_DIR,
    load_memo_config,
    log_error,
    resolve_project_name,
    truncate_task,
    write_memo,
)

MIN_DURATION_S = 15  # skip trivial agents (a one-shot lookup adds noise, not memory)


_TS_RE = re.compile(r'"timestamp":\s*"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})')


def _duration(transcript_path):
    """Seconds between the first and last timestamped entry, or None."""
    first = last = None
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            for line in f:
                m = _TS_RE.search(line)
                if not m:
                    continue
                try:
                    t = datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    continue
                first = first or t
                last = t
    except OSError:
        return None
    if first and last:
        return int((last - first).total_seconds())
    return None


def _fmt(seconds):
    if seconds is None:
        return ''
    if seconds < 60:
        return f'{seconds}s'
    return f'{seconds // 60}m{seconds % 60:02d}s'


def _description(agent_id, transcript_path):
    if not transcript_path:
        return ''
    meta_path = os.path.join(os.path.dirname(transcript_path), f'agent-{agent_id}.meta.json')
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            return json.load(f).get('description', '') or ''
    except (OSError, ValueError):
        return ''


def _current_task(session_id):
    try:
        with open(os.path.join(TASKS_DIR, f'{session_id}.txt'), 'r', encoding='utf-8') as f:
            first = f.readline().strip()
    except OSError:
        return ''
    for prefix in ('WIP:', 'DONE:', 'MANUAL:'):
        if first.startswith(prefix):
            return first[len(prefix):].strip()
    return ''


def build_bullet(agent_type, description, seconds):
    label = agent_type or 'agent'
    desc = truncate_task(description, 60) if description else ''
    parts = [f'【子代理】{label}' + (f'「{desc}」' if desc else '')]
    dur = _fmt(seconds)
    if dur:
        parts.append(dur)
    return ' · '.join(parts)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    config = load_memo_config()
    if not config.get('memo_subagents', True):
        return
    session_id = payload.get('session_id', '')
    agent_id = payload.get('agent_id', '')
    transcript = payload.get('agent_transcript_path', '')
    seconds = _duration(transcript)
    if seconds is not None and seconds < MIN_DURATION_S:
        return
    task = _current_task(session_id)
    if not task:
        return  # nothing to file it under yet
    bullet = build_bullet(payload.get('agent_type', ''), _description(agent_id, transcript), seconds)
    project = resolve_project_name(payload.get('cwd') or os.environ.get('PWD', os.getcwd()))
    try:
        write_memo(bullet, task, project, merge_config=config)
    except Exception as exc:
        log_error(f'subagent memo failed: {type(exc).__name__}: {exc}')


if __name__ == '__main__':
    main()
