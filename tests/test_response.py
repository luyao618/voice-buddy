import re
from voice_buddy.context import ContextResult
from voice_buddy.response import select_response


def test_select_response_pretooluse_git_commit():
    ctx = ContextResult(event="pretooluse", sub_event="git_commit", mood="encouraging")
    result = select_response(ctx)
    assert result is not None
    assert result in ["要提交代码咯，加油！", "代码提交中~"]


def test_select_response_posttooluse_test_passed():
    ctx = ContextResult(event="posttooluse", sub_event="test_passed", mood="happy")
    result = select_response(ctx)
    assert result is not None
    assert "测试" in result or "全绿" in result or "太棒" in result


def test_select_response_sessionstart():
    ctx = ContextResult(event="sessionstart", sub_event="default", mood="happy")
    result = select_response(ctx)
    assert result is not None
    assert len(result) > 0


def test_select_response_unknown_sub_event_returns_none():
    ctx = ContextResult(event="posttooluse", sub_event="unknown_event", mood="neutral")
    result = select_response(ctx)
    assert result is None


def test_select_response_unknown_event_returns_none():
    ctx = ContextResult(event="nonexistent", sub_event="default", mood="neutral")
    result = select_response(ctx)
    assert result is None


def test_select_response_variable_substitution():
    ctx = ContextResult(
        event="posttooluse",
        sub_event="test_passed",
        mood="happy",
        variables={"detail": "42个测试"},
    )
    result = select_response(ctx)
    assert result is not None
    # Variable substitution happens if template contains {{detail}}


def test_select_response_posttoolusefailure_default():
    ctx = ContextResult(event="posttoolusefailure", sub_event="default", mood="encouraging")
    result = select_response(ctx)
    assert result is not None
    assert "小问题" in result or "别担心" in result
