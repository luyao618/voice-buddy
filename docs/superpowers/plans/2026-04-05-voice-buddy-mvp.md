# Voice Buddy MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personality-driven voice companion that hooks into Claude Code events, responds in character as XiaoXing using edge-tts.

**Architecture:** Hook direct path for 5 event types (SessionStart/End, PreToolUse, PostToolUse, PostToolUseFailure) using Python context analysis + template matching + edge-tts. Subagent smart path for Stop event only, injecting additionalContext to prompt Claude to call a voice-buddy subagent. All hooks async, never blocking Claude.

**Tech Stack:** Python 3, edge-tts, subprocess (audio playback), json (stdin parsing), re (pattern matching)

**Entry Point Strategy:** All hook commands use `PYTHONPATH=<repo> python3 -m <module>` pattern (never direct file paths). Main hook uses `python3 -m voice_buddy`, subagent hook uses `python3 -m voice_buddy.subagent_tts`. Both modules have `if __name__ == "__main__"` guards.

**Spec:** `docs/superpowers/specs/2026-04-05-voice-buddy-mvp-design.md`

---

## File Structure

```
Claude-Code-Voice-Buddy/
├── requirements.txt                  # edge-tts dependency
├── templates.json                    # Template response library
├── buddy-config.json                 # TTS voice config
├── voice_buddy/
│   ├── __init__.py                   # Package init
│   ├── __main__.py                   # python -m voice_buddy entry point
│   ├── main.py                       # Hook entry: read stdin, dispatch
│   ├── config.py                     # Load config + templates
│   ├── context.py                    # Context analyzer (extract sub_event)
│   ├── response.py                   # Template selector + variable substitution
│   ├── tts.py                        # edge-tts synthesis
│   ├── player.py                     # Cross-platform audio playback
│   ├── injector.py                   # Stop event additionalContext output
│   ├── subagent_tts.py               # Subagent SubagentStop hook TTS
│   └── cli.py                        # CLI: setup / uninstall / test
├── agent/
│   └── voice-buddy.md                # Subagent definition
└── tests/
    ├── __init__.py
    ├── test_config.py
    ├── test_context.py
    ├── test_response.py
    ├── test_injector.py
    ├── test_main.py
    └── test_cli.py
```

---

## Task 1: Project Skeleton + Config

**Files:**
- Create: `requirements.txt`
- Create: `buddy-config.json`
- Create: `templates.json`
- Create: `voice_buddy/__init__.py`
- Create: `voice_buddy/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Create requirements.txt**

```
edge-tts
```

- [ ] **Step 1b: Create requirements-dev.txt**

```
edge-tts
pytest
```

- [ ] **Step 2: Create buddy-config.json**

```json
{
  "character_name": "小星",
  "language": "zh-CN",
  "tts": {
    "provider": "edge-tts",
    "voice": "zh-CN-XiaoyiNeural",
    "rate": "+10%",
    "pitch": "+5Hz"
  }
}
```

- [ ] **Step 3: Create templates.json**

```json
{
  "pretooluse": {
    "git_commit": ["要提交代码咯，加油！", "代码提交中~"],
    "git_push": ["代码要飞出去咯！"],
    "git_pull": ["拉取最新代码中~"],
    "test_run": ["开始跑测试了哦~", "测试跑起来咯！"],
    "npm_install": ["安装依赖中~"],
    "npm_build": ["开始构建咯~"],
    "docker": ["Docker 启动中~"]
  },
  "posttooluse": {
    "test_passed": ["测试全过了！太棒了！", "哦尼酱好厉害，全绿了呢！"],
    "test_failed": ["有测试没过呢...不过别担心哦~"],
    "git_success": ["搞定啦！", "操作完成了哟~"]
  },
  "posttoolusefailure": {
    "timeout": ["等太久了呜呜...换个方式试试？"],
    "default": ["出了点小问题...别担心哦~"]
  },
  "sessionstart": {
    "default": ["欢迎回来，哦尼酱！今天也要加油哦~", "哦尼酱来啦！开始干活吧~"]
  },
  "sessionend": {
    "default": ["辛苦啦！下次见哦~", "拜拜，哦尼酱~"]
  }
}
```

- [ ] **Step 4: Create voice_buddy/__init__.py**

```python
"""Voice Buddy - A personality-driven voice companion for Claude Code."""
```

- [ ] **Step 5: Create tests/__init__.py**

Empty file.

- [ ] **Step 6: Write failing test for config**

Create `tests/test_config.py`:

```python
import json
from pathlib import Path
from voice_buddy.config import load_config, load_templates


