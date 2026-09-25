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


def _write_job(tmp_path, task_file, **extra):
    import json
    job = {'prompt': 'summarize me', 'task_file': str(task_file)}
    job.update(extra)
    job_file = tmp_path / 'job.json'
    job_file.write_text(json.dumps(job))
    return job_file


def _mock_cli(monkeypatch, stdout='Summarized task', returncode=0, seen=None):
    import cli_background

    def mock_run(cmd, **kwargs):
        if seen is not None:
            seen['cmd'] = cmd
        class Result:
            pass
        r = Result()
        r.returncode = returncode
        r.stdout = stdout
        r.stderr = ''
        return r

    monkeypatch.setattr(cli_background.subprocess, 'run', mock_run)
    return cli_background


def test_cli_background_main_disables_hooks(tmp_path, monkeypatch):
    """Detached CLI helper should disable hooks before invoking claude."""
    task_file = tmp_path / 'task.txt'
    job_file = _write_job(tmp_path, task_file)
    seen = {}
    cli_background = _mock_cli(monkeypatch, seen=seen)
    monkeypatch.setattr(sys, 'argv', ['cli_background.py', str(job_file)])

    cli_background.main()

    assert task_file.read_text().splitlines()[0] == 'WIP:Summarized task'
    assert '--settings' in seen['cmd']
    settings_value = seen['cmd'][seen['cmd'].index('--settings') + 1]
    assert '"disableAllHooks":true' in settings_value.replace(' ', '')
    assert '--no-session-persistence' in seen['cmd']
    assert '--bare' not in seen['cmd']  # --bare skips subscription login
    assert not job_file.exists()  # job file is consumed


def test_cli_background_falls_back_when_cli_fails(tmp_path, monkeypatch):
    """A CLI failure must not leave the statusline stale: use the keyword fallback."""
    task_file = tmp_path / 'task.txt'
    task_file.write_text('INIT:proj\n')
    job_file = _write_job(tmp_path, task_file, fallback_task='Fix the login bug', fallback_done=False)
    cli_background = _mock_cli(monkeypatch, stdout='', returncode=1)
    monkeypatch.setattr(sys, 'argv', ['cli_background.py', str(job_file)])

    cli_background.main()

    assert task_file.read_text().splitlines()[0] == 'WIP:Fix the login bug'


def test_cli_background_treats_login_banner_as_failure(tmp_path, monkeypatch):
    task_file = tmp_path / 'task.txt'
    job_file = _write_job(tmp_path, task_file, fallback_task='Fix the login bug')
    cli_background = _mock_cli(monkeypatch, stdout='Not logged in · Please run /login', returncode=0)
    monkeypatch.setattr(sys, 'argv', ['cli_background.py', str(job_file)])

    cli_background.main()

    assert task_file.read_text().splitlines()[0] == 'WIP:Fix the login bug'


def test_cli_background_skips_write_when_superseded(tmp_path, monkeypatch):
    """A newer helper (newer generation token) owns the task file."""
    from dynamic_task_update import write_generation
    task_file = tmp_path / 'task.txt'
    task_file.write_text('WIP:newer result\n')
    write_generation(str(task_file))  # current token
    job_file = _write_job(tmp_path, task_file, generation='stale-token')
    cli_background = _mock_cli(monkeypatch, stdout='Old slow result')
    monkeypatch.setattr(sys, 'argv', ['cli_background.py', str(job_file)])

    try:
        cli_background.main()
    except SystemExit as e:
        assert e.code == 0

    assert task_file.read_text().splitlines()[0] == 'WIP:newer result'


def test_cli_background_respects_manual_pin(tmp_path, monkeypatch):
    """If the user ran /task while the helper was running, keep MANUAL."""
    task_file = tmp_path / 'task.txt'
    task_file.write_text('MANUAL:Reviewing strategy\n')
    job_file = _write_job(tmp_path, task_file)
    cli_background = _mock_cli(monkeypatch, stdout='Auto result')
    monkeypatch.setattr(sys, 'argv', ['cli_background.py', str(job_file)])

    try:
        cli_background.main()
    except SystemExit as e:
        assert e.code == 0

    assert task_file.read_text().splitlines()[0] == 'MANUAL:Reviewing strategy'


def test_cli_background_preserves_prev_history(tmp_path, monkeypatch):
    task_file = tmp_path / 'task.txt'
    task_file.write_text('WIP:\nPREV:1:old task\nPREV:2:older task\n')
    job_file = _write_job(tmp_path, task_file)
    cli_background = _mock_cli(monkeypatch, stdout='New task')
    monkeypatch.setattr(sys, 'argv', ['cli_background.py', str(job_file)])

    cli_background.main()

    assert task_file.read_text().splitlines() == ['WIP:New task', 'PREV:1:old task', 'PREV:2:older task']


def test_launch_cli_background_writes_job_and_generation(tmp_path, monkeypatch):
    import json
    import dynamic_task_update as d
    captured = {}

    class FakePopen:
        def __init__(self, args, **kwargs):
            captured['args'] = args
            captured['env'] = kwargs.get('env', {})

    monkeypatch.setattr(d.subprocess, 'Popen', FakePopen)
    task_file = tmp_path / 'task.txt'
    d._launch_cli_background('PROMPT', str(task_file), str(tmp_path / 'memos'), 'proj',
                             fallback=('kw task', False))

    job_path = captured['args'][-1]
    job = json.loads(open(job_path, encoding='utf-8').read())
    os.unlink(job_path)
    assert job['prompt'] == 'PROMPT'
    assert job['fallback_task'] == 'kw task'
    assert job['generation'] == d.read_generation(str(task_file))
    assert captured['env']['CLAUDE_TAB_SKIP_HOOK'] == '1'


