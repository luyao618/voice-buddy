import json
import pytest
from unittest.mock import patch, MagicMock
from voice_buddy.main import handle_hook_event


@pytest.fixture(autouse=True)
def supervisor():
    with patch("voice_buddy.listener_supervisor.ensure_listener_for_session") as start, \
         patch("voice_buddy.listener_supervisor.release_session") as end:
        yield start, end


def test_handle_sessionstart_plays_prepackaged_audio():
    data = {"hook_event_name": "SessionStart"}
    user_config = {
        "style": "cute-girl", "nickname": "Master", "enabled": True,
        "events": {"sessionstart": True, "sessionend": True,
                   "notification": True, "stop": True},
        "persona_override": None,
    }

    with patch("voice_buddy.main.load_user_config", return_value=user_config), \
         patch("voice_buddy.main.select_response") as mock_resp, \
         patch("voice_buddy.main.resolve_audio_path", return_value="/tmp/cached.mp3") as mock_resolve, \
         patch("voice_buddy.main.play_audio", return_value=True) as mock_play, \
         patch("voice_buddy.main.synthesize_to_file") as mock_tts:
        mock_resp.return_value = MagicMock(text="Hello!", audio_id="sessionstart_01")
        handle_hook_event(data)
        mock_resolve.assert_called_once_with("cute-girl", "sessionstart_01")
        mock_play.assert_called_once_with("/tmp/cached.mp3")
        mock_tts.assert_not_called()  # Should NOT call TTS for pre-packaged


def test_handle_sessionstart_fallback_to_tts_when_no_audio():
    data = {"hook_event_name": "SessionStart"}
    user_config = {
        "style": "cute-girl", "nickname": "Master", "enabled": True,
        "events": {"sessionstart": True, "sessionend": True,
                   "notification": True, "stop": True},
        "persona_override": None,
    }

    with patch("voice_buddy.main.load_user_config", return_value=user_config), \
         patch("voice_buddy.main.select_response") as mock_resp, \
         patch("voice_buddy.main.resolve_audio_path", return_value=None), \
         patch("voice_buddy.main.synthesize_to_file", return_value="/tmp/audio.mp3") as mock_tts, \
         patch("voice_buddy.main.play_audio", return_value=True) as mock_play, \
         patch("voice_buddy.main.load_style") as mock_style:
        mock_resp.return_value = MagicMock(text="Hello!", audio_id="sessionstart_01")
        mock_style.return_value = {"tts": {"voice": "zh-CN-XiaoyiNeural", "rate": "+10%", "pitch": "+5Hz"}}
        handle_hook_event(data)
        mock_tts.assert_called_once()
        mock_play.assert_called_once_with("/tmp/audio.mp3")


def test_handle_notification_always_uses_tts():
    data = {"hook_event_name": "Notification", "message": "Question", "title": "Claude"}
    user_config = {
        "style": "cute-girl", "nickname": "Master", "enabled": True,
        "events": {"sessionstart": True, "sessionend": True,
                   "notification": True, "stop": True},
        "persona_override": None,
    }

    with patch("voice_buddy.main.load_user_config", return_value=user_config), \
         patch("voice_buddy.main.select_response") as mock_resp, \
         patch("voice_buddy.main.synthesize_to_file", return_value="/tmp/audio.mp3") as mock_tts, \
         patch("voice_buddy.main.play_audio", return_value=True) as mock_play, \
         patch("voice_buddy.main.load_style") as mock_style:
        mock_resp.return_value = MagicMock(text="Master, come here~", audio_id=None)
        mock_style.return_value = {"tts": {"voice": "zh-CN-XiaoyiNeural", "rate": "+10%", "pitch": "+5Hz"}}
        handle_hook_event(data)
        mock_tts.assert_called_once()
        mock_play.assert_called_once()


def test_handle_event_disabled_globally_stays_silent():
    data = {"hook_event_name": "SessionStart"}
    user_config = {
        "style": "cute-girl", "nickname": "Master", "enabled": False,
        "events": {"sessionstart": True, "sessionend": True,
                   "notification": True, "stop": True},
        "persona_override": None,
    }

    with patch("voice_buddy.main.load_user_config", return_value=user_config), \
         patch("voice_buddy.main.synthesize_to_file") as mock_tts, \
         patch("voice_buddy.main.play_audio") as mock_play:
        handle_hook_event(data)
        mock_tts.assert_not_called()
        mock_play.assert_not_called()


def test_handle_event_disabled_per_event_stays_silent():
    data = {"hook_event_name": "SessionStart"}
    user_config = {
        "style": "cute-girl", "nickname": "Master", "enabled": True,
        "events": {"sessionstart": False, "sessionend": True,
                   "notification": True, "stop": True},
        "persona_override": None,
    }

    with patch("voice_buddy.main.load_user_config", return_value=user_config), \
         patch("voice_buddy.main.synthesize_to_file") as mock_tts, \
         patch("voice_buddy.main.play_audio") as mock_play:
        handle_hook_event(data)
        mock_tts.assert_not_called()
        mock_play.assert_not_called()


def test_handle_stop_calls_injector():
    data = {"hook_event_name": "Stop", "transcript_path": "/tmp/t.json"}
    user_config = {
        "style": "cute-girl", "nickname": "Master", "enabled": True,
        "events": {"sessionstart": True, "sessionend": True,
                   "notification": True, "stop": True},
        "persona_override": None,
    }

    with patch("voice_buddy.main.load_user_config", return_value=user_config), \
         patch("voice_buddy.main.handle_stop_event") as mock_injector:
        handle_hook_event(data)
        mock_injector.assert_called_once()


def test_muted_session_start_still_starts_listener(supervisor):
    config = {"enabled": True, "events": {"sessionstart": False}}
    with patch("voice_buddy.main.load_user_config", return_value=config), \
         patch("voice_buddy.main.play_audio") as play:
        handle_hook_event({"hook_event_name": "SessionStart", "session_id": "muted"})
    supervisor[0].assert_called_once_with("muted")
    play.assert_not_called()


@pytest.mark.parametrize("config", [
    {"enabled": False},
    {"events": {"sessionend": False}},
])
def test_disabled_session_end_still_releases_session(config, supervisor):
    with patch("voice_buddy.main.load_user_config", return_value=config), \
         patch("voice_buddy.main.play_audio") as play:
        handle_hook_event({"hook_event_name": "SessionEnd", "session_id": "closed"})
    supervisor[1].assert_called_once_with("closed")
    play.assert_not_called()


def test_session_end_releases_session_when_config_cannot_load(supervisor):
    with patch("voice_buddy.main.load_user_config", side_effect=ValueError("invalid JSON")):
        handle_hook_event({"hook_event_name": "SessionEnd", "session_id": "closed"})
    supervisor[1].assert_called_once_with("closed")


def test_session_end_releases_session_when_runtime_resources_are_missing(supervisor):
    with patch("voice_buddy.main.missing_runtime_resources", return_value=["assets"]):
        handle_hook_event({"hook_event_name": "SessionEnd", "session_id": "closed"})
    supervisor[1].assert_called_once_with("closed")