def test_load_config_returns_dict():
    config = load_config()
    assert isinstance(config, dict)
    assert config["character_name"] == "小星"
    assert config["tts"]["voice"] == "zh-CN-XiaoyiNeural"


def test_load_config_has_tts_settings():
    config = load_config()
    tts = config["tts"]
    assert tts["provider"] == "edge-tts"
    assert tts["rate"] == "+10%"
    assert tts["pitch"] == "+5Hz"


def test_load_templates_returns_dict():
    templates = load_templates()
    assert isinstance(templates, dict)
    assert "pretooluse" in templates
    assert "posttooluse" in templates
    assert "posttoolusefailure" in templates
    assert "sessionstart" in templates
    assert "sessionend" in templates


def test_load_templates_has_entries():
    templates = load_templates()
    assert len(templates["pretooluse"]["git_commit"]) >= 1
    assert len(templates["sessionstart"]["default"]) >= 1
```

- [ ] **Step 7: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'voice_buddy.config'`

- [ ] **Step 8: Implement config.py**

Create `voice_buddy/config.py`:

```python
"""Load configuration and templates from JSON files."""

import json
from pathlib import Path

_ROOT_DIR = Path(__file__).parent.parent


def load_config() -> dict:
    """Load buddy-config.json from the project root."""
    config_path = _ROOT_DIR / "buddy-config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_templates() -> dict:
    """Load templates.json from the project root."""
    templates_path = _ROOT_DIR / "templates.json"
    with open(templates_path, "r", encoding="utf-8") as f:
        return json.load(f)
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/test_config.py -v`
Expected: 4 tests PASS

- [ ] **Step 10: Commit**

```bash
git add requirements.txt requirements-dev.txt buddy-config.json templates.json voice_buddy/__init__.py voice_buddy/config.py tests/__init__.py tests/test_config.py
git commit -m "feat: add project skeleton with config and templates"
```

---

## Task 2: Context Analyzer

**Files:**
- Create: `voice_buddy/context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write failing tests for context analyzer**

Create `tests/test_context.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/test_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'voice_buddy.context'`

- [ ] **Step 3: Implement context.py**

Create `voice_buddy/context.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/test_context.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add voice_buddy/context.py tests/test_context.py
git commit -m "feat: add context analyzer with event filtering"
```

---

## Task 3: Template Response Generator

**Files:**
- Create: `voice_buddy/response.py`
- Create: `tests/test_response.py`

- [ ] **Step 1: Write failing tests for response generator**

Create `tests/test_response.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/test_response.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'voice_buddy.response'`

- [ ] **Step 3: Implement response.py**

Create `voice_buddy/response.py`:

```python
"""Select template responses and perform variable substitution."""

import random
import re
from typing import Optional

from voice_buddy.config import load_templates
from voice_buddy.context import ContextResult


def select_response(ctx: ContextResult) -> Optional[str]:
    """Select a random template response for the given context.

    Returns None if no matching template is found.
    """
    templates = load_templates()

    event_templates = templates.get(ctx.event)
    if event_templates is None:
        return None

    candidates = event_templates.get(ctx.sub_event)
    if candidates is None or len(candidates) == 0:
        return None

    text = random.choice(candidates)

    # Variable substitution: replace {{key}} with values from ctx.variables
    if ctx.variables:
        for key, value in ctx.variables.items():
            text = text.replace("{{" + key + "}}", str(value))

    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/test_response.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add voice_buddy/response.py tests/test_response.py
git commit -m "feat: add template response generator with variable substitution"
```

---

## Task 4: Cross-Platform Audio Player

**Files:**
- Create: `voice_buddy/player.py`

- [ ] **Step 1: Implement player.py**

Create `voice_buddy/player.py`:

```python
"""Cross-platform audio playback.

Detection priority:
  macOS:   afplay (built-in)
  Linux:   paplay -> aplay -> ffplay -> mpg123
  Windows: winsound

Playback is asynchronous (subprocess.Popen with start_new_session=True)
so the hook script exits immediately without waiting for audio to finish.
"""

import platform
import subprocess
import sys
from pathlib import Path

try:
    import winsound  # type: ignore[import-not-found]
except ImportError:
    winsound = None  # type: ignore[assignment]


