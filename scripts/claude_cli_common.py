#!/usr/bin/env python3
"""Shared Claude CLI invocation helpers for child summarizer sessions."""
import json
import re


_CHILD_SESSION_SETTINGS = json.dumps({'disableAllHooks': True}, separators=(',', ':'))

# Output that means the CLI ran but produced no summary. Matched
# case-insensitively against the start of stdout.
_CLI_ERROR_PATTERNS = re.compile(
    r'^(not logged in|please run /login|invalid api key|error:|api error|rate limit)',
    re.IGNORECASE,
)


def build_claude_cli_cmd(model='haiku'):
    """Return a claude CLI command safe for nested summarizer calls.

    Child summarizer sessions must not inherit user hooks, otherwise a Stop
    hook that shells out to ``claude -p`` can recursively trigger itself.
    ``--bare`` is deliberately not used: it skips loading the subscription
    login, so it only works with an API key in the environment.
    """
    return [
        'claude',
        '-p',
        '--model', model,
        '--output-format', 'text',
        '--settings', _CHILD_SESSION_SETTINGS,
        '--no-session-persistence',
    ]


def looks_like_cli_error(text):
    """True if *text* is an error banner rather than a summary."""
    return bool(_CLI_ERROR_PATTERNS.match((text or '').strip()))
