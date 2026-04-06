import random
from unittest.mock import patch

from voice_buddy.context import ContextResult
from voice_buddy.response import select_response, ResponseResult


def test_select_response_returns_response_result():
    ctx = ContextResult(event="sessionstart", sub_event="default", mood="happy")
    with patch("voice_buddy.response._load_style_templates") as mock_load:
        mock_load.return_value = {
            "sessionstart": ["Hello!", "Hi there!"],
            "sessionend": ["Bye!"],
            "notification": ["{{nickname}}, look!"],
        }
        result = select_response(ctx, style="cute-girl")
    assert isinstance(result, ResponseResult)
    assert result.text in ["Hello!", "Hi there!"]
    assert result.audio_id in ["sessionstart_01", "sessionstart_02"]


def test_select_response_notification_replaces_nickname():
    ctx = ContextResult(event="notification", sub_event="default", mood="encouraging")
    with patch("voice_buddy.response._load_style_templates") as mock_load:
        mock_load.return_value = {
            "sessionstart": ["Hello!"],
            "sessionend": ["Bye!"],
            "notification": ["{{nickname}}, come here~"],
        }
        result = select_response(ctx, style="cute-girl", nickname="Master")
    assert result.text == "Master, come here~"
    assert result.audio_id is None  # notification has no pre-packaged audio


def test_select_response_sessionstart_has_audio_id():
    ctx = ContextResult(event="sessionstart", sub_event="default", mood="happy")
    with patch("voice_buddy.response._load_style_templates") as mock_load:
        mock_load.return_value = {
            "sessionstart": ["A", "B", "C", "D", "E", "F"],
            "sessionend": [],
            "notification": [],
        }
        random.seed(42)
        result = select_response(ctx, style="cute-girl")
    assert result.audio_id is not None
    assert result.audio_id.startswith("sessionstart_")


def test_select_response_unknown_event_returns_none():
    ctx = ContextResult(event="nonexistent", sub_event="default", mood="neutral")
    result = select_response(ctx, style="cute-girl")
    assert result is None


def test_select_response_unknown_style_returns_none():
    ctx = ContextResult(event="sessionstart", sub_event="default", mood="happy")
    result = select_response(ctx, style="nonexistent-style")
    assert result is None
