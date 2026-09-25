import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from dynamic_task_update import detect_task_boundary


def _msg(role, content):
    return {'role': role, 'content': content}


def test_no_boundary():
    msgs = [_msg('user', 'Fix the bug'), _msg('assistant', 'Working on it')]
    assert detect_task_boundary(msgs) == 0


def test_single_boundary():
    msgs = [
        _msg('user', 'Fix the bug'),
        _msg('assistant', 'Done, the bug is fixed and all tests pass.'),
        _msg('user', 'Now add a new feature'),
        _msg('assistant', 'Working on the feature'),
    ]
    assert detect_task_boundary(msgs) == 2


def test_multiple_boundaries_returns_last():
    msgs = [
        _msg('user', 'Fix bug A'),
        _msg('assistant', 'Fixed, all tests pass successfully.'),
        _msg('user', 'Fix bug B'),
        _msg('assistant', 'Done, bug B is resolved and deployed.'),
        _msg('user', 'Now build feature C'),
        _msg('assistant', 'Starting on feature C'),
    ]
    assert detect_task_boundary(msgs) == 4


def test_no_boundary_when_no_followup_user_msg():
    msgs = [
        _msg('user', 'Fix the bug'),
        _msg('assistant', 'Done, the bug is completely fixed and tests pass.'),
    ]
    assert detect_task_boundary(msgs) == 0


# ---------------------------------------------------------------------------
# Tests for extract_text
# ---------------------------------------------------------------------------

from dynamic_task_update import extract_text


def test_extract_text_string():
    assert extract_text('hello world') == 'hello world'


def test_extract_text_list_of_text_blocks():
    blocks = [
        {'type': 'text', 'text': 'hello'},
        {'type': 'text', 'text': 'world'},
    ]
    assert extract_text(blocks) == 'hello world'


def test_extract_text_mixed_content():
    blocks = [
        'raw string',
        {'type': 'text', 'text': 'block text'},
        {'type': 'tool_use', 'name': 'bash'},
    ]
    assert extract_text(blocks) == 'raw string block text'


def test_extract_text_empty():
    assert extract_text('') == ''
    assert extract_text([]) == ''
    assert extract_text(None) == ''


# ---------------------------------------------------------------------------
# Tests for parse_llm_response
# ---------------------------------------------------------------------------

from dynamic_task_update import parse_llm_response


def test_parse_plain_text():
    task, done, memo = parse_llm_response('Fix the data pipeline')
    assert task == 'Fix the data pipeline'
    assert done is False
    assert memo == ''


def test_parse_done_chinese():
    task, done, memo = parse_llm_response('[完成] 修复数据管道')
    assert task == '修复数据管道'
    assert done is True
    assert memo == ''


def test_parse_done_english():
    task, done, memo = parse_llm_response('[DONE] Fix the pipeline')
    assert task == 'Fix the pipeline'
    assert done is True
    assert memo == ''


def test_parse_truncates_long_text():
    long_text = 'A' * 100
    task, done, memo = parse_llm_response(long_text)
    assert len(task) <= 60
    assert task.endswith('...')
    assert memo == ''


# ---------------------------------------------------------------------------
# Tests for memo parsing
# ---------------------------------------------------------------------------


def test_parse_response_with_memo():
    response = '任务：修复登录页验证\n备忘：【决策】改用 JWT | 【数据】影响 3 个 endpoint'
    task, is_done, memo = parse_llm_response(response)
    assert task == '修复登录页验证'
    assert is_done is False
    assert memo == '【决策】改用 JWT | 【数据】影响 3 个 endpoint'


def test_parse_response_without_memo():
    response = '任务：修复登录页验证'
    task, is_done, memo = parse_llm_response(response)
    assert task == '修复登录页验证'
    assert is_done is False
    assert memo == ''


def test_parse_response_no_prefix_backward_compat():
    response = 'Fix the data pipeline'
    task, is_done, memo = parse_llm_response(response)
    assert task == 'Fix the data pipeline'
    assert is_done is False
    assert memo == ''


def test_parse_response_done_with_memo():
    response = '任务：[完成] 修复数据管道\n备忘：【结论】根因是缓存过期'
    task, is_done, memo = parse_llm_response(response)
    assert task == '修复数据管道'
    assert is_done is True
    assert memo == '【结论】根因是缓存过期'


def test_parse_response_memo_only_no_task_prefix():
    response = '修复登录页\n备忘：【决策】改用 JWT'
    task, is_done, memo = parse_llm_response(response)
    assert task == '修复登录页'
    assert memo == '【决策】改用 JWT'


# ---------------------------------------------------------------------------
# Tests for keyword_fallback
# ---------------------------------------------------------------------------

from dynamic_task_update import keyword_fallback


def test_keyword_no_completion():
    msgs = [
        _msg('user', 'Fix the bug in parser'),
        _msg('assistant', 'I see the issue, working on it now.'),
    ]
    task, done, memo = keyword_fallback(msgs)
    assert task is not None
    assert done is False
    assert memo == ''


def test_keyword_clear_completion():
    msgs = [
        _msg('user', 'Fix the auth bug'),
        _msg('assistant', 'The bug is fixed and all tests pass. The fix is deployed successfully.'),
    ]
    task, done, memo = keyword_fallback(msgs)
    assert done is True
    assert memo == ''


