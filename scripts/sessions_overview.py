#!/usr/bin/env python3
"""Overview of every live Claude Code session on this machine.

Joins three sources, none of which require a server or a daemon:
  * Claude Code's own live-session registry  ~/.claude/sessions/<pid>.json
    (name, busy/idle, cwd, desktop vs terminal)
  * this plugin's per-turn task line          ~/.claude/session-tasks/<id>.txt
  * subagent metadata next to the transcript  ~/.claude/projects/*/<id>/subagents/

Usage:
    sessions_overview.py [--self SESSION_ID] [--json] [--all]

--self marks the calling session. --all includes sessions whose process is
gone (normally hidden). Output is plain text meant to be shown verbatim.
"""
import glob
import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime

CLAUDE_DIR = os.environ.get('CLAUDE_CONFIG_DIR') or os.path.join(str(pathlib.Path.home()), '.claude')
SESSIONS_DIR = os.path.join(CLAUDE_DIR, 'sessions')
TASKS_DIR = os.path.join(CLAUDE_DIR, 'session-tasks')
PROJECTS_DIR = os.path.join(CLAUDE_DIR, 'projects')
MEMOS_DIR = os.path.join(CLAUDE_DIR, 'memos')

ACTIVE_WINDOW_S = 90   # a subagent transcript touched within this window counts as running
TASK_WIDTH = 46


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _age(ms_or_s):
    """Human age of an epoch timestamp (ms or s)."""
    if not ms_or_s:
        return ''
    t = float(ms_or_s)
    if t > 1e12:
        t /= 1000.0
    d = max(0, int(time.time() - t))
    if d < 60:
        return f'{d}s'
    if d < 3600:
        return f'{d // 60}m'
    return f'{d // 3600}h{(d % 3600) // 60:02d}m'


def _read_task(session_id):
    """Return (badge, text, prev1) from the plugin's task file."""
    path = os.path.join(TASKS_DIR, f'{session_id}.txt')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = [ln.rstrip('\n') for ln in f]
    except OSError:
        return '', '', ''
    if not lines:
        return '', '', ''
    first = lines[0]
    badge, text = '', first
    for prefix, b in (('WIP:', 'WIP'), ('DONE:', 'DONE'), ('MANUAL:', 'SET'), ('INIT:', '---')):
        if first.startswith(prefix):
            badge, text = b, first[len(prefix):]
            break
    prev1 = ''
    for ln in lines[1:]:
        m = re.match(r'^PREV:(?:1:)?(.*)$', ln)
        if m and not re.match(r'^PREV:[2-9]:', ln):
            prev1 = m.group(1)
            break
    return badge, text.strip(), prev1.strip()


def _find_transcript_dir(session_id):
    hits = glob.glob(os.path.join(PROJECTS_DIR, '*', f'{session_id}.jsonl'))
    if not hits:
        return None
    return os.path.join(os.path.dirname(hits[0]), session_id)


def _subagents(session_id, now=None):
    """Return list of dicts: description, agent_type, running(bool), age."""
    now = now or time.time()
    base = _find_transcript_dir(session_id)
    out = []
    if not base:
        return out
    for meta_path in sorted(glob.glob(os.path.join(base, 'subagents', 'agent-*.meta.json'))):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        transcript = meta_path.replace('.meta.json', '.jsonl')
        try:
            mtime = os.path.getmtime(transcript)
        except OSError:
            mtime = 0
        out.append({
            'description': meta.get('description', ''),
            'agent_type': meta.get('agentType', ''),
            'running': (now - mtime) <= ACTIVE_WINDOW_S,
            'age': _age(mtime),
        })
    return out


def _project_name(cwd):
    # Mirrors dynamic_task_update.resolve_project_name without importing it
    # (this script is also used standalone).
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from dynamic_task_update import resolve_project_name
        return resolve_project_name(cwd)
    except Exception:
        return re.sub(r'[^a-zA-Z0-9_-]', '-', os.path.basename(cwd or '')).lower()[:50] or 'general'