# ---------------------------------------------------------------------------
# Transcript hygiene: injected entries must not become the task anchor
# ---------------------------------------------------------------------------

def _jsonl(tmp_path, entries):
    import json
    p = tmp_path / 't.jsonl'
    p.write_text('\n'.join(json.dumps(e, ensure_ascii=False) for e in entries) + '\n')
    return str(p)


def test_parse_transcript_skips_slash_command_entries(tmp_path):
    from dynamic_task_update import parse_transcript
    path = _jsonl(tmp_path, [
        {'type': 'user', 'message': {'content': '<command-name>/login</command-name>\n<command-message>login</command-message>'}},
        {'type': 'user', 'message': {'content': '<local-command-stdout>Login successful</local-command-stdout>'}},
        {'type': 'user', 'message': {'content': 'Fix the login bug in auth.py'}},
        {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Looking at auth.py'}]}},
    ])
    msgs = parse_transcript(path)
    assert [m['content'] for m in msgs] == ['Fix the login bug in auth.py', 'Looking at auth.py']


def test_parse_transcript_skips_meta_sidechain_and_notifications(tmp_path):
    from dynamic_task_update import parse_transcript
    path = _jsonl(tmp_path, [
        {'type': 'user', 'isMeta': True, 'message': {'content': 'injected context'}},
        {'type': 'user', 'isSidechain': True, 'message': {'content': 'subagent prompt'}},
        {'type': 'user', 'parent_tool_use_id': 'toolu_1', 'message': {'content': 'subagent prompt 2'}},
        {'type': 'user', 'message': {'content': '<task-notification>agent finished</task-notification>'}},
        {'type': 'user', 'message': {'content': '[Request interrupted by user]'}},
        {'type': 'user', 'message': {'content': 'Real request here'}},
    ])
    msgs = parse_transcript(path)
    assert [m['content'] for m in msgs] == ['Real request here']


def test_parse_transcript_strips_system_reminder_blocks(tmp_path):
    from dynamic_task_update import parse_transcript
    path = _jsonl(tmp_path, [
        {'type': 'user', 'message': {'content': '<system-reminder>\nlots of context\n</system-reminder>\nAdd a retry to the fetcher'}},
        {'type': 'user', 'message': {'content': '<system-reminder>only a reminder</system-reminder>'}},
    ])
    msgs = parse_transcript(path)
    assert [m['content'] for m in msgs] == ['Add a retry to the fetcher']


def test_truncate_task_limits_length():
    from dynamic_task_update import truncate_task
    assert truncate_task('x' * 60) == 'x' * 60
    assert truncate_task('x' * 61) == 'x' * 57 + '...'
    assert truncate_task('  spaced  ') == 'spaced'


def test_log_error_writes_and_never_raises(tmp_path, monkeypatch):
    import dynamic_task_update as d
    log = tmp_path / 'sub' / '_errors.log'
    monkeypatch.setattr(d, 'ERROR_LOG', str(log))
    d.log_error('backend x failed')
    assert 'backend x failed' in log.read_text()
    monkeypatch.setattr(d, 'ERROR_LOG', '/dev/null/not-writable/x.log')
    d.log_error('ignored')  # must not raise


def test_looks_like_cli_error():
    from claude_cli_common import looks_like_cli_error
    assert looks_like_cli_error('Not logged in · Please run /login')
    assert looks_like_cli_error('Error: something')
    assert not looks_like_cli_error('修复登录 bug')
    assert not looks_like_cli_error('')


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


# ---------------------------------------------------------------------------
# Shell hooks: exercised end to end with a fake HOME (require jq)
# ---------------------------------------------------------------------------

import shutil
import pytest

_HAS_JQ = shutil.which('jq') is not None


def _run_hook(script, payload, home, env=None):
    import json
    env = dict(os.environ, HOME=str(home), **(env or {}))
    return subprocess.run(
        ['bash', os.path.join(SCRIPTS_DIR, script)],
        input=json.dumps(payload), capture_output=True, text=True, timeout=30, env=env,
    )


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_session_start_writes_placeholder_and_lookup(tmp_path):
    r = _run_hook('session_start.sh', {'session_id': 'sid-1', 'cwd': str(tmp_path), 'source': 'startup'}, tmp_path)
    assert r.returncode == 0, r.stderr
    tasks = tmp_path / '.claude' / 'session-tasks'
    assert (tasks / 'sid-1.txt').read_text().startswith('INIT:' + tmp_path.name)
    lookups = list(tasks.glob('current_*.txt'))
    assert len(lookups) == 1 and lookups[0].read_text().strip() == 'sid-1'


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_session_start_keeps_task_on_resume_and_compact(tmp_path):
    tasks = tmp_path / '.claude' / 'session-tasks'
    tasks.mkdir(parents=True)
    (tasks / 'sid-2.txt').write_text('WIP:Refactoring the parser\n')
    for source in ('resume', 'compact', 'clear'):
        r = _run_hook('session_start.sh', {'session_id': 'sid-2', 'cwd': str(tmp_path), 'source': source}, tmp_path)
        assert r.returncode == 0, r.stderr
        assert (tasks / 'sid-2.txt').read_text() == 'WIP:Refactoring the parser\n', source


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_session_start_memo_overview_counts_entries(tmp_path):
    memos = tmp_path / '.claude' / 'memos' / 'proj'
    memos.mkdir(parents=True)
    (memos / '2026-01-01.md').write_text('# 2026-01-01\n\n## 10:00 | a\n- x\n\n## 11:00 | b\n- y\n')
    (memos / '2026-01-02.md').write_text('# 2026-01-02\n')  # zero entries: grep -c exits 1
    r = _run_hook('session_start.sh', {'session_id': 'sid-3', 'cwd': str(tmp_path), 'source': 'startup'}, tmp_path)
    assert r.returncode == 0
    assert 'integer expression expected' not in r.stderr
    assert '[memo] Recent projects:' in r.stdout
    assert '2026-01-01 2' in r.stdout
    assert '2026-01-02' not in r.stdout


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_session_end_removes_own_lookup_and_sidecars(tmp_path):
    _run_hook('session_start.sh', {'session_id': 'sid-6', 'cwd': str(tmp_path), 'source': 'startup'}, tmp_path)
    tasks = tmp_path / '.claude' / 'session-tasks'
    (tasks / 'sid-6.txt.gen').write_text('1')
    (tasks / 'sid-6.txt.lock').write_text('')
    # A different session took over the same cwd: lookup must survive
    lookup = next(tasks.glob('current_*.txt'))
    lookup.write_text('sid-other\n')
    _run_hook('session_end.sh', {'session_id': 'sid-6', 'cwd': str(tmp_path)}, tmp_path)
    assert lookup.exists()
    assert (tasks / 'sid-6.txt.gen').exists()  # kept: a helper may still be in flight
    assert not (tasks / 'sid-6.txt.lock').exists()
    lookup.write_text('sid-6\n')
    _run_hook('session_end.sh', {'session_id': 'sid-6', 'cwd': str(tmp_path)}, tmp_path)
    assert not lookup.exists()


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_statusline_renders_task_and_footer(tmp_path):
    tasks = tmp_path / '.claude' / 'session-tasks'
    tasks.mkdir(parents=True)
    (tasks / 'sid-7.txt').write_text('WIP:Fix \\n escapes\nPREV:1:earlier work\n')
    payload = {
        'session_id': 'sid-7',
        'workspace': {'current_dir': '/a/b/myproj'},
        'context_window': {'used_percentage': 42.7},
        'cost': {'total_duration_ms': 5400000},
        'model': {'display_name': 'Haiku 4.5'},
    }
    r = _run_hook('session_statusline.sh', payload, tmp_path)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert '[WIP]' in lines[0] and 'Fix \\n escapes' in lines[0]
    assert '[DONE]' in lines[1] and 'earlier work' in lines[1]
    assert 'myproj' in lines[2] and 'ctx' in lines[2] and '42%' in lines[2]
    assert '1h30m' in lines[2] and 'Haiku 4.5' in lines[2]


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_statusline_falls_back_to_token_counts(tmp_path):
    payload = {
        'session_id': 'none',
        'cwd': '/a/b',
        'context_window': {'context_window_size': 200000,
                           'current_usage': {'input_tokens': 1000, 'cache_read_input_tokens': 99000}},
        'cost': {'total_duration_ms': 61000},
    }
    r = _run_hook('session_statusline.sh', payload, tmp_path)
    assert r.returncode == 0
    assert '50%' in r.stdout and 'starting...' in r.stdout


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_statusline_survives_garbage_input(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path))
    r = subprocess.run(['bash', os.path.join(SCRIPTS_DIR, 'session_statusline.sh')],
                       input='not json', capture_output=True, text=True, timeout=30, env=env)
    assert r.returncode == 0
    assert r.stderr == ''
    assert 'ctx' in r.stdout


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_stop_hook_wrapper_rotates_done_into_prev(tmp_path):
    """DONE on entry becomes PREV:1 and the current line is reset for the summarizer."""
    tasks = tmp_path / '.claude' / 'session-tasks'
    tasks.mkdir(parents=True)
    (tasks / 'sid-8.txt').write_text('DONE:Finished thing\nPREV:1:before\nPREV:2:way before\nPREV:3:ancient\n')
    transcript = tmp_path / 't.jsonl'
    transcript.write_text('{"type":"user","message":{"content":"hello there"}}\n')
    r = _run_hook('dynamic_task_update.sh',
                  {'session_id': 'sid-8', 'transcript_path': str(transcript), 'stop_hook_active': False},
                  tmp_path, env={'CLAUDE_TAB_BACKEND': 'keyword'})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == '{"continue":true,"suppressOutput":true}'
    # DONE rotated into PREV:1, then the keyword backend (run from the script's own
    # directory, not ~/.claude/scripts) wrote the new WIP line.
    assert (tasks / 'sid-8.txt').read_text().splitlines() == [
        'WIP:hello there', 'PREV:1:Finished thing', 'PREV:2:before', 'PREV:3:way before']


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_stop_hook_wrapper_respects_manual_and_recursion_guard(tmp_path):
    tasks = tmp_path / '.claude' / 'session-tasks'
    tasks.mkdir(parents=True)
    (tasks / 'sid-9.txt').write_text('MANUAL:pinned\n')
    transcript = tmp_path / 't.jsonl'
    transcript.write_text('{"type":"user","message":{"content":"hello there"}}\n')
    payload = {'session_id': 'sid-9', 'transcript_path': str(transcript), 'stop_hook_active': False}
    r = _run_hook('dynamic_task_update.sh', payload, tmp_path)
    assert r.stdout.strip() == '{"continue":true,"suppressOutput":true}'
    assert (tasks / 'sid-9.txt').read_text() == 'MANUAL:pinned\n'
    payload['stop_hook_active'] = True
    r = _run_hook('dynamic_task_update.sh', payload, tmp_path)
    assert r.returncode == 0 and 'continue' in r.stdout


