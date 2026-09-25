#!/usr/bin/env python3
"""Budgeted, two-stage recall over the daily memo files.

Subcommands:
    index  [--project P|all] [--days N]                 one line per entry, newest first
    show   ID[,ID...]                                    full text of the given entries
    auto   [--project P|all] [--days N] [--budget T]     pick the most valuable entries
                                                         that fit the token budget, then
                                                         an index of the rest
    add    [--project P] [--task TITLE] TEXT             file a manual note (weight 1.0)

Entry ids look like  general/2026-09-25#3  (project / day / 1-based entry).

Scoring, per bullet, then summed per entry:
    weight(tag) × 0.5 ** (age_days / half_life(tag)) × source × status
    tag weights   决策 1.0  TODO 1.0  手记 1.0  结论 0.7  数据 0.4  子代理 0.3  other 0.5
    half-lives    决策 90d  结论 30d  数据 14d  子代理 7d  手记 90d  TODO: none while open
    source        bullets written by hand (【手记】) 1.0, everything the hooks wrote 0.5
    status        a 决策 that a later, similar 决策 replaced: 0.35; a closed TODO: 0.1
"""
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dynamic_task_update import (  # noqa: E402
    MEMO_BASE_DIR,
    estimate_tokens,
    load_memo_config,
    resolve_project_name,
    title_similarity,
    write_memo,
)

TAG_WEIGHT = {'决策': 1.0, 'TODO': 1.0, '手记': 1.0, '结论': 0.7, '数据': 0.4, '子代理': 0.3}
HALF_LIFE_DAYS = {'决策': 90, '结论': 30, '数据': 14, '子代理': 7, '手记': 90}
DEFAULT_WEIGHT = 0.5
AUTO_SOURCE = 0.5
SUPERSEDED = 0.35
CLOSED_TODO = 0.1
SUPERSEDE_SIMILARITY = 0.6
INDEX_CAP = 30

_TAG_RE = re.compile(r'^-\s*【([^】]+)】\s*(.*)$')
_HEADER_RE = re.compile(r'^##\s+(\d{1,2}:\d{2})\s*\|\s*(.*)$')
_CLOSED_RE = re.compile(r'(\[x\]|✓|✔|已完成|已关闭|done\b)', re.IGNORECASE)


class Bullet:
    __slots__ = ('tag', 'text', 'raw', 'superseded_by')

    def __init__(self, raw):
        self.raw = raw.rstrip('\n')
        m = _TAG_RE.match(self.raw.strip())
        self.tag = m.group(1) if m else ''
        self.text = (m.group(2) if m else self.raw.lstrip('- ').strip()).strip()
        self.superseded_by = None


