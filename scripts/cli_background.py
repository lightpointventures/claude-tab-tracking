#!/usr/bin/env python3
"""Background helper: calls ``claude -p`` and writes the task summary to a file.

Invoked by dynamic_task_update.py as a detached process so the Stop hook
returns immediately while the (slow) CLI call runs in the background.

Usage: cli_background.py <job.json>

The job file (deleted after reading) contains:
    prompt          full prompt for the summarizer
    task_file       session task file to update
    generation      token written by the launcher; the helper only writes if
                    it still matches, otherwise a newer helper has taken over
    memo_base_dir   optional, together with project_name enables memo writing
    project_name    optional
    fallback_task   optional keyword-derived description used if the CLI fails
    fallback_done   completion flag for the fallback description
"""
import json
import os
import subprocess
import sys

from claude_cli_common import build_claude_cli_cmd, looks_like_cli_error
from dynamic_task_update import (
    load_memo_config,
    log_error,
    parse_llm_response,
    read_generation,
    read_prev_lines,
    write_memo,
)

TIMEOUT = 90


def _load_job(job_path):
    try:
        with open(job_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as exc:
        log_error(f"cli helper: cannot read job file {job_path}: {exc}")
        return None
    finally:
        try:
            os.unlink(job_path)
        except OSError:
            pass


def _run_claude(prompt):
    """Return CLI stdout, or None on any failure (logged)."""
    cmd = build_claude_cli_cmd()
    try:
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        log_error(f"cli helper: claude -p timed out after {TIMEOUT}s")
        return None
    except FileNotFoundError:
        log_error("cli helper: `claude` executable not found on PATH")
        return None
    except Exception as exc:
        log_error(f"cli helper: {type(exc).__name__}: {exc}")
        return None
    if result.returncode != 0:
        log_error(f"cli helper: claude -p exited {result.returncode}: {result.stderr.strip()[:300]}")
        return None
    text = result.stdout.strip()
    if not text:
        log_error("cli helper: empty response from claude -p")
        return None
    if looks_like_cli_error(text):
        log_error(f"cli helper: claude -p returned an error banner: {text[:120]!r}")
        return None
    return text


def _superseded(task_file, generation):
    """True if a newer helper was launched for this task file, or the user pinned it."""
    if generation and read_generation(task_file) != generation:
        return True
    try:
        with open(task_file, 'r', encoding='utf-8') as f:
            return f.readline().startswith('MANUAL:')
    except OSError:
        return False


def write_task_file(task_file, task, is_done, generation=None):
    """Write ``WIP:``/``DONE:`` line plus preserved PREV history under a lock."""
    import fcntl

    dirpart = os.path.dirname(task_file)
    if dirpart:
        os.makedirs(dirpart, exist_ok=True)

    prefix = 'DONE' if is_done else 'WIP'
    lock_path = task_file + '.lock'
    with open(lock_path, 'w') as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            if _superseded(task_file, generation):
                return False
            prev_lines = read_prev_lines(task_file)
            with open(task_file, 'w', encoding='utf-8') as f:
                f.write(f"{prefix}:{task}\n")
                for pl in prev_lines:
                    f.write(f"{pl}\n")
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)
    return True


def main():
    if len(sys.argv) != 2:
        sys.exit(1)

    job = _load_job(sys.argv[1])
    if not job or not job.get('prompt') or not job.get('task_file'):
        sys.exit(1)

    task_file = job['task_file']
    generation = job.get('generation') or None

    text = _run_claude(job['prompt'])
    task, is_done, memo = ('', False, '')
    if text:
        task, is_done, memo = parse_llm_response(text)
        if not task:
            log_error(f"cli helper: could not parse response: {text[:120]!r}")

    if not task:
        task = job.get('fallback_task') or ''
        is_done = bool(job.get('fallback_done'))
        memo = ''
        if not task:
            sys.exit(1)

    if not write_task_file(task_file, task, is_done, generation):
        sys.exit(0)  # superseded or manually pinned; nothing to do

    memo_base_dir = job.get('memo_base_dir')
    project_name = job.get('project_name')
    if memo and memo_base_dir and project_name:
        write_memo(memo, task, project_name, memo_base_dir, merge_config=load_memo_config())


if __name__ == '__main__':
    main()