# ---------------------------------------------------------------------------
# Plugin packaging
# ---------------------------------------------------------------------------

import re

REPO_DIR = os.path.join(os.path.dirname(__file__), '..')


def test_plugin_manifests_are_consistent():
    import json
    plugin = json.load(open(os.path.join(REPO_DIR, '.claude-plugin', 'plugin.json')))
    market = json.load(open(os.path.join(REPO_DIR, '.claude-plugin', 'marketplace.json')))
    assert plugin['name'] == 'tabtrack'  # commands are /tabtrack:task, /tabtrack:memo, ...
    assert plugin['version'] == market['metadata']['version']
    entry = market['plugins'][0]
    assert entry['name'] == 'claude-tab-tracking' and entry['source'] == './'
    for cmd in ('task', 'memo', 'recall', 'setup'):
        assert os.path.exists(os.path.join(REPO_DIR, 'commands', f'{cmd}.md'))


def test_plugin_hooks_reference_existing_scripts():
    import json
    hooks = json.load(open(os.path.join(REPO_DIR, 'hooks', 'hooks.json')))['hooks']
    assert set(hooks) == {'SessionStart', 'Stop', 'SessionEnd', 'SubagentStop', 'Notification'}  # no TaskCompleted: per-task, not per-session
    for event, rules in hooks.items():
        for rule in rules:
            for h in rule['hooks']:
                assert h['type'] == 'command'
                m = re.search(r'\$\{CLAUDE_PLUGIN_ROOT\}/(scripts/[\w.]+)', h['command'])
                assert m, h['command']
                path = os.path.join(REPO_DIR, m.group(1))
                assert os.path.exists(path) and os.access(path, os.X_OK), path