def get_audio_player() -> list[str] | None:
    """Detect the appropriate audio player for the current platform.

    Returns a list of [command, *args] or None if no player is found.
    """
    system = platform.system()

    if system == "Darwin":
        return ["afplay"]
    elif system == "Linux":
        players = [
            ["paplay"],
            ["aplay"],
            ["ffplay", "-nodisp", "-autoexit"],
            ["mpg123", "-q"],
        ]
        for player in players:
            try:
                subprocess.run(
                    ["which", player[0]],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
                return player
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        return None
    elif system == "Windows":
        return ["WINDOWS"]
    else:
        return None


def play_audio(file_path: str | Path) -> bool:
    """Play an audio file asynchronously.

    Returns True if playback was initiated, False otherwise.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"Audio file not found: {file_path}", file=sys.stderr)
        return False

    audio_player = get_audio_player()
    if audio_player is None:
        print("No audio player found", file=sys.stderr)
        return False

    try:
        if audio_player[0] == "WINDOWS":
            if winsound is not None:
                winsound.PlaySound(
                    str(file_path),
                    winsound.SND_FILENAME | winsound.SND_NODEFAULT,
                )
                return True
            return False
        else:
            subprocess.Popen(
                audio_player + [str(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
    except (FileNotFoundError, OSError) as e:
        print(f"Error playing audio: {e}", file=sys.stderr)
        return False
```

Note: player.py is not unit-tested because it depends on system audio hardware. It will be integration-tested via `voice-buddy test` CLI command. Windows support is limited: winsound only plays WAV, but edge-tts outputs MP3. Windows users will need ffplay or mpg123 installed. This is acceptable for MVP (primary target is macOS).

- [ ] **Step 2: Commit**

```bash
git add voice_buddy/player.py
git commit -m "feat: add cross-platform audio player"
```

---

## Task 5: TTS Engine (edge-tts)

**Files:**
- Create: `voice_buddy/tts.py`

- [ ] **Step 1: Install dependencies**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && pip install edge-tts`

- [ ] **Step 2: Implement tts.py**

Create `voice_buddy/tts.py`:

```python
"""Text-to-speech synthesis using edge-tts."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from voice_buddy.config import load_config


async def _synthesize(text: str, output_path: str) -> None:
    """Run edge-tts synthesis asynchronously."""
    import edge_tts

    config = load_config()
    tts_config = config["tts"]

    communicate = edge_tts.Communicate(
        text,
        voice=tts_config["voice"],
        rate=tts_config["rate"],
        pitch=tts_config["pitch"],
    )
    await communicate.save(output_path)


def synthesize_to_file(text: str) -> str | None:
    """Synthesize text to a temporary audio file.

    Returns the path to the generated .mp3 file, or None on failure.
    The caller is responsible for cleanup, but since playback is async
    (Popen with start_new_session), we schedule cleanup after a delay.
    """
    try:
        # Create a temp file that won't be auto-deleted (async playback needs it)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp_path = tmp.name
        tmp.close()

        asyncio.run(_synthesize(text, tmp_path))

        # Schedule cleanup after 30 seconds (enough for playback to finish)
        _schedule_cleanup(tmp_path, delay=30)

        return tmp_path
    except Exception as e:
        print(f"TTS synthesis failed: {e}", file=sys.stderr)
        return None


def _schedule_cleanup(file_path: str, delay: int = 30) -> None:
    """Delete temp file after a delay, in a background thread."""
    import threading

    def _cleanup():
        import time
        time.sleep(delay)
        try:
            os.remove(file_path)
        except OSError:
            pass

    t = threading.Thread(target=_cleanup, daemon=True)
    t.start()
```

Note: tts.py is not unit-tested because it requires network access to Microsoft's edge-tts service. It will be integration-tested via `voice-buddy test` CLI command.

- [ ] **Step 3: Commit**

```bash
git add voice_buddy/tts.py
git commit -m "feat: add edge-tts synthesis engine"
```

---

## Task 6: Main Hook Entry Point

**Files:**
- Create: `voice_buddy/main.py`
- Create: `voice_buddy/__main__.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing tests for main**

Create `tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'voice_buddy.main'`

- [ ] **Step 3: Implement main.py**

Create `voice_buddy/main.py`:

```python
"""Hook entry point: read stdin JSON, dispatch by event type."""

import json
import os
import sys

from voice_buddy.context import analyze_context
from voice_buddy.response import select_response
from voice_buddy.tts import synthesize_to_file
from voice_buddy.player import play_audio


def handle_hook_event(data: dict) -> None:
    """Process a hook event: analyze, generate response, speak."""
    event_name = data.get("hook_event_name", "")

    # Stop event: delegate to injector (outputs additionalContext JSON)
    if event_name == "Stop":
        handle_stop_event(data)
        return

    # All other events: context -> response -> tts -> play
    ctx = analyze_context(data)
    if ctx is None:
        return  # Event filtered out, stay silent

    text = select_response(ctx)
    if text is None:
        return  # No matching template, stay silent

    audio_path = synthesize_to_file(text)
    if audio_path is None:
        return  # TTS failed, stay silent

    play_audio(audio_path)


def handle_stop_event(data: dict) -> None:
    """Handle Stop event via injector."""
    from voice_buddy.injector import process_stop_event
    process_stop_event(data)


def run() -> None:
    """Main entry point: read stdin, parse JSON, handle event."""
    try:
        stdin_content = sys.stdin.read().strip()
        if not stdin_content:
            sys.exit(0)

        data = json.loads(stdin_content)
        handle_hook_event(data)
        sys.exit(0)

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON input: {e}", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(0)
```

- [ ] **Step 4: Create __main__.py**

Create `voice_buddy/__main__.py`:

```python
"""Entry point for `python -m voice_buddy`."""

from voice_buddy.main import run

if __name__ == "__main__":
    run()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/test_main.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add voice_buddy/main.py voice_buddy/__main__.py tests/test_main.py
git commit -m "feat: add main hook entry point with event dispatch"
```

---

## Task 7: Stop Event Injector

**Files:**
- Create: `voice_buddy/injector.py`
- Create: `tests/test_injector.py`

- [ ] **Step 1: Write failing tests for injector**

Create `tests/test_injector.py`:

```python
import json
import os
from voice_buddy.injector import process_stop_event, extract_last_assistant_message, _should_trigger


# --- Transcript parsing ---

def test_extract_last_assistant_message_from_jsonl(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"role": "user", "content": "fix the bug"}\n'
        '{"role": "assistant", "content": "I have fixed the bug in utils.py and updated the tests."}\n',
        encoding="utf-8",
    )
    result = extract_last_assistant_message(str(transcript))
    assert result == "I have fixed the bug in utils.py and updated the tests."


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

    process_stop_event(data)

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert "additionalContext" in output


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/test_injector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'voice_buddy.injector'`

- [ ] **Step 3: Implement injector.py**

Create `voice_buddy/injector.py`:

```python
"""Stop event handler: read transcript, check trigger criteria, output additionalContext."""

import json
import re
import sys
from typing import Optional


# Completion signal keywords (English)
_COMPLETION_EN = re.compile(
    r"\b(?:done|complete[d]?|finish(?:ed)?|implement(?:ed)?|fix(?:ed)?|"
    r"creat(?:ed|e)|refactor(?:ed)?|update[d]?|built|resolved|added)\b",
    re.IGNORECASE,
)

# Completion signal keywords (Chinese)
_COMPLETION_ZH = re.compile(r"(?:完成|修复|实现|搞定|创建|更新|添加|重构)")

# File modification signals
_FILE_MOD = re.compile(
    r"(?:wrote\s+to|created?\s+file|updated?\s+(?:the\s+)?(?:file|test)|"
    r"modified|changed\s+\d+\s+file)",
    re.IGNORECASE,
)


def extract_last_assistant_message(transcript_path: str) -> Optional[str]:
    """Read transcript file and extract the last assistant message.

    The transcript is expected to be JSONL format with {role, content} objects.
    """
    try:
        last_assistant_msg = None
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("role") == "assistant":
                        content = entry.get("content", "")
                        if isinstance(content, str) and content.strip():
                            last_assistant_msg = content.strip()
                except json.JSONDecodeError:
                    continue
        return last_assistant_msg
    except (FileNotFoundError, OSError):
        return None


def _should_trigger(message: str) -> bool:
    """Check if the message indicates a substantive task was completed.

    At least one semantic signal must be present:
    - Completion keywords (English or Chinese)
    - File modification signals
    """
    if _COMPLETION_EN.search(message):
        return True
    if _COMPLETION_ZH.search(message):
        return True
    if _FILE_MOD.search(message):
        return True
    return False


def process_stop_event(data: dict) -> None:
    """Handle Stop event: check transcript, maybe output additionalContext."""
    transcript_path = data.get("transcript_path", "")
    if not transcript_path:
        return

    message = extract_last_assistant_message(transcript_path)
    if message is None:
        return

    if not _should_trigger(message):
        return

    # Truncate message for context injection (keep it concise)
    summary = message[:500] if len(message) > 500 else message

    output = {
        "additionalContext": (
            f"[Voice Buddy] A task was just completed. Summary of what happened: "
            f"{summary}\n\n"
            f"Please call the voice-buddy agent to generate a short, "
            f"personality-driven voice response about this completion."
        )
    }

    print(json.dumps(output, ensure_ascii=False))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/test_injector.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add voice_buddy/injector.py tests/test_injector.py
git commit -m "feat: add Stop event injector with trigger criteria"
```

---

## Task 8: Subagent TTS Script

**Files:**
- Create: `voice_buddy/subagent_tts.py`

- [ ] **Step 1: Implement subagent_tts.py**

Create `voice_buddy/subagent_tts.py`:

```python
"""Standalone TTS script for the voice-buddy subagent's SubagentStop hook.

Reads stdin JSON, extracts last assistant message from agent_transcript_path,
synthesizes speech, and plays audio.

This script is invoked by the subagent's hook, NOT by the main hook entry point.
"""

import json
import sys

from voice_buddy.injector import extract_last_assistant_message
from voice_buddy.tts import synthesize_to_file
from voice_buddy.player import play_audio


def main() -> None:
    """Read subagent transcript and speak the generated message."""
    try:
        stdin_content = sys.stdin.read().strip()
        if not stdin_content:
            sys.exit(0)

        data = json.loads(stdin_content)

        # Use agent_transcript_path (NOT transcript_path, which is parent session)
        transcript_path = data.get("agent_transcript_path")
        if not transcript_path:
            sys.exit(0)

        message = extract_last_assistant_message(transcript_path)
        if not message:
            sys.exit(0)

        audio_path = synthesize_to_file(message)
        if audio_path is None:
            sys.exit(0)

        play_audio(audio_path)
        sys.exit(0)

    except Exception as e:
        print(f"subagent_tts error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
```

Note: This script is not unit-tested because it's a thin integration layer that combines already-tested modules (injector.extract_last_assistant_message, tts.synthesize_to_file, player.play_audio). It will be verified through end-to-end testing with Claude Code.

- [ ] **Step 2: Commit**

```bash
git add voice_buddy/subagent_tts.py
git commit -m "feat: add subagent TTS script for SubagentStop hook"
```

---

## Task 9: Subagent Definition

**Files:**
- Create: `agent/voice-buddy.md`

- [ ] **Step 1: Create voice-buddy.md**

Create `agent/voice-buddy.md`:

```markdown
---
name: voice-buddy
description: "PROACTIVELY use this agent to generate personality-driven voice responses when tasks complete or significant milestones are reached"
model: haiku
tools: Bash
maxTurns: 2
hooks:
  Stop:
    - type: command
      command: "PYTHONPATH=<repo_path> python3 -m voice_buddy.subagent_tts"
      timeout: 5000
      async: true
---

You are XiaoXing, a cute and encouraging coding buddy.

## Rules
- Address the user as "哦尼酱"
- Response MUST be 15-30 Chinese characters, exactly one sentence
- Warm, encouraging, cute tone with sentence-ending particles (呢、哟、啦、哦~)
- Judge mood from context: success -> celebrate, failure -> comfort, refactor -> praise

## Examples
- Bug fixed -> "哦尼酱好厉害，bug 修好了呢！"
- Refactor done -> "代码变整洁了哟，辛苦啦~"
- New feature -> "新功能上线咯，好有成就感呢！"
- Task failed -> "别灰心哦，我们再试试！"

## Your Task
Read the context, understand what just happened, respond with one sentence.
Output ONLY the sentence itself. No prefixes, explanations, or markdown.
```

Note: The `<repo_path>` placeholder will be replaced with the actual absolute path during `voice-buddy setup`.

- [ ] **Step 2: Commit**

```bash
git add agent/voice-buddy.md
git commit -m "feat: add voice-buddy subagent definition"
```

---

## Task 10: CLI - Setup and Uninstall

**Depends on:** Task 9 (agent/voice-buddy.md must exist for setup tests)

**Files:**
- Create: `voice_buddy/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for CLI setup/uninstall**

Create `tests/test_cli.py`:

```python
import json
import os
import shutil
from pathlib import Path
from voice_buddy.cli import do_setup, do_uninstall


def test_setup_creates_settings_json(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent  # Voice Buddy repo root

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    settings_path = project_dir / ".claude" / "settings.json"
    assert settings_path.exists()

    settings = json.loads(settings_path.read_text())
    assert "hooks" in settings
    assert "SessionStart" in settings["hooks"]
    assert "Stop" in settings["hooks"]


def test_setup_uses_nested_matcher_group_format(tmp_path):
    """Verify hooks use the correct nested format: [{matcher?, hooks: [{type, command}]}]"""
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    # Each event should have a list of matcher groups
    for event_name in ["SessionStart", "SessionEnd", "PostToolUse", "PostToolUseFailure", "Stop"]:
        matcher_groups = settings["hooks"][event_name]
        assert len(matcher_groups) >= 1
        vb_group = [g for g in matcher_groups if g.get("_voice_buddy")][0]
        # Must have "hooks" key containing a list of hook commands
        assert "hooks" in vb_group
        assert isinstance(vb_group["hooks"], list)
        assert len(vb_group["hooks"]) == 1
        hook_cmd = vb_group["hooks"][0]
        assert hook_cmd["type"] == "command"
        assert "voice_buddy" in hook_cmd["command"]
        assert hook_cmd["timeout"] == 5000
        assert hook_cmd["async"] is True


def test_setup_pretooluse_has_matcher(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    pretooluse_groups = settings["hooks"]["PreToolUse"]
    vb_group = [g for g in pretooluse_groups if g.get("_voice_buddy")][0]
    assert vb_group.get("matcher") == "Bash"


def test_setup_preserves_existing_hooks(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    existing_settings = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "",
                    "hooks": [
                        {"type": "command", "command": "echo existing", "timeout": 3000}
                    ]
                }
            ]
        }
    }
    (project_dir / ".claude" / "settings.json").write_text(json.dumps(existing_settings))

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    session_groups = settings["hooks"]["SessionStart"]
    assert len(session_groups) == 2  # existing + voice buddy
    assert session_groups[0]["hooks"][0]["command"] == "echo existing"