def test_keyword_edge_case_two_hits_not_done():
    msgs = [
        _msg('user', 'Fix the bug'),
        _msg('assistant', 'I have finished the investigation. The root cause is identified.'),
    ]
    task, done, memo = keyword_fallback(msgs)
    assert done is False
    assert memo == ''


def test_keyword_empty_messages():
    task, done, memo = keyword_fallback([])
    assert task is None
    assert done is False
    assert memo == ''


# ---------------------------------------------------------------------------
# Tests for parse_transcript
# ---------------------------------------------------------------------------

import json
import tempfile

from dynamic_task_update import parse_transcript


def test_parse_valid_transcript():
    lines = [
        json.dumps({'type': 'user', 'message': {'content': 'Hello'}}),
        json.dumps({'type': 'assistant', 'message': {'content': 'Hi there'}}),
    ]
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write('\n'.join(lines))
        path = f.name
    try:
        msgs = parse_transcript(path)
        assert len(msgs) == 2
        assert msgs[0]['role'] == 'user'
        assert msgs[1]['role'] == 'assistant'
    finally:
        os.unlink(path)


def test_parse_skips_slash_commands():
    lines = [
        json.dumps({'type': 'user', 'message': {'content': '/task Set something'}}),
        json.dumps({'type': 'user', 'message': {'content': 'Fix the bug'}}),
    ]
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write('\n'.join(lines))
        path = f.name
    try:
        msgs = parse_transcript(path)
        assert len(msgs) == 1
        assert msgs[0]['content'] == 'Fix the bug'
    finally:
        os.unlink(path)


def test_parse_skips_malformed_lines():
    lines = [
        'not valid json',
        json.dumps({'type': 'user', 'message': {'content': 'Valid message'}}),
        '{broken',
    ]
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write('\n'.join(lines))
        path = f.name
    try:
        msgs = parse_transcript(path)
        assert len(msgs) == 1
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Tests for PREV line preservation
# ---------------------------------------------------------------------------


def test_main_preserves_prev_line(tmp_path):
    """When Python script writes a new task, it should preserve existing PREV line."""
    from dynamic_task_update import main as _unused  # just verify import works
    # We can't easily test main() directly (it reads sys.argv),
    # so test the PREV preservation logic in isolation.

    # Simulate: task file has WIP + PREV
    task_file = tmp_path / "test_session.txt"
    task_file.write_text("WIP:Old task\nPREV:Even older task\n")

    # Read PREV line (same logic as in main)
    prev_line = None
    with open(task_file, 'r') as f:
        for line in f:
            if line.startswith('PREV:'):
                prev_line = line.strip()
                break

    # Write new task, preserving PREV
    with open(task_file, 'w') as f:
        f.write("WIP:New task\n")
        if prev_line:
            f.write(f"{prev_line}\n")

    lines = task_file.read_text().splitlines()
    assert lines[0] == "WIP:New task"
    assert lines[1] == "PREV:Even older task"
    assert len(lines) == 2


def test_prev_line_not_added_when_absent(tmp_path):
    """When no PREV line exists, output should be single line."""
    task_file = tmp_path / "test_session.txt"
    task_file.write_text("WIP:Current task\n")

    prev_line = None
    with open(task_file, 'r') as f:
        for line in f:
            if line.startswith('PREV:'):
                prev_line = line.strip()
                break

    with open(task_file, 'w') as f:
        f.write("DONE:Current task\n")
        if prev_line:
            f.write(f"{prev_line}\n")

    lines = task_file.read_text().splitlines()
    assert lines[0] == "DONE:Current task"
    assert len(lines) == 1


def test_prev_line_stripped_properly(tmp_path):
    """PREV line should be stripped of whitespace including \\r\\n."""
    task_file = tmp_path / "test_session.txt"
    task_file.write_text("WIP:Task\nPREV:Old task\r\n")

    prev_line = None
    with open(task_file, 'r') as f:
        for line in f:
            if line.startswith('PREV:'):
                prev_line = line.strip()
                break

    assert prev_line == "PREV:Old task"  # no \r


# ---------------------------------------------------------------------------
# Tests for _get_backend_chain
# ---------------------------------------------------------------------------

import subprocess

from dynamic_task_update import (
    _get_backend_chain,
    build_user_prompt,
    claude_cli_summarize,
    claude_summarize,
    ollama_summarize,
)


# ---------------------------------------------------------------------------
# Tests for build_user_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_short_conversation():
    msgs = [_msg('user', 'Hi'), _msg('assistant', 'Hello')]
    prompt = build_user_prompt(msgs, min_turns=3)
    assert '备忘' not in prompt


def test_build_prompt_long_conversation():
    msgs = [
        _msg('user', 'Fix the bug'),
        _msg('assistant', 'Working on it'),
        _msg('user', 'Use JWT instead'),
        _msg('assistant', 'Done, switched to JWT'),
    ]
    prompt = build_user_prompt(msgs, min_turns=3)
    assert '备忘' in prompt


def test_build_prompt_custom_tags():
    msgs = [_msg('user', 'a'), _msg('assistant', 'b'), _msg('user', 'c'), _msg('assistant', 'd')]
    prompt = build_user_prompt(msgs, min_turns=3, tags='【风险】【成本】')
    assert '【风险】【成本】' in prompt