def test_no_hardcoded_home_scripts_path():
    """Plugin files must locate helpers relative to the plugin, not ~/.claude/scripts."""
    for name in os.listdir(os.path.join(REPO_DIR, 'scripts')):
        if not name.endswith(('.sh', '.py')):
            continue
        text = open(os.path.join(REPO_DIR, 'scripts', name), encoding='utf-8').read()
        assert '.claude/scripts/' not in text, name
    for name in ('task.md', 'memo.md', 'recall.md', 'setup.md'):
        text = open(os.path.join(REPO_DIR, 'commands', name), encoding='utf-8').read()
        assert 'python3 ~/.claude/scripts' not in text, name


@pytest.mark.skipif(shutil.which('claude') is None, reason='claude CLI not installed')
def test_claude_plugin_validate_passes():
    r = subprocess.run(['claude', 'plugin', 'validate', REPO_DIR], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_statusline_segment_mode_prints_only_task_line(tmp_path):
    tasks = tmp_path / '.claude' / 'session-tasks'
    tasks.mkdir(parents=True)
    (tasks / 'sid-10.txt').write_text('WIP:Segment task\nPREV:1:older\n')
    payload = {'session_id': 'sid-10', 'cwd': '/a/b', 'context_window': {'used_percentage': 10}}
    env = dict(os.environ, HOME=str(tmp_path))
    r = subprocess.run(['bash', os.path.join(SCRIPTS_DIR, 'session_statusline.sh'), '--segment'],
                       input=__import__('json').dumps(payload), capture_output=True, text=True, timeout=30, env=env)
    assert r.returncode == 0
    lines = r.stdout.splitlines()
    assert len(lines) == 1 and '[WIP]' in lines[0] and 'Segment task' in lines[0]
    r = _run_hook('session_statusline.sh', payload, tmp_path, env={'CLAUDE_TAB_SEGMENT': '1'})
    assert len(r.stdout.splitlines()) == 1


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_session_start_writes_plugin_launcher_and_hint(tmp_path):
    data_dir = tmp_path / 'plugin-data'
    r = _run_hook('session_start.sh', {'session_id': 'sid-11', 'cwd': str(tmp_path), 'source': 'startup'},
                  tmp_path, env={'CLAUDE_PLUGIN_DATA': str(data_dir)})
    assert r.returncode == 0, r.stderr
    launcher = data_dir / 'statusline.sh'
    assert launcher.exists() and os.access(launcher, os.X_OK)
    assert os.path.join(os.path.abspath(SCRIPTS_DIR), 'session_statusline.sh') in launcher.read_text()
    assert '/tabtrack:setup' in r.stdout  # no statusLine configured yet
    # The launcher works end to end
    tasks = tmp_path / '.claude' / 'session-tasks'
    (tasks / 'sid-11.txt').write_text('WIP:Via launcher\n')
    env = dict(os.environ, HOME=str(tmp_path))
    out = subprocess.run(['bash', str(launcher), '--segment'], input='{"session_id":"sid-11"}',
                         capture_output=True, text=True, timeout=30, env=env).stdout
    assert 'Via launcher' in out
    # Configured statusline: no hint
    settings = tmp_path / '.claude' / 'settings.json'
    settings.write_text('{"statusLine":{"type":"command","command":"%s"}}' % launcher)
    r = _run_hook('session_start.sh', {'session_id': 'sid-12', 'cwd': str(tmp_path), 'source': 'startup'},
                  tmp_path, env={'CLAUDE_PLUGIN_DATA': str(data_dir)})
    assert '/tabtrack:setup' not in r.stdout


def test_main_keyword_backend_writes_task(tmp_path, monkeypatch):
    """Regression: main() passes min_turns/tags to every backend; keyword_fallback
    must accept them or the zero-dependency path silently never writes."""
    import dynamic_task_update as d
    transcript = tmp_path / 't.jsonl'
    transcript.write_text('{"type":"user","message":{"content":"Fix the login bug please"}}\n')
    task_file = tmp_path / 'task.txt'
    monkeypatch.setenv('CLAUDE_TAB_BACKEND', 'keyword')
    monkeypatch.setattr(sys, 'argv', ['x', str(transcript), str(task_file)])
    monkeypatch.setattr(d, 'ERROR_LOG', str(tmp_path / 'err.log'))
    d.main()
    assert task_file.read_text().splitlines()[0] == 'WIP:Fix the login bug please'
    assert not (tmp_path / 'err.log').exists()


def test_cli_background_writes_when_generation_file_missing(tmp_path, monkeypatch):
    """SessionEnd (or a headless -p run) can remove sidecars before the helper
    finishes; a missing token must not be treated as superseded, or the last
    turn's task and memo are dropped."""
    task_file = tmp_path / 'task.txt'
    task_file.write_text('INIT:x\n')
    job_file = _write_job(tmp_path, task_file, generation='tok-1')
    cli_background = _mock_cli(monkeypatch, stdout='Final result')
    monkeypatch.setattr(sys, 'argv', ['cli_background.py', str(job_file)])
    cli_background.main()
    assert task_file.read_text().splitlines()[0] == 'WIP:Final result'


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_statusline_truncates_cjk_by_character_under_c_locale(tmp_path):
    tasks = tmp_path / '.claude' / 'session-tasks'
    tasks.mkdir(parents=True)
    task = '中' * 70
    (tasks / 'sid-13.txt').write_text(f'WIP:{task}\n')
    env = {k: v for k, v in os.environ.items() if k not in ('LANG', 'LC_ALL', 'LC_CTYPE')}
    env.update(HOME=str(tmp_path), LC_ALL='C')
    r = subprocess.run(['bash', os.path.join(SCRIPTS_DIR, 'session_statusline.sh'), '--segment'],
                       input='{"session_id":"sid-13"}', capture_output=True, text=True, timeout=30, env=env)
    assert r.returncode == 0
    line = r.stdout.splitlines()[0]
    assert '中' * 57 + '...' in line
    assert '中' * 58 not in line
    assert '\ufffd' not in line  # no broken multibyte sequence


# ---------------------------------------------------------------------------
# Phase 2: sessions overview, subagent memo, notifications
# ---------------------------------------------------------------------------

def _fake_claude_dir(tmp_path, session_id='sid-ov', pid=None, name='My session', status='busy',
                     cwd=None, task='WIP:Refactor the parser\nPREV:1:earlier\n', agents=(), memo=None):
    import json
    claude = tmp_path / '.claude'
    (claude / 'sessions').mkdir(parents=True, exist_ok=True)
    (claude / 'session-tasks').mkdir(exist_ok=True)
    cwd = cwd or str(tmp_path / 'proj')
    reg = {'pid': pid if pid is not None else os.getpid(), 'sessionId': session_id, 'cwd': cwd,
           'startedAt': int(time.time() * 1000) - 600000, 'name': name, 'status': status,
           'statusUpdatedAt': int(time.time() * 1000) - 5000, 'entrypoint': 'cli', 'kind': 'interactive'}
    (claude / 'sessions' / f'{reg["pid"]}.json').write_text(json.dumps(reg))
    if task is not None:
        (claude / 'session-tasks' / f'{session_id}.txt').write_text(task)
    proj_dir = claude / 'projects' / re.sub(r'[^A-Za-z0-9]', '-', cwd)
    (proj_dir / session_id / 'subagents').mkdir(parents=True, exist_ok=True)
    (proj_dir / f'{session_id}.jsonl').write_text('{}\n')
    for i, (desc, running) in enumerate(agents):
        meta = proj_dir / session_id / 'subagents' / f'agent-a{i}.meta.json'
        meta.write_text(json.dumps({'agentType': 'general-purpose', 'description': desc}))
        jsonl = proj_dir / session_id / 'subagents' / f'agent-a{i}.jsonl'
        jsonl.write_text('{}\n')
        if not running:
            old = time.time() - 3600
            os.utime(jsonl, (old, old))
    if memo:
        from dynamic_task_update import resolve_project_name
        mdir = claude / 'memos' / resolve_project_name(cwd)
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / (time.strftime('%Y-%m-%d') + '.md')).write_text(memo)
    return claude


