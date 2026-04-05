"""Analyze hook event data and extract semantic context."""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContextResult:
    event: str          # "pretooluse", "posttooluse", etc.
    sub_event: str      # "git_commit", "test_passed", "default", etc.
    mood: str = ""      # "happy", "sad", "encouraging", "neutral"
    detail: str = ""    # Human-readable detail string
    variables: dict = field(default_factory=dict)


# PreToolUse: (regex_pattern, sub_event_name)
_PRE_TOOL_PATTERNS = [
    (r"git\s+commit", "git_commit"),
    (r"git\s+push", "git_push"),
    (r"git\s+pull", "git_pull"),
    (r"(?:npm\s+test|pytest|python\s+-m\s+pytest|cargo\s+test|go\s+test)", "test_run"),
    (r"npm\s+install", "npm_install"),
    (r"npm\s+run\s+build", "npm_build"),
    (r"docker\b", "docker"),
]

# PostToolUse: patterns to detect in response text
_TEST_PASSED_PATTERNS = [
    re.compile(r"\d+\s+passed", re.IGNORECASE),
    re.compile(r"tests?\s+passed", re.IGNORECASE),
    re.compile(r"all\s+tests?\s+pass", re.IGNORECASE),
    re.compile(r"ok\s*\(\d+\s+test", re.IGNORECASE),
]

_TEST_FAILED_PATTERNS = [
    re.compile(r"\d+\s+failed", re.IGNORECASE),
    re.compile(r"tests?\s+failed", re.IGNORECASE),
    re.compile(r"FAIL", re.MULTILINE),
    re.compile(r"failures?:", re.IGNORECASE),
]

_GIT_SUCCESS_PATTERNS = [
    re.compile(r"->\s+\w+", re.MULTILINE),          # push output: main -> main
    re.compile(r"Already up to date", re.IGNORECASE),
    re.compile(r"Fast-forward", re.IGNORECASE),
    re.compile(r"\d+\s+files?\s+changed", re.IGNORECASE),
]


def analyze_context(data: dict) -> Optional[ContextResult]:
    """Analyze hook stdin JSON and return a ContextResult, or None if silent."""
    event_name = data.get("hook_event_name", "")

    if event_name == "PreToolUse":
        return _analyze_pretooluse(data)
    elif event_name == "PostToolUse":
        return _analyze_posttooluse(data)
    elif event_name == "PostToolUseFailure":
        return _analyze_posttoolusefailure(data)
    elif event_name == "SessionStart":
        return ContextResult(event="sessionstart", sub_event="default", mood="happy")
    elif event_name == "SessionEnd":
        return ContextResult(event="sessionend", sub_event="default", mood="neutral")
    else:
        # Stop and unknown events: return None (Stop is handled by injector)
        return None


def _analyze_pretooluse(data: dict) -> Optional[ContextResult]:
    """PreToolUse: only trigger for whitelisted Bash commands."""
    tool_name = data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""

    for pattern, sub_event in _PRE_TOOL_PATTERNS:
        if re.search(pattern, command):
            return ContextResult(
                event="pretooluse",
                sub_event=sub_event,
                mood="encouraging",
                detail=command,
            )

    return None


def _analyze_posttooluse(data: dict) -> Optional[ContextResult]:
    """PostToolUse: only trigger for meaningful Bash results."""
    inputs = data.get("inputs", {})
    response = data.get("response", "")

    # Only process Bash tool outputs (inputs has "command" key)
    if not isinstance(inputs, dict) or "command" not in inputs:
        return None

    response_str = str(response)

    # Check for test failures first (higher priority than pass)
    for pattern in _TEST_FAILED_PATTERNS:
        if pattern.search(response_str):
            return ContextResult(
                event="posttooluse",
                sub_event="test_failed",
                mood="sad",
                detail=response_str[:200],
            )

    # Check for test passed
    for pattern in _TEST_PASSED_PATTERNS:
        if pattern.search(response_str):
            return ContextResult(
                event="posttooluse",
                sub_event="test_passed",
                mood="happy",
                detail=response_str[:200],
            )

    # Check for git success
    command = inputs.get("command", "")
    if re.search(r"git\s+(push|pull|commit|merge)", command):
        for pattern in _GIT_SUCCESS_PATTERNS:
            if pattern.search(response_str):
                return ContextResult(
                    event="posttooluse",
                    sub_event="git_success",
                    mood="happy",
                    detail=command,
                )

    # Unrecognized Bash output: stay silent
    return None


def _analyze_posttoolusefailure(data: dict) -> Optional[ContextResult]:
    """PostToolUseFailure: only announce Bash tool failures."""
    tool_name = data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    error_type = data.get("error_type", "")
    error_msg = data.get("error", "")

    if "timeout" in error_type.lower() or "timeout" in error_msg.lower():
        sub_event = "timeout"
        mood = "sad"
    else:
        sub_event = "default"
        mood = "encouraging"

    return ContextResult(
        event="posttoolusefailure",
        sub_event=sub_event,
        mood=mood,
        detail=error_msg[:200],
    )