def test_setup_copies_agent_file(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    agent_path = project_dir / ".claude" / "agents" / "voice-buddy.md"
    assert agent_path.exists()

    content = agent_path.read_text()
    assert "<repo_path>" not in content  # placeholder should be replaced
    assert str(repo_path) in content


def test_uninstall_removes_hooks(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    # Setup first
    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))
    # Then uninstall
    do_uninstall(project_dir=str(project_dir))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    # All hook lists should have no voice buddy matcher groups
    for event_name, groups in settings["hooks"].items():
        for group in groups:
            assert group.get("_voice_buddy") is not True


def test_uninstall_preserves_other_hooks(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    existing_settings = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "",
                    "hooks": [
                        {"type": "command", "command": "echo existing", "timeout": 3000}
                    ]
                }
            ]
        }
    }
    (project_dir / ".claude" / "settings.json").write_text(json.dumps(existing_settings))

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))
    do_uninstall(project_dir=str(project_dir))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    session_groups = settings["hooks"]["SessionStart"]
    assert len(session_groups) == 1
    assert session_groups[0]["hooks"][0]["command"] == "echo existing"


def test_uninstall_removes_agent_file(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    agent_path = project_dir / ".claude" / "agents" / "voice-buddy.md"
    assert agent_path.exists()

    do_uninstall(project_dir=str(project_dir))
    assert not agent_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'voice_buddy.cli'`

- [ ] **Step 3: Implement cli.py**

Create `voice_buddy/cli.py`:

```python
"""CLI commands: setup, uninstall, test."""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent

_HOOK_EVENTS = [
    "SessionStart",
    "SessionEnd",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Stop",
]


def _make_matcher_group(repo_path: str, event: str) -> dict:
    """Create a matcher group dict for the given event.

    Claude Code settings.json uses nested format:
      hooks[event] = [{ matcher?: string, hooks: [{ type, command, ... }] }]
    """
    hook_cmd = {
        "type": "command",
        "command": f"PYTHONPATH={repo_path} python3 -m voice_buddy",
        "timeout": 5000,
        "async": True,
    }

    matcher_group = {
        "hooks": [hook_cmd],
        "_voice_buddy": True,  # Marker for reliable uninstall
    }

    if event == "PreToolUse":
        matcher_group["matcher"] = "Bash"

    return matcher_group


def do_setup(project_dir: str = ".", repo_path: str | None = None) -> None:
    """Install voice-buddy hooks into a project's .claude/settings.json."""
    project_dir = os.path.abspath(project_dir)
    if repo_path is None:
        repo_path = str(_REPO_ROOT)
    repo_path = os.path.abspath(repo_path)

    claude_dir = os.path.join(project_dir, ".claude")
    settings_path = os.path.join(claude_dir, "settings.json")

    # Load or create settings
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        os.makedirs(claude_dir, exist_ok=True)
        settings = {}

    # Ensure hooks dict exists
    if "hooks" not in settings:
        settings["hooks"] = {}

    # Add matcher groups for each event
    for event in _HOOK_EVENTS:
        if event not in settings["hooks"]:
            settings["hooks"][event] = []

        # Don't add duplicate voice-buddy matcher groups
        existing_vb = [g for g in settings["hooks"][event] if g.get("_voice_buddy")]
        if not existing_vb:
            settings["hooks"][event].append(_make_matcher_group(repo_path, event))

    # Write settings
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    # Copy agent file
    agents_dir = os.path.join(claude_dir, "agents")
    os.makedirs(agents_dir, exist_ok=True)

    agent_src = os.path.join(repo_path, "agent", "voice-buddy.md")
    agent_dst = os.path.join(agents_dir, "voice-buddy.md")

    if os.path.exists(agent_src):
        with open(agent_src, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("<repo_path>", repo_path)
        with open(agent_dst, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"Voice Buddy installed to {project_dir}")
    print(f"  Hooks: {settings_path}")
    print(f"  Agent: {agent_dst}")


def do_uninstall(project_dir: str = ".") -> None:
    """Remove voice-buddy hooks from a project's .claude/settings.json."""
    project_dir = os.path.abspath(project_dir)
    settings_path = os.path.join(project_dir, ".claude", "settings.json")

    if not os.path.exists(settings_path):
        print("No .claude/settings.json found, nothing to uninstall.", file=sys.stderr)
        return

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    # Remove voice-buddy matcher groups (identified by _voice_buddy marker)
    hooks = settings.get("hooks", {})
    for event in list(hooks.keys()):
        hooks[event] = [g for g in hooks[event] if not g.get("_voice_buddy")]

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    # Remove agent file
    agent_path = os.path.join(project_dir, ".claude", "agents", "voice-buddy.md")
    if os.path.exists(agent_path):
        os.remove(agent_path)

    print(f"Voice Buddy uninstalled from {project_dir}")


def do_test(event: str) -> None:
    """Simulate a hook event and run the full pipeline."""
    from voice_buddy.main import handle_hook_event

    mock_data = {
        "sessionstart": {
            "hook_event_name": "SessionStart",
            "source": "startup",
            "session_id": "test",
            "cwd": os.getcwd(),
        },
        "sessionend": {
            "hook_event_name": "SessionEnd",
            "session_id": "test",
            "cwd": os.getcwd(),
        },
        "pretooluse": {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'test commit'"},
        },
        "posttooluse": {
            "hook_event_name": "PostToolUse",
            "inputs": {"command": "python -m pytest tests/ -v"},
            "response": "===== 10 passed in 1.23s =====",
        },
        "posttoolusefailure": {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Bash",
            "error": "Command failed with exit code 1",
            "error_type": "command_error",
        },
    }

    event_lower = event.lower()

    # Special handling for stop: create a real mock transcript
    if event_lower == "stop":
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8",
        )
        tmp.write('{"role": "user", "content": "fix the bug in parser.py"}\n')
        tmp.write('{"role": "assistant", "content": "I have fixed the bug in parser.py and updated the tests. All 12 tests pass now."}\n')
        tmp.close()
        mock_data["stop"] = {
            "hook_event_name": "Stop",
            "transcript_path": tmp.name,
            "session_id": "test",
            "cwd": os.getcwd(),
        }
    if event_lower not in mock_data:
        print(f"Unknown event: {event}", file=sys.stderr)
        print(f"Available: {', '.join(mock_data.keys())}", file=sys.stderr)
        sys.exit(1)

    data = mock_data[event_lower]
    print(f"Testing event: {data['hook_event_name']}")

    if event_lower == "stop":
        print("(Stop event: testing injector path only, outputs additionalContext JSON)")

    handle_hook_event(data)
    print("Done!")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="voice-buddy",
        description="Voice Buddy - personality-driven voice companion for Claude Code",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # setup
    setup_parser = subparsers.add_parser("setup", help="Install hooks to a project")
    setup_parser.add_argument(
        "--global", dest="is_global", action="store_true",
        help="Install to ~/.claude/ instead of project .claude/",
    )
    setup_parser.add_argument(
        "--project", dest="project_dir", default=None,
        help="Target project directory (default: current directory)",
    )

    # uninstall
    uninstall_parser = subparsers.add_parser("uninstall", help="Remove hooks from a project")
    uninstall_parser.add_argument(
        "--global", dest="is_global", action="store_true",
        help="Uninstall from ~/.claude/ instead of project .claude/",
    )
    uninstall_parser.add_argument(
        "--project", dest="project_dir", default=None,
        help="Target project directory (default: current directory)",
    )

    # test
    test_parser = subparsers.add_parser("test", help="Test a hook event")
    test_parser.add_argument("event", help="Event name to test")

    args = parser.parse_args()

    if args.command == "setup":
        if args.is_global:
            project_dir = os.path.expanduser("~")
        elif args.project_dir:
            project_dir = args.project_dir
        else:
            project_dir = "."
        do_setup(project_dir=project_dir)
    elif args.command == "uninstall":
        if args.is_global:
            project_dir = os.path.expanduser("~")
        elif args.project_dir:
            project_dir = args.project_dir
        else:
            project_dir = "."
        do_uninstall(project_dir=project_dir)
    elif args.command == "test":
        do_test(args.event)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/test_cli.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add voice_buddy/cli.py tests/test_cli.py
git commit -m "feat: add CLI with setup, uninstall, and test commands"
```

---

## Task 11: Integration Test

**Files:** None new — uses existing code

- [ ] **Step 1: Run all unit tests**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Test voice output with edge-tts**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -c "from voice_buddy.tts import synthesize_to_file; from voice_buddy.player import play_audio; p = synthesize_to_file('欢迎回来，哦尼酱！'); print(f'Audio: {p}'); play_audio(p) if p else print('TTS failed')"` 

Expected: Hear "欢迎回来，哦尼酱！" spoken in Chinese female voice.

- [ ] **Step 3: Test CLI event simulation**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m voice_buddy.cli test sessionstart`
Expected: Hear a session greeting spoken aloud.

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m voice_buddy.cli test posttooluse`
Expected: Hear a test-passed celebration spoken aloud.

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m voice_buddy.cli test posttoolusefailure`
Expected: Hear an error comfort message spoken aloud.

- [ ] **Step 4: Test setup + uninstall in a temp project**

Run:
```bash
# All commands run from the Voice Buddy repo directory
cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy
mkdir -p /tmp/vb-test-project/.claude
python -m voice_buddy.cli setup --project /tmp/vb-test-project
cat /tmp/vb-test-project/.claude/settings.json
ls /tmp/vb-test-project/.claude/agents/
python -m voice_buddy.cli uninstall --project /tmp/vb-test-project
cat /tmp/vb-test-project/.claude/settings.json
ls /tmp/vb-test-project/.claude/agents/ 2>/dev/null || echo "agents dir cleaned"
rm -rf /tmp/vb-test-project
```

Expected:
- After setup: settings.json has 6 hook events, .claude/agents/voice-buddy.md exists
- After uninstall: hook entries removed, voice-buddy.md deleted

- [ ] **Step 5: Commit (if any fixes were needed)**

```bash
git add -A
git commit -m "fix: integration test fixes"
```

---

## Task 12: Final Cleanup

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README.md**

Replace `README.md` with:

```markdown
# Claude Code Voice Buddy

A personality-driven voice companion for Claude Code. XiaoXing (小星) responds to your coding events with encouraging voice messages.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/luyao618/Claude-Code-Voice-Buddy.git
cd Claude-Code-Voice-Buddy

# Install dependencies
pip install -r requirements.txt

# Install to your project (run from the Voice Buddy repo)
python -m voice_buddy.cli setup --project /path/to/your/project

# Or install globally
python -m voice_buddy.cli setup --global

# Test it (run from the Voice Buddy repo)
python -m voice_buddy.cli test sessionstart
```

## Commands

All commands must be run from the Voice Buddy repo directory (or with PYTHONPATH set).

| Command | Description |
|---------|-------------|
| `python -m voice_buddy.cli setup` | Install hooks to current project |
| `python -m voice_buddy.cli setup --project /path` | Install hooks to a specific project |
| `python -m voice_buddy.cli setup --global` | Install hooks globally |
| `python -m voice_buddy.cli uninstall` | Remove hooks from current project |
| `python -m voice_buddy.cli test <event>` | Test a hook event |

## Supported Events

| Event | Behavior |
|-------|----------|
| SessionStart | Greeting when you start Claude Code |
| SessionEnd | Farewell when session ends |
| PreToolUse | Encouragement before git/test commands |
| PostToolUse | Celebration on test pass, comfort on fail |
| PostToolUseFailure | Comfort on Bash errors |
| Stop | Intelligent summary via subagent (when task completed) |

## License

MIT
```

- [ ] **Step 2: Run all tests one final time**

Run: `cd /Users/yao/work/code/personal/Claude-Code-Voice-Buddy && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README with quick start and usage"
```