import time


def _run_overview(claude_dir, *args):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(claude_dir), HOME=str(claude_dir.parent))
    return subprocess.run([sys.executable, os.path.join(SCRIPTS_DIR, 'sessions_overview.py'), *args],
                          capture_output=True, text=True, timeout=30, env=env)


def test_sessions_overview_joins_registry_task_agents_and_memo(tmp_path):
    (tmp_path / 'proj').mkdir()
    claude = _fake_claude_dir(tmp_path, agents=[('Search GitHub for repos', True), ('Old finished job', False)],
                              memo='# today\n\n## 10:00 | Refactor the parser\n- 【决策】use a tokenizer\n')
    r = _run_overview(claude, '--self', 'sid-ov')
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert '1 live session(s) · 1 busy' in out
    assert '▶ [busy] My session' in out and 'proj' in out
    assert '[WIP]  Refactor the parser' in out
    assert 'agents 1 running / 2 total' in out
    assert '◐ general-purpose: Search GitHub for repos' in out
    assert 'Old finished job' not in out
    assert 'memo   1 entries today · last: Refactor the parser' in out


def test_sessions_overview_hides_dead_sessions_unless_all(tmp_path):
    (tmp_path / 'proj').mkdir()
    claude = _fake_claude_dir(tmp_path, session_id='dead', pid=2**22 - 1, name='Gone')
    r = _run_overview(claude)
    assert 'No live Claude Code sessions found.' in r.stdout
    r = _run_overview(claude, '--all')
    assert 'Gone' in r.stdout


def test_sessions_overview_json(tmp_path):
    import json
    (tmp_path / 'proj').mkdir()
    claude = _fake_claude_dir(tmp_path, task='MANUAL:pinned\n')
    r = _run_overview(claude, '--json')
    data = json.loads(r.stdout)
    assert data[0]['badge'] == 'SET' and data[0]['task'] == 'pinned'
    assert data[0]['session_id'] == 'sid-ov'


