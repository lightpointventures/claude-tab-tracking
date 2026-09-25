#!/usr/bin/env python3
"""
Reads Claude Code transcript JSONL and generates a one-line task summary.

Summarization backends (set CLAUDE_TAB_BACKEND to choose):
  "auto"    — try all backends in order: api → ollama → claude-cli → keywords (default)
  "cli"     — Claude Code CLI only (uses your Max subscription, no API key needed)
  "api"     — Claude API only (requires ANTHROPIC_API_KEY)
  "ollama"  — Ollama only (requires local server on port 11434)
  "keyword" — keyword heuristics only (zero dependencies)

Updates task file with WIP:description or DONE:description.
"""
import json
import logging
import os
import pathlib
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

from claude_cli_common import build_claude_cli_cmd


MEMO_BASE_DIR = os.path.join(str(pathlib.Path.home()), '.claude', 'memos')
MEMO_CONFIG_PATH = os.path.join(MEMO_BASE_DIR, 'config.yaml')
TASKS_DIR = os.path.join(str(pathlib.Path.home()), '.claude', 'session-tasks')
ERROR_LOG = os.path.join(TASKS_DIR, '_errors.log')
ERROR_LOG_MAX_BYTES = 256 * 1024
MAX_TASK_LEN = 60


def log_error(message):
    """Append a timestamped line to the error log. Never raises.

    Hooks run with stdout/stderr discarded, so this file is the only place a
    backend failure becomes visible. The log is truncated when it grows past
    ERROR_LOG_MAX_BYTES.
    """
    try:
        os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
        try:
            if os.path.getsize(ERROR_LOG) > ERROR_LOG_MAX_BYTES:
                os.remove(ERROR_LOG)
        except OSError:
            pass
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


def truncate_task(task, limit=MAX_TASK_LEN):
    """Clamp a task description to *limit* characters with an ellipsis."""
    task = task.strip()
    if len(task) > limit:
        return task[:limit - 3] + '...'
    return task

DEFAULT_CONFIG = {
    'tags': ['决策', '数据', '结论', 'TODO'],
    'min_turns': 3,
    'archive_days': 90,
    'ollama_timeout': 15,
    'recall_token_budget': 8000,
    'memo_merge_window': 300,
    'memo_merge_threshold': 0.6,
    'memo_subagents': True,
    'memory_pointer': True,
}


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_memo_config(config_path=None):
    """Load memo config from YAML file. Returns dict with defaults for missing keys."""
    if config_path is None:
        config_path = MEMO_CONFIG_PATH
    config = dict(DEFAULT_CONFIG)
    config['tags_str'] = ''.join(f'【{t}】' for t in config['tags'])
    if not os.path.exists(config_path):
        return config
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        current_key = None
        tags = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if stripped == 'tags:':
                current_key = 'tags'
                continue
            if current_key == 'tags' and stripped.startswith('- '):
                tags.append(stripped[2:].strip())
                continue
            else:
                current_key = None
            if ':' in stripped:
                key, val = stripped.split(':', 1)
                key, val = key.strip(), val.strip()
                if key == 'min_turns' and val.isdigit():
                    config['min_turns'] = int(val)
                elif key == 'archive_days' and val.isdigit():
                    config['archive_days'] = int(val)
                elif key == 'ollama_timeout' and val.isdigit():
                    config['ollama_timeout'] = int(val)
                elif key == 'recall_token_budget' and val.isdigit():
                    config['recall_token_budget'] = int(val)
                elif key == 'memo_merge_window' and val.isdigit():
                    config['memo_merge_window'] = int(val)
                elif key == 'memo_merge_threshold':
                    try:
                        config['memo_merge_threshold'] = float(val)
                    except ValueError:
                        pass
                elif key == 'memo_subagents':
                    config['memo_subagents'] = val.strip().lower() not in ('false', 'no', '0', 'off')
        if tags:
            config['tags'] = tags
        config['tags_str'] = ''.join(f'【{t}】' for t in config['tags'])
    except Exception:
        pass
    return config