class Entry:
    def __init__(self, project, day, n, time_str, title):
        self.project, self.day, self.n = project, day, n
        self.time_str, self.title = time_str, title
        self.bullets = []
        self.score = 0.0

    @property
    def id(self):
        return f'{self.project}/{self.day}#{self.n}'

    @property
    def when(self):
        try:
            return datetime.strptime(f'{self.day} {self.time_str}', '%Y-%m-%d %H:%M')
        except ValueError:
            return datetime.strptime(self.day, '%Y-%m-%d')

    def text(self):
        lines = [f'## {self.time_str} | {self.title}']
        lines += [b.raw for b in self.bullets]
        return '\n'.join(lines)

    def tokens(self):
        return estimate_tokens(self.text())

    def tag_counts(self):
        counts = {}
        for b in self.bullets:
            counts[b.tag or '其他'] = counts.get(b.tag or '其他', 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def parse_memo_file(path, project, day):
    entries = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except OSError:
        return entries
    current = None
    for line in lines:
        m = _HEADER_RE.match(line.strip())
        if m:
            current = Entry(project, day, len(entries) + 1, m.group(1), m.group(2).strip())
            entries.append(current)
        elif current is not None and line.strip().startswith('- '):
            current.bullets.append(Bullet(line))
    return entries


def load_entries(memo_base_dir=None, project=None, days=None, now=None):
    """All entries, newest first. project=None means every project."""
    memo_base_dir = memo_base_dir or MEMO_BASE_DIR
    now = now or datetime.now()
    entries = []
    if not os.path.isdir(memo_base_dir):
        return entries
    for proj in sorted(os.listdir(memo_base_dir)):
        if proj.startswith('_') or proj == 'config.yaml':
            continue
        if project and proj != project:
            continue
        pdir = os.path.join(memo_base_dir, proj)
        if not os.path.isdir(pdir):
            continue
        for fname in sorted(os.listdir(pdir)):
            if not re.match(r'^\d{4}-\d{2}-\d{2}\.md$', fname):
                continue
            day = fname[:-3]
            if days is not None:
                try:
                    age = (now - datetime.strptime(day, '%Y-%m-%d')).days
                except ValueError:
                    continue
                if age > days:
                    continue
            entries.extend(parse_memo_file(os.path.join(pdir, fname), proj, day))
    mark_superseded(entries)
    for e in entries:
        e.score = score_entry(e, now)
    entries.sort(key=lambda e: e.when, reverse=True)
    return entries


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def mark_superseded(entries, threshold=SUPERSEDE_SIMILARITY):
    """A 决策 bullet is superseded when a later 决策 in the same project is similar."""
    by_project = {}
    for e in sorted(entries, key=lambda e: e.when):
        by_project.setdefault(e.project, []).append(e)
    for plist in by_project.values():
        decisions = [(e, b) for e in plist for b in e.bullets if b.tag == '决策']
        for i, (e_old, b_old) in enumerate(decisions):
            for e_new, b_new in decisions[i + 1:]:
                if e_new.when <= e_old.when:
                    continue
                if title_similarity(b_old.text, b_new.text) >= threshold:
                    b_old.superseded_by = e_new.id
                    break


def score_bullet(bullet, entry_when, now):
    weight = TAG_WEIGHT.get(bullet.tag, DEFAULT_WEIGHT)
    age_days = max(0.0, (now - entry_when).total_seconds() / 86400.0)
    half = HALF_LIFE_DAYS.get(bullet.tag)
    decay = 0.5 ** (age_days / half) if half else 1.0
    source = 1.0 if bullet.tag == '手记' else AUTO_SOURCE
    status = 1.0
    if bullet.superseded_by:
        status = SUPERSEDED
    if bullet.tag == 'TODO' and _CLOSED_RE.search(bullet.text):
        status = CLOSED_TODO
    return weight * decay * source * status


def score_entry(entry, now=None):
    now = now or datetime.now()
    return round(sum(score_bullet(b, entry.when, now) for b in entry.bullets), 4)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def select_within_budget(entries, budget):
    """Greedy by score; returns (chosen newest-first, rest newest-first)."""
    if not budget or budget <= 0:
        return list(entries), []
    chosen, rest, used = [], [], 0
    for e in sorted(entries, key=lambda e: (e.score, e.when), reverse=True):
        t = e.tokens()
        if used + t <= budget:
            chosen.append(e)
            used += t
        else:
            rest.append(e)
    chosen.sort(key=lambda e: e.when, reverse=True)
    rest.sort(key=lambda e: e.when, reverse=True)
    return chosen, rest


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def index_line(e):
    tags = ' '.join(f'{k}×{v}' for k, v in sorted(e.tag_counts().items(), key=lambda kv: -kv[1]))
    flags = []
    sup = sum(1 for b in e.bullets if b.superseded_by)
    if sup:
        flags.append(f'{sup} superseded')
    open_todo = sum(1 for b in e.bullets if b.tag == 'TODO' and not _CLOSED_RE.search(b.text))
    if open_todo:
        flags.append(f'{open_todo} open TODO')
    flag_str = f'  [{", ".join(flags)}]' if flags else ''
    return f'{e.id:<34} {e.time_str} | {e.title[:48]:<48} {tags} ~{e.tokens()}tok score {e.score:.2f}{flag_str}'


def render_index(entries):
    if not entries:
        return 'No memo entries found.'
    return '\n'.join(index_line(e) for e in entries)


def render_show(entries):
    blocks = []
    for e in entries:
        block = [f'# {e.id}', e.text()]
        for b in e.bullets:
            if b.superseded_by:
                block.append(f'  (superseded by {b.superseded_by}: {b.text[:60]})')
        blocks.append('\n'.join(block))
    return '\n\n'.join(blocks) if blocks else 'No matching entries.'


def render_auto(entries, budget):
    chosen, rest = select_within_budget(entries, budget)
    total = sum(e.tokens() for e in entries)
    used = sum(e.tokens() for e in chosen)
    out = [f'{len(entries)} entries, ~{total} tokens total; loaded {len(chosen)} (~{used} tokens, budget {budget or "unlimited"})']
    for e in chosen:
        out.append('')
        out.append(f'# {e.id}')
        out.append(e.text())
    if rest:
        out.append('')
        out.append(f'Not loaded ({len(rest)}); fetch with: memo_recall.py show ID[,ID]')
        for e in rest[:INDEX_CAP]:
            out.append('  ' + index_line(e))
        if len(rest) > INDEX_CAP:
            out.append(f'  … {len(rest) - INDEX_CAP} more; run `index` to list them')
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse(argv):
    opts = {'project': None, 'days': None, 'budget': None, 'task': None, 'positional': []}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--project' and i + 1 < len(argv):
            opts['project'] = argv[i + 1]; i += 2
        elif a == '--days' and i + 1 < len(argv):
            opts['days'] = int(argv[i + 1]); i += 2
        elif a == '--budget' and i + 1 < len(argv):
            opts['budget'] = int(argv[i + 1]); i += 2
        elif a == '--task' and i + 1 < len(argv):
            opts['task'] = argv[i + 1]; i += 2
        elif a == '--full':
            opts['budget'] = 0; i += 1
        else:
            opts['positional'].append(a); i += 1
    return opts


def _default_project(explicit):
    if explicit == 'all':
        return None
    if explicit:
        return explicit
    return resolve_project_name(os.environ.get('PWD', os.getcwd()))


def main(argv=None, memo_base_dir=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.strip())
        return 0
    cmd, opts = argv[0], _parse(argv[1:])
    config = load_memo_config()
    memo_base_dir = memo_base_dir or MEMO_BASE_DIR

    if cmd == 'index':
        days = opts['days'] if opts['days'] is not None else 14
        print(render_index(load_entries(memo_base_dir, _default_project(opts['project']), days)))
    elif cmd == 'show':
        wanted = set(x.strip() for x in ','.join(opts['positional']).split(',') if x.strip())
        entries = [e for e in load_entries(memo_base_dir, None, None) if e.id in wanted]
        print(render_show(entries))
    elif cmd == 'auto':
        days = opts['days'] if opts['days'] is not None else 14
        budget = opts['budget'] if opts['budget'] is not None else config.get('recall_token_budget', 8000)
        print(render_auto(load_entries(memo_base_dir, _default_project(opts['project']), days), budget))
    elif cmd == 'add':
        text = ' '.join(opts['positional']).strip()
        if not text:
            print('Nothing to add.', file=sys.stderr)
            return 1
        project = _default_project(opts['project']) or 'general'
        write_memo(f'【手记】{text}', opts['task'] or '手记', project, memo_base_dir, merge_config=config)
        print(f'Added to {project}: 【手记】{text}')
    else:
        print(f'Unknown command: {cmd}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