def _subagent_payload(tmp_path, seconds=120, description='Find auth code', session_id='sid-sa'):
    import json
    from datetime import datetime, timedelta
    sub = tmp_path / 'subagents'
    sub.mkdir(exist_ok=True)
    (sub / 'agent-a1.meta.json').write_text(json.dumps({'agentType': 'Explore', 'description': description}))
    t0 = datetime(2026, 9, 25, 10, 0, 0)
    lines = [json.dumps({'timestamp': (t0 + timedelta(seconds=s)).strftime('%Y-%m-%dT%H:%M:%S.000Z')})
             for s in (0, seconds)]
    (sub / 'agent-a1.jsonl').write_text('\n'.join(lines) + '\n')
    return {'session_id': session_id, 'agent_id': 'a1', 'agent_type': 'Explore',
            'agent_transcript_path': str(sub / 'agent-a1.jsonl'), 'cwd': str(tmp_path / 'proj')}


def _run_subagent_hook(tmp_path, payload, extra_env=None):
    import json
    env = dict(os.environ, HOME=str(tmp_path), **(extra_env or {}))
    return subprocess.run(['bash', os.path.join(SCRIPTS_DIR, 'subagent_stop.sh')], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=30, env=env)


def test_subagent_stop_files_bullet_under_current_task(tmp_path):
    from dynamic_task_update import resolve_project_name
    (tmp_path / 'proj').mkdir()
    tasks = tmp_path / '.claude' / 'session-tasks'
    tasks.mkdir(parents=True)
    (tasks / 'sid-sa.txt').write_text('WIP:Fix the login bug\n')
    payload = _subagent_payload(tmp_path)
    r = _run_subagent_hook(tmp_path, payload)
    assert r.returncode == 0 and r.stdout == ''
    project = resolve_project_name(str(tmp_path / 'proj'))
    memo = (tmp_path / '.claude' / 'memos' / project / (time.strftime('%Y-%m-%d') + '.md')).read_text()
    assert '| Fix the login bug' in memo
    assert '- 【子代理】Explore「Find auth code」 · 2m00s' in memo
    # A second agent for the same task merges into the same entry
    payload2 = _subagent_payload(tmp_path, seconds=45, description='Check tests')
    payload2['agent_id'] = 'a1'
    _run_subagent_hook(tmp_path, payload2)
    memo = (tmp_path / '.claude' / 'memos' / project / (time.strftime('%Y-%m-%d') + '.md')).read_text()
    assert memo.count('## ') == 1
    assert '「Check tests」 · 45s' in memo


def test_subagent_stop_skips_trivial_agents_and_respects_config(tmp_path):
    (tmp_path / 'proj').mkdir()
    tasks = tmp_path / '.claude' / 'session-tasks'
    tasks.mkdir(parents=True)
    (tasks / 'sid-sa.txt').write_text('WIP:Fix the login bug\n')
    memos = tmp_path / '.claude' / 'memos'
    _run_subagent_hook(tmp_path, _subagent_payload(tmp_path, seconds=5))
    assert not memos.exists() or not list(memos.rglob('*.md'))
    memos.mkdir(parents=True, exist_ok=True)
    (memos / 'config.yaml').write_text('memo_subagents: false\n')
    _run_subagent_hook(tmp_path, _subagent_payload(tmp_path, seconds=300))
    assert not list(memos.rglob('*.md'))


def test_load_memo_config_parses_memo_subagents(tmp_path):
    from dynamic_task_update import load_memo_config
    cfg = tmp_path / 'config.yaml'
    cfg.write_text('memo_subagents: false\n')
    assert load_memo_config(str(cfg))['memo_subagents'] is False
    cfg.write_text('memo_subagents: true\n')
    assert load_memo_config(str(cfg))['memo_subagents'] is True
    assert load_memo_config(str(tmp_path / 'missing.yaml'))['memo_subagents'] is True


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_notify_is_silent_unless_enabled(tmp_path):
    import json
    payload = {'session_id': 'x', 'notification_type': 'idle_prompt', 'message': 'waiting', 'cwd': '/a/b'}
    env = dict(os.environ, HOME=str(tmp_path))
    env.pop('CLAUDE_PLUGIN_OPTION_NOTIFICATIONS', None)
    env.pop('CLAUDE_TAB_NOTIFY', None)
    r = subprocess.run(['bash', os.path.join(SCRIPTS_DIR, 'notify.sh')], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=30, env=env)
    assert r.returncode == 0 and r.stdout == '' and r.stderr == ''
    # Enabled but no notifier on PATH: still exits 0 quietly
    env.update(CLAUDE_PLUGIN_OPTION_NOTIFICATIONS='true', PATH='/nonexistent')
    r = subprocess.run(['/bin/bash', os.path.join(SCRIPTS_DIR, 'notify.sh')], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=30, env=env)
    assert r.returncode == 0 and r.stdout == ''


# ---------------------------------------------------------------------------
# Phase 3: budgeted recall, redaction, handoff anchor, MEMORY.md pointer
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta


def _memo_tree(tmp_path, files):
    """files: {(project, day): text}"""
    base = tmp_path / 'memos'
    for (proj, day), text in files.items():
        (base / proj).mkdir(parents=True, exist_ok=True)
        (base / proj / f'{day}.md').write_text(text)
    return base


def test_recall_scoring_half_life_and_tags(tmp_path):
    import memo_recall as mr
    now = datetime(2026, 9, 25, 12, 0)
    base = _memo_tree(tmp_path, {
        ('p', '2026-09-25'): '# d\n\n## 10:00 | fresh\n- 【决策】a\n- 【数据】b\n',
        ('p', '2026-06-27'): '# d\n\n## 10:00 | old\n- 【决策】c\n- 【数据】d\n',  # 90 days ago
    })
    entries = {e.title: e for e in mr.load_entries(str(base), 'p', None, now=now)}
    fresh, old = entries['fresh'], entries['old']
    # decision 1.0 + data 0.4, both × auto source 0.5 → 0.7
    assert abs(fresh.score - 0.7) < 0.01
    # 90 days: decision halves (0.25), data ~0 (0.4×0.5×0.5^(90/14) ≈ 0.002)
    assert 0.25 < old.score < 0.26