def _memo_today(cwd):
    """Return (entry_count, last_title) for today's memo file of this cwd's project."""
    project = _project_name(cwd)
    path = os.path.join(MEMOS_DIR, project, datetime.now().strftime('%Y-%m-%d') + '.md')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except OSError:
        return 0, ''
    titles = [re.sub(r'^##\s+\d{1,2}:\d{2}\s*\|\s*', '', ln.strip()) for ln in lines if ln.startswith('## ')]
    return len(titles), (titles[-1] if titles else '')


def collect(include_dead=False, self_id=None):
    sessions = []
    for path in glob.glob(os.path.join(SESSIONS_DIR, '*.json')):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                reg = json.load(f)
        except (OSError, ValueError):
            continue
        sid = reg.get('sessionId')
        if not sid:
            continue
        alive = _pid_alive(reg.get('pid'))
        if not alive and not include_dead:
            continue
        badge, task, prev1 = _read_task(sid)
        agents = _subagents(sid)
        memo_count, memo_last = _memo_today(reg.get('cwd', ''))
        sessions.append({
            'session_id': sid,
            'pid': reg.get('pid'),
            'alive': alive,
            'name': reg.get('name') or '',
            'status': reg.get('status') or '',
            'status_age': _age(reg.get('statusUpdatedAt')),
            'started_age': _age(reg.get('startedAt')),
            'cwd': reg.get('cwd', ''),
            'dir': os.path.basename(reg.get('cwd', '') or '') or reg.get('cwd', ''),
            'entrypoint': reg.get('entrypoint', ''),
            'badge': badge,
            'task': task,
            'prev': prev1,
            'subagents': agents,
            'memo_count': memo_count,
            'memo_last': memo_last,
            'is_self': sid == self_id,
        })
    # busy first, then most recently active
    sessions.sort(key=lambda s: (s['status'] != 'busy', -(_age_seconds(s['status_age']))))
    return sessions


def _age_seconds(age):
    m = re.match(r'^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$', age or '')
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return -(h * 3600 + mi * 60 + s)  # negative so "more recent" sorts first after negation


def _clip(text, width):
    text = (text or '').replace('\n', ' ')
    return text if len(text) <= width else text[:width - 1] + '…'


def render(sessions):
    if not sessions:
        return 'No live Claude Code sessions found.'
    lines = [f'{len(sessions)} live session(s) · {sum(1 for s in sessions if s["status"] == "busy")} busy']
    for s in sessions:
        marker = '▶' if s['is_self'] else ' '
        status = 'busy' if s['status'] == 'busy' else 'idle'
        where = s['dir'] + ('' if s['entrypoint'] in ('cli', '') else f' · {s["entrypoint"].replace("claude-", "")}')
        head = f'{marker} [{status:<4}] {s["name"] or "(unnamed)"}  ·  {where}  ·  {s["status_age"]} ago'
        lines.append(head)
        if s['task']:
            badge = f'[{s["badge"]}]' if s['badge'] else '[---]'
            lines.append(f'      {badge:<6} {_clip(s["task"], TASK_WIDTH)}')
        running = [a for a in s['subagents'] if a['running']]
        if s['subagents']:
            summary = f'      agents {len(running)} running / {len(s["subagents"])} total'
            lines.append(summary)
            for a in running[:3]:
                lines.append(f'        ◐ {a["agent_type"]}: {_clip(a["description"], TASK_WIDTH)}')
        if s['memo_count']:
            lines.append(f'      memo   {s["memo_count"]} entries today · last: {_clip(s["memo_last"], TASK_WIDTH)}')
    return '\n'.join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    self_id = None
    as_json = False
    include_dead = False
    while argv:
        a = argv.pop(0)
        if a == '--self' and argv:
            self_id = argv.pop(0)
        elif a == '--json':
            as_json = True
        elif a == '--all':
            include_dead = True
    sessions = collect(include_dead=include_dead, self_id=self_id)
    if as_json:
        print(json.dumps(sessions, ensure_ascii=False, indent=1))
    else:
        print(render(sessions))


if __name__ == '__main__':
    main()
