import json
from unittest.mock import patch, MagicMock
from voice_buddy.main import handle_hook_event


def test_handle_sessionstart_calls_tts_pipeline(tmp_path):
    data = {"hook_event_name": "SessionStart", "source": "startup"}

    with patch("voice_buddy.main.synthesize_to_file", return_value="/tmp/audio.mp3") as mock_tts, \
         patch("voice_buddy.main.play_audio", return_value=True) as mock_play:
        handle_hook_event(data)
        mock_tts.assert_called_once()
        mock_play.assert_called_once_with("/tmp/audio.mp3")


def test_handle_pretooluse_whitelisted_calls_tts():
    data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'test'"},
    }

    with patch("voice_buddy.main.synthesize_to_file", return_value="/tmp/audio.mp3") as mock_tts, \
         patch("voice_buddy.main.play_audio", return_value=True):
        handle_hook_event(data)
        mock_tts.assert_called_once()


def test_handle_pretooluse_non_whitelisted_stays_silent():
    data = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"},
    }

    with patch("voice_buddy.main.synthesize_to_file") as mock_tts, \
         patch("voice_buddy.main.play_audio"):
        handle_hook_event(data)
        mock_tts.assert_not_called()


def test_handle_posttooluse_read_tool_stays_silent():
    data = {
        "hook_event_name": "PostToolUse",
        "inputs": {"file_path": "/some/file.py"},
        "response": "file contents...",
    }

    with patch("voice_buddy.main.synthesize_to_file") as mock_tts, \
         patch("voice_buddy.main.play_audio"):
        handle_hook_event(data)
        mock_tts.assert_not_called()


def test_handle_posttoolusefailure_non_bash_stays_silent():
    data = {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Read",
        "error": "File not found",
        "error_type": "file_not_found",
    }

    with patch("voice_buddy.main.synthesize_to_file") as mock_tts, \
         patch("voice_buddy.main.play_audio"):
        handle_hook_event(data)
        mock_tts.assert_not_called()


def test_handle_stop_calls_injector():
    data = {
        "hook_event_name": "Stop",
        "transcript_path": "/tmp/transcript.json",
    }

    with patch("voice_buddy.main.handle_stop_event") as mock_injector:
        handle_hook_event(data)
        mock_injector.assert_called_once_with(data)


def test_handle_tts_failure_does_not_crash():
    data = {"hook_event_name": "SessionStart", "source": "startup"}

    with patch("voice_buddy.main.synthesize_to_file", return_value=None) as mock_tts, \
         patch("voice_buddy.main.play_audio") as mock_play:
        handle_hook_event(data)  # Should not raise
        mock_tts.assert_called_once()
        mock_play.assert_not_called()