def test_recall_open_todo_does_not_decay_and_closed_is_ignored(tmp_path):
    import memo_recall as mr
    now = datetime(2026, 9, 25, 12, 0)
    base = _memo_tree(tmp_path, {
        ('p', '2026-03-01'): '# d\n\n## 09:00 | todos\n- 【TODO】ship it\n- 【TODO】[x] already done\n',
    })
    e = mr.load_entries(str(base), 'p', None, now=now)[0]
    assert abs(e.score - (0.5 + 0.05)) < 0.001


def test_recall_marks_superseded_decisions(tmp_path):
    import memo_recall as mr
    base = _memo_tree(tmp_path, {
        ('p', '2026-09-20'): '# d\n\n## 09:00 | first\n- 【决策】用 Postgres 存索引数据\n',
        ('p', '2026-09-24'): '# d\n\n## 09:00 | second\n- 【决策】改用 SQLite 存索引数据\n',
        ('q', '2026-09-24'): '# d\n\n## 09:00 | other project\n- 【决策】用 Postgres 存索引数据\n',
    })
    entries = mr.load_entries(str(base), None, None, now=datetime(2026, 9, 25))
    by_id = {e.id: e for e in entries}
    assert by_id['p/2026-09-20#1'].bullets[0].superseded_by == 'p/2026-09-24#1'
    assert by_id['p/2026-09-24#1'].bullets[0].superseded_by is None
    assert by_id['q/2026-09-24#1'].bullets[0].superseded_by is None  # projects are independent
    assert 'superseded by p/2026-09-24#1' in mr.render_show([by_id['p/2026-09-20#1']])


def test_recall_manual_notes_outrank_hook_bullets(tmp_path):
    import memo_recall as mr
    now = datetime(2026, 9, 25, 12, 0)
    base = _memo_tree(tmp_path, {
        ('p', '2026-09-25'): '# d\n\n## 10:00 | a\n- 【决策】auto\n\n## 11:00 | b\n- 【手记】manual\n',
    })
    scores = {e.title: e.score for e in mr.load_entries(str(base), 'p', None, now=now)}
    assert abs(scores['b'] - 1.0) < 0.01 and abs(scores['a'] - 0.5) < 0.01


def test_recall_budget_selection_and_index_of_rest(tmp_path):
    import memo_recall as mr
    now = datetime(2026, 9, 25, 12, 0)
    big = '- 【数据】' + 'x' * 400
    base = _memo_tree(tmp_path, {
        ('p', '2026-09-25'): f'# d\n\n## 09:00 | cheap decision\n- 【决策】keep\n\n## 10:00 | expensive data\n{big}\n',
    })
    entries = mr.load_entries(str(base), 'p', None, now=now)
    chosen, rest = mr.select_within_budget(entries, budget=100)
    assert [e.title for e in chosen] == ['cheap decision']
    assert [e.title for e in rest] == ['expensive data']
    out = mr.render_auto(entries, 100)
    assert 'loaded 1' in out and '## 09:00 | cheap decision' in out
    assert 'Not loaded (1)' in out and 'p/2026-09-25#2' in out
    assert 'x' * 100 not in out  # the expensive body is not loaded
    # No budget: everything
    chosen, rest = mr.select_within_budget(entries, budget=0)
    assert len(chosen) == 2 and not rest


def test_recall_cli_index_show_add(tmp_path, monkeypatch):
    import memo_recall as mr
    base = _memo_tree(tmp_path, {
        ('p', '2026-09-25'): '# d\n\n## 09:00 | one\n- 【决策】keep\n',
    })
    monkeypatch.setenv('PWD', str(tmp_path))
    out = []
    monkeypatch.setattr('builtins.print', lambda *a, **k: out.append(' '.join(str(x) for x in a)))
    assert mr.main(['index', '--project', 'all', '--days', '3650'], memo_base_dir=str(base)) == 0
    assert 'p/2026-09-25#1' in out[-1] and '决策×1' in out[-1]
    assert mr.main(['show', 'p/2026-09-25#1'], memo_base_dir=str(base)) == 0
    assert '- 【决策】keep' in out[-1]
    assert mr.main(['add', '--project', 'p', '--task', 'one', 'remember this'], memo_base_dir=str(base)) == 0
    text = (base / 'p' / f'{datetime.now():%Y-%m-%d}.md').read_text()
    assert '- 【手记】remember this' in text
    assert mr.main(['bogus'], memo_base_dir=str(base)) == 1


def test_redact_secrets_masks_credentials_and_keeps_prose():
    from dynamic_task_update import redact_secrets
    s = redact_secrets('key sk-ant-api03-abcdefghijklmnop123 and AKIAABCDEFGHIJKLMNOP and password=hunter22 and token: "abcdefgh"')
    assert 'sk-ant' not in s and 'AKIA' not in s and 'hunter22' not in s and 'abcdefgh' not in s
    assert s.count('[REDACTED]') == 4
    assert redact_secrets('普通决策：用 sqlite 存索引') == '普通决策：用 sqlite 存索引'
    assert redact_secrets('') == ''
    assert 'ghp_' not in redact_secrets('push with ghp_abcdefghijklmnopqrstuvwxyz0123')
    assert 'PRIVATE KEY-----' not in redact_secrets('-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----')


