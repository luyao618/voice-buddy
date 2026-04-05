import json
import os
from voice_buddy.injector import process_stop_event, extract_last_assistant_message, _should_trigger


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

def test_process_stop_event_triggers(tmp_path, capsys):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "assistant", "content": "I have implemented the feature and created 3 files."}\n',
        encoding="utf-8",
    )
    data = {"hook_event_name": "Stop", "transcript_path": str(transcript)}

    import pytest
    with pytest.raises(SystemExit) as exc_info:
        process_stop_event(data)
    assert exc_info.value.code == 2

    captured = capsys.readouterr()
    assert "voice-buddy agent" in captured.err


def test_process_stop_event_stays_silent(tmp_path, capsys):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "assistant", "content": "The answer is 42."}\n',
        encoding="utf-8",
    )
    data = {"hook_event_name": "Stop", "transcript_path": str(transcript)}

    process_stop_event(data)

    captured = capsys.readouterr()
    assert captured.out == ""


def test_process_stop_event_missing_transcript(capsys):
    data = {"hook_event_name": "Stop", "transcript_path": "/nonexistent/file"}

    process_stop_event(data)

    captured = capsys.readouterr()
    assert captured.out == ""