def title_similarity(a: str, b: str) -> float:
    """Word-overlap ratio between two titles (Jaccard on word tokens).

    Splits on whitespace/punctuation AND splits CJK characters individually
    so that mixed ASCII+Chinese strings tokenize correctly.
    """
    def _tokenize(s):
        tokens = set()
        for chunk in re.findall(r'\w+', s.lower()):
            # Split individual CJK characters out of the chunk
            has_cjk = bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf]', chunk))
            if has_cjk:
                # Emit each CJK character separately and any ASCII sub-words
                for ch in re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]|[a-z0-9]+', chunk):
                    tokens.add(ch)
            else:
                tokens.add(chunk)
        return tokens

    words_a = _tokenize(a)
    words_b = _tokenize(b)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def estimate_tokens(text: str) -> int:
    """Rough token estimate for mixed Chinese/English text."""
    if not text:
        return 0
    return int(len(text) / 1.5)


def summarize_memo_content(content: str) -> str:
    """Extract headers and 【结论】lines from memo content for summary mode."""
    if not content:
        return ""
    lines = content.splitlines()
    summary_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('# ') or stripped.startswith('## ') or '【结论】' in stripped:
            summary_lines.append(line)
    return '\n'.join(summary_lines)


# ---------------------------------------------------------------------------
# Shared prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    'You are a concise task tracker. '
    'Based on the full conversation arc — including how the task evolved across multiple exchanges — '
    'summarize what is currently being worked on. '
    'IMPORTANT: When the user message contains ambiguous terms, '
    'use the assistant responses to determine the correct meaning. '
    'Output only the requested format — no explanations, no quotes, no extra punctuation.'
)

TASK_ONLY_TEMPLATE = """根据以下完整对话记录，综合判断当前正在进行的任务。请关注整体目标和对话走向，而不只是最后一条消息。
注意：如果用户用词有歧义，请根据 Claude 的实际回复内容来判断正确含义。

对话记录（含开头和最近内容）：
{conversation}

用一句话描述任务（中文25字以内，英文40字以内）。仅在任务明确完成时加 [完成] 前缀。
任务："""

MEMO_TEMPLATE = """根据以下完整对话记录，综合判断当前正在进行的任务，并提取关键信息。
注意：如果用户用词有歧义，请根据 Claude 的实际回复内容来判断正确含义。

对话记录（含开头和最近内容）：
{conversation}

请按以下格式输出两行：
第一行：用一句话描述任务（中文25字以内，英文40字以内）。仅在任务明确完成时加 [完成] 前缀。
第二行以"备忘："开头：提取对话中的关键信息，用 | 分隔，每条加标签前缀（{tags}）。如果没有值得记录的信息，省略第二行。

任务："""

DEFAULT_TAGS = '【决策】【数据】【结论】【TODO】'


def build_user_prompt(messages, min_turns=3, tags=None):
    """Build the user prompt, choosing task-only or task+memo based on turn count."""
    conversation = build_conversation_snippet(messages)
    if tags is None:
        tags = DEFAULT_TAGS
    if len(messages) < min_turns:
        return TASK_ONLY_TEMPLATE.format(conversation=conversation)
    return MEMO_TEMPLATE.format(conversation=conversation, tags=tags)


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