def test_write_memo_redacts_before_writing(tmp_path):
    from dynamic_task_update import write_memo
    write_memo('【数据】api_key=sk-ant-api03-zzzzzzzzzzzzzzzz', 'token=abcdefgh123 setup', 'p', str(tmp_path))
    text = (tmp_path / 'p' / f'{datetime.now():%Y-%m-%d}.md').read_text()
    assert 'sk-ant' not in text and 'abcdefgh123' not in text
    assert '[REDACTED]' in text


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_handoff_anchor_written_and_replayed(tmp_path):
    import json
    proj = tmp_path / 'proj'
    proj.mkdir()
    _run_hook('session_start.sh', {'session_id': 'h1', 'cwd': str(proj), 'source': 'startup'}, tmp_path)
    tasks = tmp_path / '.claude' / 'session-tasks'
    (tasks / 'h1.txt').write_text('WIP:Migrate the parser to SQLite\n')
    r = _run_hook('session_end.sh', {'session_id': 'h1', 'cwd': str(proj)}, tmp_path)
    assert r.returncode == 0, r.stderr
    handoff = next(tasks.glob('handoff_*.json'))
    data = json.loads(handoff.read_text())
    assert data['task'] == 'Migrate the parser to SQLite' and data['head'] == ''  # not a git repo
    # Next startup in the same directory replays it
    r = _run_hook('session_start.sh', {'session_id': 'h2', 'cwd': str(proj), 'source': 'startup'}, tmp_path)
    assert 'Last session in this directory' in r.stdout and 'Migrate the parser to SQLite' in r.stdout
    # A different HEAD (simulate by editing the anchor) suppresses the replay
    data['head'] = 'deadbeef'
    handoff.write_text(json.dumps(data))
    r = _run_hook('session_start.sh', {'session_id': 'h3', 'cwd': str(proj), 'source': 'startup'}, tmp_path)
    assert 'Last session in this directory' not in r.stdout
    # INIT placeholders are never recorded
    (tasks / 'h4.txt').write_text('INIT:proj\n')
    handoff.unlink()
    _run_hook('session_end.sh', {'session_id': 'h4', 'cwd': str(proj)}, tmp_path)
    assert not list(tasks.glob('handoff_*.json'))


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_memory_md_pointer_added_once_and_only_when_memos_exist(tmp_path):
    proj = tmp_path / 'my-proj'
    proj.mkdir()
    encoded = re.sub(r'[^A-Za-z0-9]', '-', str(proj))
    memory_md = tmp_path / '.claude' / 'projects' / encoded / 'memory' / 'MEMORY.md'
    memory_md.parent.mkdir(parents=True)
    memory_md.write_text('# Memory Index\n\n- [something](something.md) — x\n')
    payload = {'session_id': 'm1', 'cwd': str(proj), 'source': 'startup'}
    # No memos for this project yet: no pointer
    _run_hook('session_start.sh', payload, tmp_path)
    assert 'claude-tab-tracking' not in memory_md.read_text()
    (tmp_path / '.claude' / 'memos' / 'my-proj').mkdir(parents=True)
    _run_hook('session_start.sh', payload, tmp_path)
    _run_hook('session_start.sh', payload, tmp_path)
    text = memory_md.read_text()
    assert text.count('claude-tab-tracking') == 1
    assert '~/.claude/memos/my-proj/' in text and text.startswith('# Memory Index')
    # Opt out
    (tmp_path / '.claude' / 'memos' / 'config.yaml').write_text('memory_pointer: false\n')
    memory_md.write_text('# Memory Index\n')
    _run_hook('session_start.sh', payload, tmp_path)
    assert 'claude-tab-tracking' not in memory_md.read_text()


@pytest.mark.skipif(not _HAS_JQ, reason='jq not installed')
def test_memory_md_pointer_uses_general_for_home_dir(tmp_path):
    """Home is project "general" in Python; the bash side must agree or the pointer never lands."""
    encoded = re.sub(r'[^A-Za-z0-9]', '-', str(tmp_path))
    memory_md = tmp_path / '.claude' / 'projects' / encoded / 'memory' / 'MEMORY.md'
    memory_md.parent.mkdir(parents=True)
    memory_md.write_text('# Memory Index\n')
    (tmp_path / '.claude' / 'memos' / 'general').mkdir(parents=True)
    _run_hook('session_start.sh', {'session_id': 'm2', 'cwd': str(tmp_path), 'source': 'startup'}, tmp_path)
    assert '~/.claude/memos/general/' in memory_md.read_text()


def test_api_key_ignores_environment_inside_plugin(monkeypatch):
    import dynamic_task_update as d
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'env-key-should-not-be-used')
    monkeypatch.delenv('CLAUDE_PLUGIN_OPTION_ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setenv('CLAUDE_PLUGIN_ROOT', '/x/plugin')
    assert d._api_key() == ''
    monkeypatch.setenv('CLAUDE_PLUGIN_OPTION_ANTHROPIC_API_KEY', 'option-key')
    assert d._api_key() == 'option-key'
    monkeypatch.delenv('CLAUDE_PLUGIN_OPTION_ANTHROPIC_API_KEY')
    monkeypatch.delenv('CLAUDE_PLUGIN_ROOT')
    assert d._api_key() == 'env-key-should-not-be-used'  # manual install keeps the env fallback


def test_parse_llm_response_accepts_trailing_done_marker():
    from dynamic_task_update import parse_llm_response
    task, done, _ = parse_llm_response('任务：执行精确指定的文本回复指令。[完成]')
    assert done and task == '执行精确指定的文本回复指令'
    task, done, _ = parse_llm_response('Ship the release [done]')
    assert done and task == 'Ship the release'
    task, done, _ = parse_llm_response('Still working on the parser')
    assert not done and task == 'Still working on the parser'
