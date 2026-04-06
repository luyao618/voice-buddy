import json
import os
import pytest
from voice_buddy.injector import process_stop_event, extract_last_assistant_message, _should_trigger


# --- Default user_config for tests ---

def _make_config(**kwargs):
    base = {
        "style": "cute-girl",
        "nickname": "Master",
        "enabled": True,
        "events": {"stop": True},
        "persona_override": None,
    }
    base.update(kwargs)
    return base


# --- Transcript parsing ---

def test_extract_last_assistant_message_from_simple_jsonl(tmp_path):
    """Simple JSONL format: {"role": "assistant", "content": "string"}"""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "user", "content": "fix the bug"}\n'
        '{"role": "assistant", "content": "I have fixed the bug in utils.py and updated the tests."}\n',
        encoding="utf-8",
    )
    result = extract_last_assistant_message(str(transcript))
    assert result == "I have fixed the bug in utils.py and updated the tests."


def test_extract_last_assistant_message_claude_code_format(tmp_path):
    """Claude Code format: {"type": "assistant", "message": {"role": "assistant", "content": [blocks]}}"""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"type": "user", "message": {"role": "user", "content": "fix the bug"}}\n'
        '{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "I have fixed the bug and updated tests."}]}}\n',
        encoding="utf-8",
    )
    result = extract_last_assistant_message(str(transcript))
    assert result == "I have fixed the bug and updated tests."


def test_extract_last_assistant_message_multiple_messages(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "assistant", "content": "Let me look at the code."}\n'
        '{"role": "user", "content": "ok"}\n'
        '{"role": "assistant", "content": "Done! I have implemented the feature and created 3 new files."}\n',
        encoding="utf-8",
    )
    result = extract_last_assistant_message(str(transcript))
    assert result == "Done! I have implemented the feature and created 3 new files."


def test_extract_last_assistant_message_no_assistant(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "user", "content": "hello"}\n',
        encoding="utf-8",
    )
    result = extract_last_assistant_message(str(transcript))
    assert result is None


def test_extract_last_assistant_message_missing_file():
    result = extract_last_assistant_message("/nonexistent/path/transcript.jsonl")
    assert result is None


# --- Trigger criteria ---

def test_should_trigger_completion_keyword():
    assert _should_trigger("I have implemented the new feature.") is True
    assert _should_trigger("Bug fixed in parser.py.") is True
    assert _should_trigger("Done! All changes committed.") is True
    assert _should_trigger("Created the config file.") is True
    assert _should_trigger("Refactored the module.") is True
    assert _should_trigger("Updated the tests.") is True


def test_should_trigger_chinese_keywords():
    assert _should_trigger("已经完成了所有修改。") is True
    assert _should_trigger("帮你修复了这个问题。") is True
    assert _should_trigger("搞定了！") is True
    assert _should_trigger("创建了新的配置文件。") is True


def test_should_trigger_file_modification():
    assert _should_trigger("I wrote to src/main.py and updated tests.") is True
    assert _should_trigger("Created file config.json.") is True


def test_should_not_trigger_casual_qa():
    assert _should_trigger("The answer is 42.") is False
    assert _should_trigger("Yes, you can use async/await for that.") is False
    assert _should_trigger("Here are three approaches to consider:") is False


def test_should_not_trigger_design_discussion():
    assert _should_trigger("I recommend option B because it's simpler.") is False
    assert _should_trigger("Let me explain how the architecture works.") is False


# --- Full process ---

def test_process_stop_event_triggers(tmp_path, capfd):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "assistant", "content": "I have implemented the feature and created 3 files."}\n',
        encoding="utf-8",
    )
    data = {"hook_event_name": "Stop", "transcript_path": str(transcript)}

    process_stop_event(data, _make_config())

    captured = capfd.readouterr()
    output = json.loads(captured.out)
    assert output["decision"] == "block"
    assert "additionalContext" in output["hookSpecificOutput"]


def test_process_stop_event_prefers_last_assistant_message(capfd):
    """When last_assistant_message is in hook input, use it directly (no transcript read)."""
    data = {
        "hook_event_name": "Stop",
        "transcript_path": "/nonexistent/file",
        "last_assistant_message": "I have fixed the bug and updated 3 test files.",
    }

    process_stop_event(data, _make_config())

    captured = capfd.readouterr()
    output = json.loads(captured.out)
    assert output["decision"] == "block"
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert "fixed the bug" in ctx


def test_process_stop_event_stays_silent(tmp_path, capfd):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "assistant", "content": "The answer is 42."}\n',
        encoding="utf-8",
    )
    data = {"hook_event_name": "Stop", "transcript_path": str(transcript)}

    process_stop_event(data, _make_config())

    captured = capfd.readouterr()
    assert captured.out == ""


def test_process_stop_event_missing_transcript(capfd):
    data = {"hook_event_name": "Stop", "transcript_path": "/nonexistent/file"}

    process_stop_event(data, _make_config())

    captured = capfd.readouterr()
    assert captured.out == ""


def test_process_stop_event_skips_when_stop_hook_active(tmp_path, capfd):
    """When stop_hook_active is true, injector must NOT re-trigger (avoid loop)."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "assistant", "content": "I have implemented the feature."}\n',
        encoding="utf-8",
    )
    data = {
        "hook_event_name": "Stop",
        "transcript_path": str(transcript),
        "stop_hook_active": True,
    }

    # Should just return silently
    process_stop_event(data, _make_config())

    captured = capfd.readouterr()
    assert captured.out == ""


def test_process_stop_event_outputs_json_with_style(tmp_path, capfd):
    """Stdout output must be valid JSON with hookSpecificOutput containing additionalContext."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "assistant", "content": "I have fixed the bug and updated tests."}\n',
        encoding="utf-8",
    )
    data = {"transcript_path": str(transcript)}
    user_config = _make_config(style="kawaii", nickname="Senpai")

    process_stop_event(data, user_config)

    captured = capfd.readouterr()
    output = json.loads(captured.out)
    assert output["decision"] == "block"
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert "kawaii" in ctx
    assert "Senpai" in ctx


def test_process_stop_event_includes_nickname_in_context(tmp_path, capfd):
    """additionalContext must include nickname, style, and subagent_tts command."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "assistant", "content": "I have completed the implementation."}\n',
        encoding="utf-8",
    )
    data = {"transcript_path": str(transcript)}
    user_config = _make_config(style="secretary", nickname="Boss")

    process_stop_event(data, user_config)

    captured = capfd.readouterr()
    output = json.loads(captured.out)
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert "Boss" in ctx
    assert "secretary" in ctx
    assert "subagent_tts" in ctx


def test_process_stop_event_persona_override_null(tmp_path, capfd):
    """When persona_override is None, additionalContext should contain 'null'."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "assistant", "content": "Done! I have updated the config file."}\n',
        encoding="utf-8",
    )
    data = {"transcript_path": str(transcript)}
    user_config = _make_config(persona_override=None)

    process_stop_event(data, user_config)

    captured = capfd.readouterr()
    output = json.loads(captured.out)
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert "null" in ctx


def test_process_stop_event_persona_override_set(tmp_path, capfd):
    """When persona_override is set, it appears in additionalContext."""
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "assistant", "content": "Done! I have refactored the module."}\n',
        encoding="utf-8",
    )
    data = {"transcript_path": str(transcript)}
    user_config = _make_config(persona_override="Be extra cheerful today")

    process_stop_event(data, user_config)

    captured = capfd.readouterr()
    output = json.loads(captured.out)
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert "Be extra cheerful today" in ctx