def extract_text(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get('type') == 'text':
                parts.append(block.get('text', ''))
        return ' '.join(parts).strip()
    return ''


# Text injected by Claude Code itself rather than typed by the user. These
# entries carry no information about the task and would otherwise become the
# "first user message" anchor for the summarizers.
_INJECTED_PREFIXES = (
    '<command-name>', '<command-message>', '<local-command-stdout>',
    '<local-command-caveat>', '<task-notification>', '<system-reminder>',
    '<ide_selection>', '<ide_opened_file>', '[Request interrupted',
)
_SYSTEM_REMINDER_RE = re.compile(r'<system-reminder>.*?</system-reminder>', re.DOTALL)


def _is_injected_entry(obj):
    """True for transcript entries that were not authored by the user or model."""
    if obj.get('isMeta') or obj.get('isSidechain') or obj.get('isCompactSummary'):
        return True
    if obj.get('parent_tool_use_id'):
        return True
    return False


def clean_user_text(content):
    """Strip system-reminder blocks; return '' for injected messages."""
    content = _SYSTEM_REMINDER_RE.sub('', content).strip()
    if not content:
        return ''
    if content.startswith(_INJECTED_PREFIXES):
        return ''
    return content


def parse_transcript(path):
    """Parse transcript JSONL. Returns list of {'role', 'content'} dicts."""
    messages = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                role = content = None
                if _is_injected_entry(obj):
                    continue
                if obj.get('type') in ('user', 'assistant'):
                    role = obj['type']
                    content = extract_text(obj.get('message', obj).get('content', ''))
                elif obj.get('role') in ('user', 'assistant'):
                    role = obj['role']
                    content = extract_text(obj.get('content', ''))

                if not role or not content:
                    continue
                if role == 'user':
                    content = clean_user_text(content)
                    if not content or content.startswith('/') or len(content) <= 3:
                        continue

                messages.append({'role': role, 'content': content})
    except Exception:
        pass
    return messages


def build_conversation_snippet(messages, max_exchanges=10):
    """
    Build a snippet that includes:
    - The first exchange (captures original intent)
    - The most recent exchanges (captures current state)
    This gives the LLM context on both where the task started and where it is now.
    """
    lines = []
    # Always include the first exchange to anchor the original task intent
    first_two = messages[:2]
    recent = messages[-(max_exchanges * 2):]
    # Merge, dedup by position
    combined_indices = set()
    combined = []
    for m in first_two + recent:
        idx = id(m)
        if idx not in combined_indices:
            combined_indices.add(idx)
            combined.append(m)
    # If first exchange is already in recent window, no separator needed
    show_separator = len(messages) > max_exchanges * 2 + 2
    for i, m in enumerate(combined):
        label = '用户' if m['role'] == 'user' else 'Claude'
        if show_separator and i == len(first_two):
            lines.append('...')
        lines.append(f"{label}: {m['content'][:300].replace(chr(10), ' ')}")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Response parsing (shared by all LLM backends)
# ---------------------------------------------------------------------------

def parse_llm_response(response):
    """Extract (task_description, is_done, memo) from LLM output."""
    response = response.strip()
    lines = response.splitlines()

    # Extract memo line (备忘： or 备忘:)
    memo = ''
    task_lines = []
    for line in lines:
        m = re.match(r'^备忘[：:](.*)$', line.strip())
        if m:
            memo = m.group(1).strip()
        else:
            task_lines.append(line)

    # Reconstruct task text (first non-memo line)
    task_text = task_lines[0].strip() if task_lines else ''

    # Strip 任务： or 任务: prefix from task line
    task_text = re.sub(r'^任务[：:]\s*', '', task_text)

    is_done = bool(re.match(
        r'^(\[完成\]|完成\s|完成：|completed[: ]|\[done\])',
        task_text, re.IGNORECASE
    ))
    task = re.sub(
        r'^(\[完成\]\s*|完成\s+|完成：\s*|\[done\]\s*|completed:\s*)',
        '', task_text, flags=re.IGNORECASE
    ).strip()
    return truncate_task(task), is_done, memo


# ---------------------------------------------------------------------------
# Backend 0: Claude Code CLI (uses Max subscription, no API key needed)
# ---------------------------------------------------------------------------

CLAUDE_CLI_TIMEOUT = 60


def claude_cli_summarize(messages, task_file_path=None, memo_base_dir=None, project_name=None,
                         min_turns=3, tags=None, fallback=None):
    """Call claude CLI in print mode, asynchronously.

    Because ``claude -p`` has ~30s startup overhead, this backend spawns the
    process in the background and writes the result to *task_file_path* when
    ready.  When *task_file_path* is provided (the normal path from main()),
    the function launches the helper and returns ``None`` so the caller skips
    synchronous writing.  When *task_file_path* is ``None`` (unit tests), it
    falls back to a blocking call.
    """
    user_content = build_user_prompt(messages, min_turns=min_turns, tags=tags)
    prompt = f"{SYSTEM_PROMPT}\n\n{user_content}"

    if task_file_path is None:
        # Synchronous path (for tests / direct invocation)
        result = subprocess.run(
            build_claude_cli_cmd(),
            input=prompt,
            capture_output=True, text=True,
            timeout=CLAUDE_CLI_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(f'claude CLI exited with {result.returncode}')
        text = result.stdout.strip()
        if not text:
            raise ValueError('empty response from claude CLI')
        return parse_llm_response(text)

    # Async path — fire-and-forget background process
    _launch_cli_background(prompt, task_file_path, memo_base_dir, project_name, fallback=fallback)
    return None  # signal: handled async, caller should not write


_CLI_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cli_background.py')


def generation_path(task_file_path):
    return task_file_path + '.gen'


def write_generation(task_file_path):
    """Record a new generation token for *task_file_path* and return it.

    Every Stop hook launches a fresh background helper. When the user sends
    several messages quickly, older helpers may finish after newer ones; the
    token lets a helper detect that it has been superseded and skip its write.
    """
    token = str(time.time_ns())
    try:
        with open(generation_path(task_file_path), 'w', encoding='utf-8') as f:
            f.write(token)
    except OSError:
        pass
    return token


def read_generation(task_file_path):
    try:
        with open(generation_path(task_file_path), 'r', encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


def _launch_cli_background(prompt, task_file_path, memo_base_dir=None, project_name=None,
                           fallback=None):
    """Spawn a detached process that calls claude CLI and writes the result.

    *fallback* is an optional ``(task, is_done)`` pair, normally from
    keyword_fallback(), written by the helper if the CLI call fails so the
    statusline never stays stale because of a backend error.
    """
    import tempfile
    job = {
        'prompt': prompt,
        'task_file': task_file_path,
        'generation': write_generation(task_file_path),
        'memo_base_dir': memo_base_dir,
        'project_name': project_name,
        'fallback_task': fallback[0] if fallback else None,
        'fallback_done': bool(fallback[1]) if fallback else False,
    }
    fd, job_path = tempfile.mkstemp(prefix='claude_tab_', suffix='.json')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(job, f, ensure_ascii=False)

    args = [sys.executable, _CLI_HELPER, job_path]

    env = os.environ.copy()
    env['CLAUDE_TAB_SKIP_HOOK'] = '1'
    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# Backend 1: Claude API
# ---------------------------------------------------------------------------

CLAUDE_API_URL = 'https://api.anthropic.com/v1/messages'
CLAUDE_MODEL = 'claude-haiku-4-5-20251001'
CLAUDE_TIMEOUT = 10


def claude_summarize(messages, min_turns=3, tags=None):
    """Call Claude Haiku via Anthropic API. Raises if ANTHROPIC_API_KEY not set."""
    api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not api_key:
        raise EnvironmentError('ANTHROPIC_API_KEY not set')

    user_content = build_user_prompt(messages, min_turns=min_turns, tags=tags)

    payload = json.dumps({
        'model': CLAUDE_MODEL,
        'max_tokens': 300,
        'system': SYSTEM_PROMPT,
        'messages': [{'role': 'user', 'content': user_content}],
    }).encode()

    req = urllib.request.Request(
        CLAUDE_API_URL,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=CLAUDE_TIMEOUT) as resp:
        result = json.loads(resp.read())

    text = result['content'][0]['text']
    return parse_llm_response(text)


# ---------------------------------------------------------------------------
# Backend 2: Ollama
# ---------------------------------------------------------------------------

OLLAMA_URL = 'http://localhost:11434/api/chat'
OLLAMA_TIMEOUT = 15


def _get_ollama_model():
    """Pick the best available small model from the local Ollama server."""
    req = urllib.request.Request('http://localhost:11434/api/tags')
    with urllib.request.urlopen(req, timeout=2) as resp:
        data = json.loads(resp.read())
    models = [m['name'] for m in data.get('models', [])]
    if not models:
        raise RuntimeError('no Ollama models available')
    preferred = [
        'qwen3.5:4b', 'qwen2.5:4b', 'qwen3:4b',
        'llama3.2:3b', 'llama3.2:latest', 'llama3:latest',
    ]
    for p in preferred:
        if p in models:
            return p
    return models[0]  # fall back to whatever is installed


def ollama_summarize(messages, min_turns=3, tags=None, timeout=None):
    """Call local Ollama. Raises if Ollama is not running or has no models."""
    if timeout is None:
        timeout = OLLAMA_TIMEOUT
    model = _get_ollama_model()
    user_content = build_user_prompt(messages, min_turns=min_turns, tags=tags)

    payload = json.dumps({
        'model': model,
        'stream': False,
        'think': False,          # disables extended thinking on qwen3.x
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user',   'content': user_content},
        ],
        'options': {'temperature': 0.1, 'num_predict': 300},
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read())

    text = result.get('message', {}).get('content', '').strip()
    if not text:
        raise ValueError('empty response from Ollama')
    return parse_llm_response(text)


# ---------------------------------------------------------------------------
# Backend 3: Keyword fallback (zero dependencies)
# ---------------------------------------------------------------------------

COMPLETION_KEYWORDS = [
    'complete', 'completed', 'done', 'finished', 'fixed', 'implemented',
    'deployed', 'resolved', 'merged', 'all tests pass', 'tests pass',
    'successfully', 'is working', 'are working', 'is ready', 'are ready',
    '完成', '完毕', '搞定', '结束', '修复了', '部署了', '通过了', '已实现',
]


def detect_task_boundary(messages):
    """Find the start of the current task after the last completion signal.

    Returns the index of the first user message after the last detected
    completion, or 0 if no boundary found.
    """
    boundary = 0
    for i, m in enumerate(messages):
        if m['role'] != 'assistant':
            continue
        text = m['content'].lower()
        hits = sum(1 for kw in COMPLETION_KEYWORDS if kw in text)
        if hits >= 3:
            for j in range(i + 1, len(messages)):
                if messages[j]['role'] == 'user':
                    boundary = j
                    break
    return boundary


def keyword_fallback(messages, min_turns=3, tags=None):
    """Zero-dependency summary. Extra keyword arguments match the LLM backends' signature."""
    user_msgs = [m['content'] for m in messages if m['role'] == 'user']
    asst_msgs = [m['content'] for m in messages if m['role'] == 'assistant']
    if not user_msgs:
        return None, False, ''
    # Use first user message as task anchor (original intent), truncated
    task_desc = truncate_task(re.sub(r'\s+', ' ', user_msgs[0]))
    # Check the last 3 assistant messages for completion signals
    recent_asst = [m.lower() for m in asst_msgs[-3:]]
    kw_hits = sum(1 for msg in recent_asst for kw in COMPLETION_KEYWORDS if kw in msg)
    # Require 3+ keyword hits across recent messages to reduce false positives
    is_done = kw_hits >= 3
    return task_desc, is_done, ''


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------

BACKENDS = {
    'cli': claude_cli_summarize,
    'api': claude_summarize,
    'ollama': ollama_summarize,
    'keyword': keyword_fallback,
}

AUTO_ORDER = ['api', 'ollama', 'cli', 'keyword']


def _get_backend_chain():
    """Return list of backend functions based on CLAUDE_TAB_BACKEND env var."""
    choice = os.environ.get('CLAUDE_TAB_BACKEND', 'auto').strip().lower()
    if choice == 'auto':
        return [BACKENDS[k] for k in AUTO_ORDER]
    if choice in BACKENDS:
        return [BACKENDS[choice]]
    return [BACKENDS[k] for k in AUTO_ORDER]


# ---------------------------------------------------------------------------
# Secret redaction (applied to everything written to a memo file)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    re.compile(r'sk-ant-[A-Za-z0-9_-]{8,}'),
    re.compile(r'\bsk-[A-Za-z0-9]{20,}'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'\bxox[abpr]-[A-Za-z0-9-]{10,}'),
    re.compile(r'\bAIza[0-9A-Za-z_-]{30,}'),
    re.compile(r'\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'),  # JWT
    re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._-]{16,}'),
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)'),
]
_KV_SECRET_RE = re.compile(
    r'(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)'
    r'(\s*[:=]\s*)([\'"]?)([^\s\'"]{6,})'
)