def test_backend_chain_auto(monkeypatch):
    monkeypatch.delenv('CLAUDE_TAB_BACKEND', raising=False)
    chain = _get_backend_chain()
    assert chain[0] is claude_summarize
    assert chain[1] is ollama_summarize
    assert chain[2] is claude_cli_summarize
    assert chain[3] is keyword_fallback


def test_backend_chain_cli_only(monkeypatch):
    monkeypatch.setenv('CLAUDE_TAB_BACKEND', 'cli')
    chain = _get_backend_chain()
    assert len(chain) == 1
    assert chain[0] is claude_cli_summarize


def test_backend_chain_api_only(monkeypatch):
    monkeypatch.setenv('CLAUDE_TAB_BACKEND', 'api')
    chain = _get_backend_chain()
    assert len(chain) == 1
    assert chain[0] is claude_summarize


def test_backend_chain_ollama_only(monkeypatch):
    monkeypatch.setenv('CLAUDE_TAB_BACKEND', 'ollama')
    chain = _get_backend_chain()
    assert len(chain) == 1
    assert chain[0] is ollama_summarize


def test_backend_chain_keyword_only(monkeypatch):
    monkeypatch.setenv('CLAUDE_TAB_BACKEND', 'keyword')
    chain = _get_backend_chain()
    assert len(chain) == 1
    assert chain[0] is keyword_fallback


def test_backend_chain_invalid_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv('CLAUDE_TAB_BACKEND', 'nonexistent')
    chain = _get_backend_chain()
    assert len(chain) == 4  # same as auto


# ---------------------------------------------------------------------------
# Tests for claude_cli_summarize
# ---------------------------------------------------------------------------


def test_claude_cli_summarize_success(monkeypatch):
    """claude_cli_summarize should parse CLI stdout into task description."""
    def mock_run(cmd, **kwargs):
        class Result:
            returncode = 0
            stdout = '修复认证 bug'
            stderr = ''
        return Result()

    monkeypatch.setattr(subprocess, 'run', mock_run)
    msgs = [_msg('user', 'Fix the auth bug'), _msg('assistant', 'Working on it')]
    task, done, memo = claude_cli_summarize(msgs)
    assert task == '修复认证 bug'
    assert done is False
    assert memo == ''


def test_claude_cli_summarize_done(monkeypatch):
    """claude_cli_summarize should detect completion prefix."""
    def mock_run(cmd, **kwargs):
        class Result:
            returncode = 0
            stdout = '[完成] 修复认证 bug'
            stderr = ''
        return Result()

    monkeypatch.setattr(subprocess, 'run', mock_run)
    msgs = [_msg('user', 'Fix the auth bug'), _msg('assistant', 'Done')]
    task, done, memo = claude_cli_summarize(msgs)
    assert task == '修复认证 bug'
    assert done is True
    assert memo == ''


def test_claude_cli_summarize_failure(monkeypatch):
    """claude_cli_summarize should raise on non-zero exit code."""
    def mock_run(cmd, **kwargs):
        class Result:
            returncode = 1
            stdout = ''
            stderr = 'error'
        return Result()

    monkeypatch.setattr(subprocess, 'run', mock_run)
    msgs = [_msg('user', 'Fix the bug')]
    import pytest
    with pytest.raises(RuntimeError):
        claude_cli_summarize(msgs)


def test_claude_cli_summarize_disables_hooks(monkeypatch):
    """CLI backend should disable hooks to avoid recursive Stop-hook sessions."""
    seen = {}

    def mock_run(cmd, **kwargs):
        seen['cmd'] = cmd
        class Result:
            returncode = 0
            stdout = 'Fix recursion bug'
            stderr = ''
        return Result()

    monkeypatch.setattr(subprocess, 'run', mock_run)
    msgs = [_msg('user', 'Summarize current task'), _msg('assistant', 'Working on it')]
    task, done, memo = claude_cli_summarize(msgs)

    assert task == 'Fix recursion bug'
    assert done is False
    assert memo == ''
    assert '--settings' in seen['cmd']
    settings_value = seen['cmd'][seen['cmd'].index('--settings') + 1]
    assert '"disableAllHooks":true' in settings_value.replace(' ', '')
    assert '--no-session-persistence' in seen['cmd']


# ---------------------------------------------------------------------------
# Tests for memo file writing
# ---------------------------------------------------------------------------

from dynamic_task_update import write_memo, resolve_project_name, sanitize_project_name
from datetime import datetime


def test_sanitize_project_name():
    assert sanitize_project_name('my-project') == 'my-project'
    assert sanitize_project_name('My Project 2') == 'my-project-2'
    assert sanitize_project_name('a' * 60) == 'a' * 50
    assert sanitize_project_name('proj@#$name') == 'proj---name'


def test_write_memo_creates_file(tmp_path):
    memo_dir = tmp_path / "memos"
    write_memo(
        memo_content='【决策】改用 JWT | 【数据】影响 3 个 endpoint',
        task_desc='修复登录页验证',
        project_name='test-project',
        memo_base_dir=str(memo_dir),
    )
    today = datetime.now().strftime('%Y-%m-%d')
    memo_file = memo_dir / 'test-project' / f'{today}.md'
    assert memo_file.exists()
    content = memo_file.read_text()
    assert f'# {today}' in content
    assert '修复登录页验证' in content
    assert '【决策】改用 JWT' in content
    assert '【数据】影响 3 个 endpoint' in content


