from voice_buddy.context import analyze_context, ContextResult


# --- PreToolUse: whitelist filtering ---

def test_pretooluse_git_commit():
    data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'fix bug'"},
    }
    result = analyze_context(data)
    assert result is not None
    assert result.event == "pretooluse"
    assert result.sub_event == "git_commit"


def test_pretooluse_git_push():
    data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main"},
    }
    result = analyze_context(data)
    assert result is not None
    assert result.sub_event == "git_push"


def test_pretooluse_pytest():
    data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "python -m pytest tests/ -v"},
    }
    result = analyze_context(data)
    assert result is not None
    assert result.sub_event == "test_run"


def test_pretooluse_npm_test():
    data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
    }
    result = analyze_context(data)
    assert result is not None
    assert result.sub_event == "test_run"


def test_pretooluse_non_whitelisted_returns_none():
    data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"},
    }
    result = analyze_context(data)
    assert result is None


def test_pretooluse_non_bash_tool_returns_none():
    data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/some/file.py"},
    }
    result = analyze_context(data)
    assert result is None


# --- PostToolUse: filtered by tool + output ---

def test_posttooluse_test_passed():
    data = {
        "hook_event_name": "PostToolUse",
        "inputs": {"command": "python -m pytest"},
        "response": "===== 42 passed in 3.21s =====",
    }
    result = analyze_context(data)
    assert result is not None
    assert result.event == "posttooluse"
    assert result.sub_event == "test_passed"


def test_posttooluse_test_failed():
    data = {
        "hook_event_name": "PostToolUse",
        "inputs": {"command": "npm test"},
        "response": "Tests: 3 failed, 10 passed, 13 total",
    }
    result = analyze_context(data)
    assert result is not None
    assert result.sub_event == "test_failed"


def test_posttooluse_git_success():
    data = {
        "hook_event_name": "PostToolUse",
        "inputs": {"command": "git push origin main"},
        "response": "To github.com:user/repo.git\n  abc1234..def5678  main -> main",
    }
    result = analyze_context(data)
    assert result is not None
    assert result.sub_event == "git_success"


def test_posttooluse_read_tool_returns_none():
    data = {
        "hook_event_name": "PostToolUse",
        "inputs": {"file_path": "/some/file.py"},
        "response": "file contents here...",
    }
    result = analyze_context(data)
    assert result is None


def test_posttooluse_unrecognized_bash_returns_none():
    data = {
        "hook_event_name": "PostToolUse",
        "inputs": {"command": "ls -la"},
        "response": "total 48\ndrwxr-xr-x  6 user  staff  192 Apr  5 01:01 .",
    }
    result = analyze_context(data)
    assert result is None


# --- PostToolUseFailure: only Bash ---

def test_posttoolusefailure_bash_error():
    data = {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Bash",
        "error": "Command failed with exit code 1",
        "error_type": "command_error",
    }
    result = analyze_context(data)
    assert result is not None
    assert result.event == "posttoolusefailure"
    assert result.sub_event == "default"


def test_posttoolusefailure_bash_timeout():
    data = {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Bash",
        "error": "Command timed out",
        "error_type": "timeout",
    }
    result = analyze_context(data)
    assert result is not None
    assert result.sub_event == "timeout"


def test_posttoolusefailure_read_tool_returns_none():
    data = {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Read",
        "error": "File not found",
        "error_type": "file_not_found",
    }
    result = analyze_context(data)
    assert result is None


# --- SessionStart / SessionEnd ---

def test_sessionstart():
    data = {"hook_event_name": "SessionStart", "source": "startup"}
    result = analyze_context(data)
    assert result is not None
    assert result.event == "sessionstart"
    assert result.sub_event == "default"


def test_sessionend():
    data = {"hook_event_name": "SessionEnd"}
    result = analyze_context(data)
    assert result is not None
    assert result.event == "sessionend"
    assert result.sub_event == "default"


# --- Stop: returns None (handled by injector) ---

def test_stop_returns_none():
    data = {"hook_event_name": "Stop", "transcript_path": "/tmp/transcript"}
    result = analyze_context(data)
    assert result is None