def redact_secrets(text):
    """Replace credential-looking substrings with [REDACTED]. Never raises."""
    if not text:
        return text
    try:
        for pat in _SECRET_PATTERNS:
            text = pat.sub('[REDACTED]', text)
        text = _KV_SECRET_RE.sub(lambda m: f'{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED]', text)
    except Exception:
        pass
    return text


# ---------------------------------------------------------------------------
# Memo file helpers
# ---------------------------------------------------------------------------

def sanitize_project_name(name):
    """Sanitize project name for filesystem use."""
    name = re.sub(r'[^a-zA-Z0-9_-]', '-', name).lower()
    return name[:50]


def resolve_project_name(cwd):
    """Determine project name from working directory."""
    home = str(pathlib.Path.home())
    real_cwd = os.path.realpath(cwd)
    if real_cwd == os.path.realpath(home) or real_cwd.startswith(('/tmp', '/private/tmp', '/var')):
        return 'general'
    try:
        result = subprocess.run(
            ['git', '-C', cwd, 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return sanitize_project_name(os.path.basename(result.stdout.strip()))
    except Exception:
        pass
    return sanitize_project_name(os.path.basename(cwd))


def _parse_last_entry(memo_file):
    """Parse the last entry from a memo file. Returns (header_line_idx, time_str, title, bullets, all_lines) or None."""
    if not os.path.exists(memo_file):
        return None
    with open(memo_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    last_header_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().startswith('## '):
            last_header_idx = i
            break
    if last_header_idx is None:
        return None
    header = lines[last_header_idx].strip()
    m = re.match(r'^##\s+(\d{1,2}:\d{2})\s*\|\s*(.*)$', header)
    if not m:
        return None
    time_str = m.group(1)
    title = m.group(2).strip()
    bullets = []
    for line in lines[last_header_idx + 1:]:
        stripped = line.strip()
        if stripped.startswith('- '):
            bullets.append(stripped)
    return last_header_idx, time_str, title, bullets, lines


def write_memo(memo_content, task_desc, project_name, memo_base_dir=None, merge_config=None):
    """Append a memo entry to the project's daily memo file.

    If the last entry is similar and recent, merges instead of appending.
    Uses fcntl file locking (Unix) to prevent interleaved writes.
    """
    if not memo_content:
        return
    if memo_base_dir is None:
        memo_base_dir = MEMO_BASE_DIR
    if merge_config is None:
        merge_config = DEFAULT_CONFIG

    merge_window = merge_config.get('memo_merge_window', 300)
    merge_threshold = merge_config.get('memo_merge_threshold', 0.6)

    memo_content = redact_secrets(memo_content)
    task_desc = redact_secrets(task_desc)

    today = datetime.now().strftime('%Y-%m-%d')
    time_str = datetime.now().strftime('%H:%M')
    project_dir = os.path.join(memo_base_dir, project_name)
    os.makedirs(project_dir, exist_ok=True)
    memo_file = os.path.join(project_dir, f'{today}.md')

    new_items = [item.strip() for item in memo_content.split('|') if item.strip()]
    new_bullets = [f'- {item}' for item in new_items]

    def _do_write():
        merged = False
        if merge_window > 0:
            parsed = _parse_last_entry(memo_file)
            if parsed is not None:
                header_idx, last_time, last_title, last_bullets, all_lines = parsed
                # Check time window
                try:
                    now_minutes = int(time_str.split(':')[0]) * 60 + int(time_str.split(':')[1])
                    last_minutes = int(last_time.split(':')[0]) * 60 + int(last_time.split(':')[1])
                    delta_seconds = abs(now_minutes - last_minutes) * 60
                except (ValueError, IndexError):
                    delta_seconds = 9999
                # Check similarity
                if delta_seconds <= merge_window and title_similarity(last_title, task_desc) >= merge_threshold:
                    # Merge: replace last entry with combined content
                    existing_bullet_texts = set(last_bullets)
                    merged_bullets = list(last_bullets)
                    for b in new_bullets:
                        if b not in existing_bullet_texts:
                            merged_bullets.append(b)
                    # Rebuild file: everything before last entry + merged entry
                    new_header = f'## {time_str} | {task_desc}\n'
                    with open(memo_file, 'w', encoding='utf-8') as f:
                        for line in all_lines[:header_idx]:
                            f.write(line)
                        f.write(f'\n{new_header}')
                        for b in merged_bullets:
                            f.write(f'{b}\n')
                    merged = True

        if not merged:
            entry_lines = [f'\n## {time_str} | {task_desc}']
            for b in new_bullets:
                entry_lines.append(b)
            entry_lines.append('')
            if not os.path.exists(memo_file):
                with open(memo_file, 'w', encoding='utf-8') as f:
                    f.write(f'# {today}\n')
                    f.write('\n'.join(entry_lines))
            else:
                with open(memo_file, 'a', encoding='utf-8') as f:
                    f.write('\n'.join(entry_lines))

    if HAS_FCNTL:
        lock_path = memo_file + '.lock'
        with open(lock_path, 'w') as lock_f:
            # Blocking lock: writes are tiny, and skipping would silently drop a memo.
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                _do_write()
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
    else:
        _do_write()


# ---------------------------------------------------------------------------
# Archival helpers
# ---------------------------------------------------------------------------

def archive_old_memos(memo_base_dir=None, archive_days=90):
    """Move memo files older than archive_days to _archive/ directory."""
    if memo_base_dir is None:
        memo_base_dir = MEMO_BASE_DIR
    cutoff = time.time() - (archive_days * 86400)
    archive_base = os.path.join(memo_base_dir, '_archive')
    for entry in os.listdir(memo_base_dir):
        proj_dir = os.path.join(memo_base_dir, entry)
        if not os.path.isdir(proj_dir) or entry.startswith('_') or entry == 'config.yaml':
            continue
        try:
            fnames = os.listdir(proj_dir)
        except OSError:
            logging.exception("Cannot list memo directory %s", proj_dir)
            continue
        for fname in fnames:
            if not fname.endswith('.md'):
                continue
            fpath = os.path.join(proj_dir, fname)
            if os.path.getmtime(fpath) < cutoff:
                dest_dir = os.path.join(archive_base, entry)
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(fpath, os.path.join(dest_dir, fname))


# ---------------------------------------------------------------------------
# Multi-layer PREV history helpers
# ---------------------------------------------------------------------------

MAX_PREV = 3


def read_prev_lines(task_file_path):
    """Read existing PREV lines from a task file.

    Handles both old format (``PREV:task``) and new format (``PREV:N:task``).
    Returns a list of normalised ``PREV:N:task`` strings, sorted by N.
    """
    if not os.path.exists(task_file_path):
        return []
    prev = {}
    with open(task_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line.startswith('PREV:'):
                continue
            rest = line[5:]  # after "PREV:"
            # New format: "PREV:N:task"
            m = re.match(r'^(\d+):(.*)$', rest)
            if m:
                n = int(m.group(1))
                prev[n] = m.group(2)
            else:
                # Old format: "PREV:task" — treat as PREV:1
                prev.setdefault(1, rest)
    return [f"PREV:{n}:{prev[n]}" for n in sorted(prev) if n <= MAX_PREV]


def shift_prev_lines(current_done_desc, task_file_path):
    """Shift existing PREVs down by one and insert *current_done_desc* as PREV:1.

    Returns a list of ``PREV:N:task`` strings (max MAX_PREV).
    """
    existing = read_prev_lines(task_file_path)
    new_prevs = [f"PREV:1:{current_done_desc}"]
    for entry in existing:
        m = re.match(r'^PREV:(\d+):(.*)$', entry)
        if m:
            n = int(m.group(1)) + 1
            if n <= MAX_PREV:
                new_prevs.append(f"PREV:{n}:{m.group(2)}")
    return new_prevs


# ---------------------------------------------------------------------------
# Main — try each backend in priority order
# ---------------------------------------------------------------------------

def main():
    # Prevent recursion when the Stop hook fires inside a child `claude -p`
    # session. Must live in main(), not at import time: cli_background.py is
    # launched with this env var set and imports this module.
    if os.environ.get('CLAUDE_TAB_SKIP_HOOK') == '1':
        sys.exit(0)
    if len(sys.argv) != 3:
        sys.exit(0)

    transcript_path, task_file_path = sys.argv[1], sys.argv[2]
    messages = parse_transcript(transcript_path)
    if not messages:
        sys.exit(0)

    memo_config = load_memo_config()

    # Probabilistic archival check (1 in 50 calls)
    if random.randint(1, 50) == 1:
        try:
            archive_old_memos(archive_days=memo_config['archive_days'])
        except Exception:
            pass

    boundary = detect_task_boundary(messages)
    if boundary > 0:
        messages = messages[boundary:]
    if not messages:
        sys.exit(0)

    task_desc = is_done = None
    memo_content = ''
    for backend in _get_backend_chain():
        try:
            if backend is claude_cli_summarize:
                cwd = os.environ.get('PWD', os.getcwd())
                project = resolve_project_name(cwd)
                kw_task, kw_done, _ = keyword_fallback(messages)
                result = backend(
                    messages,
                    task_file_path=task_file_path,
                    memo_base_dir=MEMO_BASE_DIR,
                    project_name=project,
                    min_turns=memo_config['min_turns'],
                    tags=memo_config['tags_str'],
                    fallback=(kw_task, kw_done) if kw_task else None,
                )
                if result is None:
                    # CLI backend launched async — it will write the file itself
                    sys.exit(0)
                task_desc, is_done, memo_content = result
            elif backend is ollama_summarize:
                task_desc, is_done, memo_content = backend(
                    messages,
                    min_turns=memo_config['min_turns'],
                    tags=memo_config['tags_str'],
                    timeout=memo_config.get('ollama_timeout', OLLAMA_TIMEOUT),
                )
            else:
                task_desc, is_done, memo_content = backend(
                    messages,
                    min_turns=memo_config['min_turns'],
                    tags=memo_config['tags_str'],
                )
            if task_desc:
                break
        except OSError:
            # Expected: no API key (EnvironmentError) or Ollama not listening
            # (URLError / ConnectionRefusedError). Fall through to the next backend.
            continue
        except Exception as exc:
            log_error(f"backend {backend.__name__} failed: {type(exc).__name__}: {exc}")
            continue

    if not task_desc:
        sys.exit(0)

    prefix = 'DONE' if is_done else 'WIP'

    # Read existing PREV lines before overwriting (up to 3)
    prev_lines = read_prev_lines(task_file_path)

    dirpart = os.path.dirname(task_file_path)
    if dirpart:
        os.makedirs(dirpart, exist_ok=True)
    with open(task_file_path, 'w', encoding='utf-8') as f:
        f.write(f"{prefix}:{task_desc}\n")
        for pl in prev_lines:
            f.write(f"{pl}\n")

    if memo_content:
        cwd = os.environ.get('PWD', os.getcwd())
        project = resolve_project_name(cwd)
        write_memo(memo_content, task_desc, project, merge_config=memo_config)


if __name__ == '__main__':
    main()