def test_write_memo_appends(tmp_path):
    memo_dir = tmp_path / "memos"
    write_memo('【决策】第一条', '任务A', 'proj', str(memo_dir))
    write_memo('【数据】第二条', '任务B', 'proj', str(memo_dir))
    today = datetime.now().strftime('%Y-%m-%d')
    content = (memo_dir / 'proj' / f'{today}.md').read_text()
    assert '任务A' in content
    assert '任务B' in content


def test_write_memo_skips_empty():
    write_memo('', '任务', 'proj', '/tmp/nonexistent-memo-dir-test')
    # Should not create any file or raise


def test_resolve_project_name_fallback():
    name = resolve_project_name('/tmp')
    assert name == 'general'


def test_resolve_project_name_home():
    import pathlib
    home = str(pathlib.Path.home())
    name = resolve_project_name(home)
    assert name == 'general'


# ---------------------------------------------------------------------------
# Tests for load_memo_config
# ---------------------------------------------------------------------------

from dynamic_task_update import load_memo_config


def test_load_config_defaults(tmp_path):
    config = load_memo_config(str(tmp_path / 'nonexistent.yaml'))
    assert config['min_turns'] == 3
    assert config['archive_days'] == 90
    assert '决策' in config['tags_str']


def test_load_config_custom(tmp_path):
    config_file = tmp_path / 'config.yaml'
    config_file.write_text('tags:\n  - 决策\n  - 风险\nmin_turns: 5\narchive_days: 30\n')
    config = load_memo_config(str(config_file))
    assert config['min_turns'] == 5
    assert config['archive_days'] == 30
    assert '风险' in config['tags_str']


def test_load_config_invalid_yaml(tmp_path):
    config_file = tmp_path / 'config.yaml'
    config_file.write_text('not: valid: yaml: [broken')
    config = load_memo_config(str(config_file))
    assert config['min_turns'] == 3  # defaults


# ---------------------------------------------------------------------------
# Tests for cli_background using parse_llm_response (imported from dynamic_task_update)
# ---------------------------------------------------------------------------


def test_cli_background_parse_response():
    """Test that parse_llm_response handles memo correctly."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
    from dynamic_task_update import parse_llm_response
    task, done, memo = parse_llm_response("任务：修复 bug\n备忘：【决策】改用新方案")
    assert task == '修复 bug'
    assert done is False
    assert memo == '【决策】改用新方案'


def test_cli_background_parse_response_done():
    """parse_llm_response detects completion prefix."""
    from dynamic_task_update import parse_llm_response
    task, done, memo = parse_llm_response("任务：[完成] 部署上线\n备忘：【结论】顺利完成")
    assert task == '部署上线'
    assert done is True
    assert memo == '【结论】顺利完成'


def test_cli_background_parse_response_no_memo():
    """parse_llm_response returns empty memo when none present."""
    from dynamic_task_update import parse_llm_response
    task, done, memo = parse_llm_response("Fix the data pipeline")
    assert task == 'Fix the data pipeline'
    assert done is False
    assert memo == ''


def test_cli_background_main_disables_hooks(tmp_path, monkeypatch):
    """Detached CLI helper should disable hooks before invoking claude."""
    import cli_background

    prompt_file = tmp_path / 'prompt.txt'
    task_file = tmp_path / 'task.txt'
    prompt_file.write_text('summarize me')

    seen = {}

    def mock_run(cmd, **kwargs):
        seen['cmd'] = cmd
        class Result:
            returncode = 0
            stdout = 'Summarized task'
            stderr = ''
        return Result()

    monkeypatch.setattr(cli_background.subprocess, 'run', mock_run)
    monkeypatch.setattr(sys, 'argv', ['cli_background.py', str(prompt_file), str(task_file)])

    cli_background.main()

    assert task_file.read_text().splitlines()[0] == 'WIP:Summarized task'
    assert '--settings' in seen['cmd']
    settings_value = seen['cmd'][seen['cmd'].index('--settings') + 1]
    assert '"disableAllHooks":true' in settings_value.replace(' ', '')
    assert '--no-session-persistence' in seen['cmd']


# ---------------------------------------------------------------------------
# Tests for archive_old_memos
# ---------------------------------------------------------------------------

import time as time_module
from dynamic_task_update import archive_old_memos


def test_archive_old_memos(tmp_path):
    memo_dir = tmp_path / 'memos'
    proj_dir = memo_dir / 'test-project'
    proj_dir.mkdir(parents=True)

    # Create an "old" file
    old_file = proj_dir / '2025-12-01.md'
    old_file.write_text('# old memo')
    old_time = time_module.time() - (100 * 86400)
    os.utime(str(old_file), (old_time, old_time))

    # Create a "recent" file
    new_file = proj_dir / '2026-03-21.md'
    new_file.write_text('# new memo')

    archive_old_memos(str(memo_dir), archive_days=90)

    archive_dir = memo_dir / '_archive' / 'test-project'
    assert not old_file.exists()
    assert (archive_dir / '2025-12-01.md').exists()
    assert new_file.exists()


# ---------------------------------------------------------------------------
# Tests for ollama_timeout config
# ---------------------------------------------------------------------------

from dynamic_task_update import OLLAMA_TIMEOUT, DEFAULT_CONFIG


def test_ollama_timeout_default_is_15():
    """OLLAMA_TIMEOUT module-level default should be 15."""
    assert OLLAMA_TIMEOUT == 15


def test_default_config_has_ollama_timeout():
    """DEFAULT_CONFIG should include ollama_timeout."""
    assert 'ollama_timeout' in DEFAULT_CONFIG
    assert DEFAULT_CONFIG['ollama_timeout'] == 15


def test_load_config_ollama_timeout(tmp_path):
    """load_memo_config should parse ollama_timeout from YAML."""
    config_file = tmp_path / 'config.yaml'
    config_file.write_text('ollama_timeout: 30\n')
    config = load_memo_config(str(config_file))
    assert config['ollama_timeout'] == 30


def test_load_config_ollama_timeout_default(tmp_path):
    """load_memo_config should use default ollama_timeout when not in YAML."""
    config = load_memo_config(str(tmp_path / 'nonexistent.yaml'))
    assert config['ollama_timeout'] == 15


def test_ollama_summarize_accepts_timeout_param():
    """ollama_summarize should accept a timeout keyword argument."""
    import inspect
    sig = inspect.signature(ollama_summarize)
    assert 'timeout' in sig.parameters


# ---------------------------------------------------------------------------
# Tests for write_memo file locking
# ---------------------------------------------------------------------------

from dynamic_task_update import HAS_FCNTL


def test_write_memo_creates_lock_file(tmp_path):
    """On Unix (fcntl available), write_memo should create a .lock file."""
    if not HAS_FCNTL:
        return  # skip on Windows
    memo_dir = tmp_path / "memos"
    write_memo('【决策】test', 'task', 'proj', str(memo_dir))
    today = datetime.now().strftime('%Y-%m-%d')
    lock_file = memo_dir / 'proj' / f'{today}.md.lock'
    assert lock_file.exists()


def test_write_memo_still_works_without_fcntl(tmp_path, monkeypatch):
    """write_memo should fall back to unlocked write when HAS_FCNTL is False."""
    import dynamic_task_update
    monkeypatch.setattr(dynamic_task_update, 'HAS_FCNTL', False)
    memo_dir = tmp_path / "memos"
    write_memo('【决策】fallback test', 'task', 'proj', str(memo_dir))
    today = datetime.now().strftime('%Y-%m-%d')
    memo_file = memo_dir / 'proj' / f'{today}.md'
    assert memo_file.exists()
    assert '【决策】fallback test' in memo_file.read_text()


# ---------------------------------------------------------------------------
# Tests for multi-layer PREV history
# ---------------------------------------------------------------------------

from dynamic_task_update import read_prev_lines, shift_prev_lines


def test_read_prev_lines_new_format(tmp_path):
    """read_prev_lines should parse PREV:N:task format."""
    f = tmp_path / "task.txt"
    f.write_text("WIP:Current\nPREV:1:First done\nPREV:2:Second done\n")
    result = read_prev_lines(str(f))
    assert result == ["PREV:1:First done", "PREV:2:Second done"]


def test_read_prev_lines_old_format(tmp_path):
    """read_prev_lines should treat old PREV:task as PREV:1:task."""
    f = tmp_path / "task.txt"
    f.write_text("WIP:Current\nPREV:Old task\n")
    result = read_prev_lines(str(f))
    assert result == ["PREV:1:Old task"]


def test_read_prev_lines_mixed_format(tmp_path):
    """read_prev_lines handles mix of old and new formats."""
    f = tmp_path / "task.txt"
    f.write_text("WIP:Current\nPREV:Legacy task\nPREV:2:Newer task\n")
    result = read_prev_lines(str(f))
    assert result == ["PREV:1:Legacy task", "PREV:2:Newer task"]


def test_read_prev_lines_empty_file(tmp_path):
    """read_prev_lines returns empty list for file with no PREVs."""
    f = tmp_path / "task.txt"
    f.write_text("WIP:Current\n")
    result = read_prev_lines(str(f))
    assert result == []


def test_read_prev_lines_nonexistent():
    """read_prev_lines returns empty list for missing file."""
    result = read_prev_lines("/tmp/nonexistent_task_file_xyz.txt")
    assert result == []


def test_read_prev_lines_caps_at_3(tmp_path):
    """read_prev_lines should not return PREV:4 or higher."""
    f = tmp_path / "task.txt"
    f.write_text("WIP:Current\nPREV:1:A\nPREV:2:B\nPREV:3:C\nPREV:4:D\n")
    result = read_prev_lines(str(f))
    assert len(result) == 3
    assert "PREV:4:D" not in result


def test_shift_prev_lines_basic(tmp_path):
    """shift_prev_lines pushes PREV:1 to PREV:2, inserts new PREV:1."""
    f = tmp_path / "task.txt"
    f.write_text("DONE:Old task\nPREV:1:First\nPREV:2:Second\n")
    result = shift_prev_lines("New done", str(f))
    assert result == ["PREV:1:New done", "PREV:2:First", "PREV:3:Second"]


def test_shift_prev_lines_overflow(tmp_path):
    """shift_prev_lines drops PREV:3 when it would become PREV:4."""
    f = tmp_path / "task.txt"
    f.write_text("DONE:Task\nPREV:1:A\nPREV:2:B\nPREV:3:C\n")
    result = shift_prev_lines("New", str(f))
    assert len(result) == 3
    assert result[0] == "PREV:1:New"
    assert result[1] == "PREV:2:A"
    assert result[2] == "PREV:3:B"


def test_shift_prev_lines_empty(tmp_path):
    """shift_prev_lines with no existing PREVs creates PREV:1 only."""
    f = tmp_path / "task.txt"
    f.write_text("DONE:Task\n")
    result = shift_prev_lines("Done task", str(f))
    assert result == ["PREV:1:Done task"]


# ---------------------------------------------------------------------------
# Tests for estimate_tokens
# ---------------------------------------------------------------------------

from dynamic_task_update import estimate_tokens


def test_estimate_tokens_english():
    text = "Hello world this is a test"
    tokens = estimate_tokens(text)
    assert 10 < tokens < 30


def test_estimate_tokens_chinese():
    text = "修复登录页验证并部署到生产环境"
    tokens = estimate_tokens(text)
    assert 5 < tokens < 30


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_estimate_tokens_large():
    """A 15KB text should estimate around 10,000 tokens."""
    text = "测试内容 " * 3000  # ~15KB
    tokens = estimate_tokens(text)
    assert 8000 < tokens < 12000


# ---------------------------------------------------------------------------
# Tests for summarize_memo_content
# ---------------------------------------------------------------------------

from dynamic_task_update import summarize_memo_content


def test_summarize_keeps_headers_and_conclusions():
    content = """# 2026-03-23

## 08:00 | Fix auth bug
- 【决策】Switch to JWT
- 【数据】Affects 3 endpoints
- 【结论】Root cause was cache

## 09:00 | Deploy to prod
- 【决策】Blue-green deploy
- 【结论】Successful rollout
"""
    summary = summarize_memo_content(content)
    assert '## 08:00 | Fix auth bug' in summary
    assert '## 09:00 | Deploy to prod' in summary
    assert '【结论】Root cause was cache' in summary
    assert '【结论】Successful rollout' in summary
    # 【决策】and 【数据】 lines should be excluded in summary
    assert '【决策】Switch to JWT' not in summary
    assert '【数据】Affects 3 endpoints' not in summary


def test_summarize_empty():
    assert summarize_memo_content("") == ""


def test_shift_prev_lines_old_format(tmp_path):
    """shift_prev_lines handles old PREV:task format."""
    f = tmp_path / "task.txt"
    f.write_text("DONE:Current\nPREV:Legacy\n")
    result = shift_prev_lines("New done", str(f))
    assert result[0] == "PREV:1:New done"
    assert result[1] == "PREV:2:Legacy"


def test_main_preserves_multi_prev(tmp_path):
    """When Python script writes a new task, it preserves all PREV lines."""
    task_file = tmp_path / "test_session.txt"
    task_file.write_text("WIP:Old task\nPREV:1:First\nPREV:2:Second\nPREV:3:Third\n")

    prev_lines = read_prev_lines(str(task_file))
    with open(task_file, 'w') as f:
        f.write("WIP:New task\n")
        for pl in prev_lines:
            f.write(f"{pl}\n")

    lines = task_file.read_text().splitlines()
    assert lines[0] == "WIP:New task"
    assert lines[1] == "PREV:1:First"
    assert lines[2] == "PREV:2:Second"
    assert lines[3] == "PREV:3:Third"


# ---------------------------------------------------------------------------
# Tests for memo search
# ---------------------------------------------------------------------------

from memo_search import search_memos


def test_search_memos_finds_keyword(tmp_path):
    """search_memos should find a memo by keyword."""
    proj_dir = tmp_path / "test-project"
    proj_dir.mkdir()
    memo_file = proj_dir / "2026-03-26.md"
    memo_file.write_text("# 2026-03-26\n\n## 14:30 | Fix JWT auth\n- Changed token expiry to 24h\n")

    results = search_memos("JWT", memo_base_dir=str(tmp_path))
    assert len(results) >= 1
    assert results[0]['project'] == 'test-project'
    assert results[0]['date'] == '2026-03-26'
    assert 'JWT' in results[0]['match_line']


def test_search_memos_case_insensitive(tmp_path):
    """search_memos should be case-insensitive."""
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / "2026-03-26.md").write_text("# 2026-03-26\n\n## 10:00 | Setup\n- Configured NGINX proxy\n")

    results = search_memos("nginx", memo_base_dir=str(tmp_path))
    assert len(results) == 1
    assert 'NGINX' in results[0]['match_line']


def test_search_memos_no_match(tmp_path):
    """search_memos returns empty list when no match found."""
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / "2026-03-26.md").write_text("# 2026-03-26\n\n## 10:00 | Setup\n- Nothing special\n")

    results = search_memos("nonexistent_keyword_xyz", memo_base_dir=str(tmp_path))
    assert results == []


def test_search_memos_respects_max_results(tmp_path):
    """search_memos should stop at max_results."""
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    lines = ["# 2026-03-26\n\n## 10:00 | Task\n"]
    for i in range(20):
        lines.append(f"- Match item {i}\n")
    (proj_dir / "2026-03-26.md").write_text("".join(lines))

    results = search_memos("Match", memo_base_dir=str(tmp_path), max_results=5)
    assert len(results) == 5


def test_search_memos_across_projects(tmp_path):
    """search_memos should find matches across multiple projects."""
    for name in ["alpha", "beta"]:
        d = tmp_path / name
        d.mkdir()
        (d / "2026-03-26.md").write_text(
            f"# 2026-03-26\n\n## 10:00 | {name} task\n- Deploy to production\n"
        )

    results = search_memos("Deploy", memo_base_dir=str(tmp_path))
    projects = {r['project'] for r in results}
    assert 'alpha' in projects
    assert 'beta' in projects


def test_search_memos_empty_dir(tmp_path):
    """search_memos on empty dir returns empty list."""
    results = search_memos("anything", memo_base_dir=str(tmp_path))
    assert results == []


def test_search_memos_nonexistent_dir():
    """search_memos with nonexistent dir returns empty list."""
    results = search_memos("query", memo_base_dir="/tmp/nonexistent_memo_dir_xyz_test")
    assert results == []


def test_search_memos_skips_archive(tmp_path):
    """search_memos should skip _archive directories."""
    archive_dir = tmp_path / "_archive"
    archive_dir.mkdir()
    (archive_dir / "2025-01-01.md").write_text("# old\n- secret keyword\n")

    results = search_memos("secret", memo_base_dir=str(tmp_path))
    assert results == []


# ---------------------------------------------------------------------------
# Tests for title_similarity
# ---------------------------------------------------------------------------

from dynamic_task_update import title_similarity


def test_similarity_identical():
    assert title_similarity("修复登录页验证", "修复登录页验证") == 1.0


def test_similarity_completely_different():
    assert title_similarity("Fix auth bug", "Deploy to production") < 0.2


def test_similarity_partial_overlap():
    score = title_similarity(
        "Phase 3 Preset 系统开发 已完成 并测试通过",
        "Phase 3 Preset 系统开发 已完成"
    )
    assert score > 0.6


def test_similarity_empty_strings():
    assert title_similarity("", "") == 0.0
    assert title_similarity("hello", "") == 0.0
    assert title_similarity("", "world") == 0.0


def test_similarity_case_insensitive():
    assert title_similarity("Fix Auth Bug", "fix auth bug") == 1.0


# ---------------------------------------------------------------------------
# Tests for new config keys (token budget)
# ---------------------------------------------------------------------------


def test_load_config_token_budget_defaults(tmp_path):
    """Default config should have token budget keys."""
    config = load_memo_config(str(tmp_path / 'nonexistent.yaml'))
    assert config['recall_token_budget'] == 8000
    assert config['memo_merge_window'] == 300
    assert config['memo_merge_threshold'] == 0.6


def test_load_config_token_budget_custom(tmp_path):
    """load_memo_config should parse new token budget keys."""
    config_file = tmp_path / 'config.yaml'
    config_file.write_text(
        'recall_token_budget: 4000\n'
        'memo_merge_window: 600\n'
        'memo_merge_threshold: 0.8\n'
    )
    config = load_memo_config(str(config_file))
    assert config['recall_token_budget'] == 4000
    assert config['memo_merge_window'] == 600
    assert config['memo_merge_threshold'] == 0.8


def test_load_config_token_budget_partial(tmp_path):
    """Missing new keys should fall back to defaults."""
    config_file = tmp_path / 'config.yaml'
    config_file.write_text('recall_token_budget: 5000\n')
    config = load_memo_config(str(config_file))
    assert config['recall_token_budget'] == 5000
    assert config['memo_merge_window'] == 300  # default
    assert config['memo_merge_threshold'] == 0.6  # default


def test_load_config_merge_disabled(tmp_path):
    """memo_merge_window: 0 should be parsed as 0 (disabled)."""
    config_file = tmp_path / 'config.yaml'
    config_file.write_text('memo_merge_window: 0\n')
    config = load_memo_config(str(config_file))
    assert config['memo_merge_window'] == 0


# ---------------------------------------------------------------------------
# Tests for memo merge (write_memo deduplication)
# ---------------------------------------------------------------------------


def test_write_memo_merges_similar_within_window(tmp_path):
    """Two similar memos within merge window should be merged."""
    memo_dir = tmp_path / "memos"
    write_memo('【决策】Switch to JWT', 'Phase 3 Preset系统开发已完成', 'proj', str(memo_dir))
    write_memo('【数据】Affects 3 endpoints', 'Phase 3 Preset系统开发已完成并测试通过', 'proj', str(memo_dir))

    today = datetime.now().strftime('%Y-%m-%d')
    content = (memo_dir / 'proj' / f'{today}.md').read_text()
    # Should have only ONE ## header (merged), not two
    headers = [l for l in content.splitlines() if l.startswith('## ')]
    assert len(headers) == 1
    # Merged entry should have both bullet points
    assert '【决策】Switch to JWT' in content
    assert '【数据】Affects 3 endpoints' in content
    # Title should be the newer one
    assert 'Phase 3 Preset系统开发已完成并测试通过' in headers[0]


def test_write_memo_no_merge_different_titles(tmp_path):
    """Memos with different titles should NOT be merged."""
    memo_dir = tmp_path / "memos"
    write_memo('【决策】改用 JWT', '修复登录页验证', 'proj', str(memo_dir))
    write_memo('【数据】新增 10 个 API', '开发支付模块', 'proj', str(memo_dir))

    today = datetime.now().strftime('%Y-%m-%d')
    content = (memo_dir / 'proj' / f'{today}.md').read_text()
    headers = [l for l in content.splitlines() if l.startswith('## ')]
    assert len(headers) == 2


def test_write_memo_no_merge_when_disabled(tmp_path):
    """When memo_merge_window=0, merging should be disabled."""
    memo_dir = tmp_path / "memos"
    config = dict(DEFAULT_CONFIG)
    config['memo_merge_window'] = 0
    write_memo('【决策】First', 'Same task name', 'proj', str(memo_dir), merge_config=config)
    write_memo('【数据】Second', 'Same task name', 'proj', str(memo_dir), merge_config=config)

    today = datetime.now().strftime('%Y-%m-%d')
    content = (memo_dir / 'proj' / f'{today}.md').read_text()
    headers = [l for l in content.splitlines() if l.startswith('## ')]
    assert len(headers) == 2


def test_write_memo_deduplicates_bullets(tmp_path):
    """Merged entry should not have duplicate bullet points."""
    memo_dir = tmp_path / "memos"
    write_memo('【决策】改用 JWT | 【结论】测试通过', 'Same task', 'proj', str(memo_dir))
    write_memo('【决策】改用 JWT | 【数据】3 endpoints', 'Same task', 'proj', str(memo_dir))

    today = datetime.now().strftime('%Y-%m-%d')
    content = (memo_dir / 'proj' / f'{today}.md').read_text()
    # 【决策】改用 JWT should appear only once
    assert content.count('【决策】改用 JWT') == 1
    assert '【结论】测试通过' in content
    assert '【数据】3 endpoints' in content


# ---------------------------------------------------------------------------
# Integration test: memo lifecycle with merge
# ---------------------------------------------------------------------------


def test_memo_lifecycle_merge_and_summarize(tmp_path):
    """End-to-end: write multiple similar memos, verify merge, then summarize."""
    memo_dir = tmp_path / "memos"

    # Write 3 similar memos (should merge into 1)
    write_memo('【决策】Use Redis', 'Optimize caching layer', 'proj', str(memo_dir))
    write_memo('【数据】p99 reduced 40%', 'Optimize caching layer performance', 'proj', str(memo_dir))
    write_memo('【结论】Cache hit rate 95%', 'Optimize caching layer performance tuning', 'proj', str(memo_dir))

    # Write 1 different memo (should NOT merge)
    write_memo('【决策】Add rate limiter', 'Implement API rate limiting', 'proj', str(memo_dir))

    today = datetime.now().strftime('%Y-%m-%d')
    content = (memo_dir / 'proj' / f'{today}.md').read_text()

    # Should have exactly 2 entries
    headers = [l for l in content.splitlines() if l.startswith('## ')]
    assert len(headers) == 2

    # First entry (merged) should have all 3 bullets
    assert '【决策】Use Redis' in content
    assert '【数据】p99 reduced 40%' in content
    assert '【结论】Cache hit rate 95%' in content

    # Second entry should be separate
    assert '【决策】Add rate limiter' in content

    # Summarize should only keep headers + conclusions
    summary = summarize_memo_content(content)
    assert '## ' in summary
    assert '【结论】Cache hit rate 95%' in summary
    assert '【决策】Use Redis' not in summary  # decisions excluded from summary

    # Token estimate should be reasonable
    full_tokens = estimate_tokens(content)
    summary_tokens = estimate_tokens(summary)
    assert summary_tokens < full_tokens


# ---------------------------------------------------------------------------
# Regression: CLAUDE_TAB_SKIP_HOOK guard must not kill the background helper
# ---------------------------------------------------------------------------

import subprocess

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'scripts')


def _run_with_skip_hook(code):
    env = dict(os.environ, CLAUDE_TAB_SKIP_HOOK='1')
    return subprocess.run(
        [sys.executable, '-c', code],
        cwd=SCRIPTS_DIR, env=env, capture_output=True, text=True, timeout=30,
    )


def test_skip_hook_env_does_not_abort_import():
    """cli_background.py is launched with CLAUDE_TAB_SKIP_HOOK=1 and imports
    dynamic_task_update. An import-time sys.exit() makes the helper die before
    ever calling claude, leaving every session stuck at INIT."""
    r = _run_with_skip_hook("import dynamic_task_update, cli_background; print('imported')")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == 'imported'


def test_skip_hook_env_still_stops_main(tmp_path):
    """The recursion guard must still apply when the Stop hook entrypoint
    itself runs inside a child claude session."""
    transcript = tmp_path / 't.jsonl'
    transcript.write_text('{"type":"user","message":{"content":"Fix the login bug please"}}\n'
                          '{"type":"assistant","message":{"content":"Looking at auth.py now"}}\n')
    task_file = tmp_path / 'task.txt'
    task_file.write_text('INIT:x\n')
    r = _run_with_skip_hook(
        "import sys; sys.argv=['x', %r, %r]; import dynamic_task_update as d; d.main()"
        % (str(transcript), str(task_file))
    )
    assert r.returncode == 0, r.stderr
    assert task_file.read_text() == 'INIT:x\n'
