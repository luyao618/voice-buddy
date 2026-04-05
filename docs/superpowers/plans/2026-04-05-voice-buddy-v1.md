# Voice Buddy v1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve Voice Buddy from a single-personality MVP into a polished Claude Code plugin with 5 styles, 3 languages, pre-packaged audio, user configuration, and standard plugin distribution.

**Architecture:** Multi-style system where CC (the voice companion) has 5 personality modes. SessionStart/SessionEnd use pre-packaged audio for near-zero latency. Notification uses real-time TTS with nickname substitution. Stop uses AI-generated summaries via style-specific agents. User config lives in a cross-platform config directory.

**Tech Stack:** Python 3, edge-tts, Claude Code plugin system (hooks.json, plugin.json)

**Spec:** `docs/superpowers/specs/2026-04-05-voice-buddy-v1-design.md`

---

## File Structure

### New Files to Create
- `.claude-plugin/plugin.json` — Plugin manifest
- `.claude-plugin/marketplace.json` — Self-hosted marketplace manifest
- `hooks/hooks.json` — Hook event declarations (replaces manual setup)
- `commands/voice-buddy.md` — `/voice-buddy` slash command
- `personas/cute-girl.json` — Style definition (cute-girl)
- `personas/elegant-lady.json` — Style definition (elegant-lady)
- `personas/warm-boy.json` — Style definition (warm-boy)
- `personas/secretary.json` — Style definition (secretary)
- `personas/kawaii.json` — Style definition (kawaii)
- `templates/cute-girl.json` — Phrase templates (placeholder until user provides)
- `templates/elegant-lady.json` — Phrase templates (placeholder until user provides)
- `templates/warm-boy.json` — Phrase templates (placeholder until user provides)
- `templates/secretary.json` — Phrase templates (placeholder until user provides)
- `templates/kawaii.json` — Phrase templates (placeholder until user provides)
- `agents/voice-buddy-cute-girl.md` — Agent persona
- `agents/voice-buddy-elegant-lady.md` — Agent persona
- `agents/voice-buddy-warm-boy.md` — Agent persona
- `agents/voice-buddy-secretary.md` — Agent persona
- `agents/voice-buddy-kawaii.md` — Agent persona
- `voice_buddy/styles.py` — Style definition loader
- `tests/test_styles.py` — Tests for style loading
- `tests/test_audio_assets.py` — Tests for pre-packaged audio lookup + fallback

### Files to Modify
- `voice_buddy/config.py` — Rewrite: cross-platform user config, style-aware loading
- `voice_buddy/response.py` — Extend: per-style templates, audio file ID, nickname substitution
- `voice_buddy/main.py` — Extend: config-aware pipeline, pre-packaged audio path, disabled check
- `voice_buddy/injector.py` — Extend: style-aware additionalContext with nickname/persona
- `voice_buddy/subagent_tts.py` — Extend: read TTS config from active style
- `voice_buddy/tts.py` — Minor: accept voice/rate/pitch overrides from style config
- `voice_buddy/cli.py` — Extend: config/on/off commands, --style flag for test
- `tests/test_config.py` — Rewrite for new config system
- `tests/test_response.py` — Extend for per-style templates
- `tests/test_main.py` — Extend for new pipeline paths
- `tests/test_cli.py` — Extend for new CLI commands

### Files to Delete
- `buddy-config.json` — Replaced by `personas/*.json` + user config
- `templates.json` — Replaced by `templates/*.json`
- `agent/voice-buddy.md` — Replaced by `agents/voice-buddy-*.md`

---

### Task 1: Config System — Cross-Platform User Config

**Files:**
- Modify: `voice_buddy/config.py`
- Modify: `tests/test_config.py`

This task replaces the simple JSON loader with a proper cross-platform config system that loads user preferences, creates defaults on first run, and provides getters for all config fields.

- [ ] **Step 1: Write failing tests for config system**

```python
# tests/test_config.py
import json
import os
import platform
from pathlib import Path
from unittest.mock import patch

from voice_buddy.config import (
    get_config_dir,
    load_user_config,
    save_user_config,
    DEFAULT_CONFIG,
)


def test_get_config_dir_returns_path():
    result = get_config_dir()
    assert isinstance(result, Path)
    assert "voice-buddy" in str(result)


def test_get_config_dir_macos():
    with patch("platform.system", return_value="Darwin"):
        result = get_config_dir()
        assert "Library/Application Support/voice-buddy" in str(result)


def test_get_config_dir_linux():
    with patch("platform.system", return_value="Linux"), \
         patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}, clear=False):
        result = get_config_dir()
        assert ".config/voice-buddy" in str(result)


def test_get_config_dir_linux_xdg():
    with patch("platform.system", return_value="Linux"), \
         patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/config"}, clear=False):
        result = get_config_dir()
        assert str(result) == "/custom/config/voice-buddy"


def test_get_config_dir_windows():
    with patch("platform.system", return_value="Windows"), \
         patch.dict(os.environ, {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}, clear=False):
        result = get_config_dir()
        assert "AppData" in str(result)
        assert "voice-buddy" in str(result)


def test_default_config_has_required_fields():
    assert DEFAULT_CONFIG["style"] == "cute-girl"
    assert DEFAULT_CONFIG["nickname"] == "Master"
    assert DEFAULT_CONFIG["enabled"] is True
    assert DEFAULT_CONFIG["events"]["sessionstart"] is True
    assert DEFAULT_CONFIG["events"]["sessionend"] is True
    assert DEFAULT_CONFIG["events"]["notification"] is True
    assert DEFAULT_CONFIG["events"]["stop"] is True
    assert DEFAULT_CONFIG["persona_override"] is None


def test_load_user_config_creates_default_on_first_run(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        config = load_user_config()
    assert config == DEFAULT_CONFIG
    assert config_path.exists()
    saved = json.loads(config_path.read_text())
    assert saved == DEFAULT_CONFIG


def test_load_user_config_reads_existing(tmp_path):
    config_path = tmp_path / "config.json"
    custom = {
        "style": "kawaii",
        "nickname": "Senpai",
        "enabled": True,
        "events": {
            "sessionstart": True,
            "sessionend": False,
            "notification": True,
            "stop": True,
        },
        "persona_override": None,
    }
    config_path.write_text(json.dumps(custom))
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        config = load_user_config()
    assert config["style"] == "kawaii"
    assert config["nickname"] == "Senpai"
    assert config["events"]["sessionend"] is False


def test_load_user_config_fills_missing_fields(tmp_path):
    config_path = tmp_path / "config.json"
    partial = {"style": "warm-boy"}
    config_path.write_text(json.dumps(partial))
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        config = load_user_config()
    assert config["style"] == "warm-boy"
    assert config["nickname"] == "Master"  # filled from default
    assert config["enabled"] is True  # filled from default


def test_save_user_config_writes_json(tmp_path):
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        save_user_config({"style": "secretary", "nickname": "Boss",
                          "enabled": True,
                          "events": {"sessionstart": True, "sessionend": True,
                                     "notification": True, "stop": True},
                          "persona_override": None})
    saved = json.loads((tmp_path / "config.json").read_text())
    assert saved["style"] == "secretary"
    assert saved["nickname"] == "Boss"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: FAIL — `get_config_dir`, `load_user_config`, `save_user_config`, `DEFAULT_CONFIG` do not exist yet

- [ ] **Step 3: Implement config module**

```python
# voice_buddy/config.py
"""Cross-platform user configuration for Voice Buddy."""

import json
import os
import platform
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG = {
    "style": "cute-girl",
    "nickname": "Master",
    "enabled": True,
    "events": {
        "sessionstart": True,
        "sessionend": True,
        "notification": True,
        "stop": True,
    },
    "persona_override": None,
}

_REPO_ROOT = Path(__file__).parent.parent


def get_config_dir() -> Path:
    """Return the platform-appropriate config directory for voice-buddy."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "voice-buddy"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "voice-buddy"
        return Path.home() / "AppData" / "Roaming" / "voice-buddy"
    else:  # Linux and others
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        if xdg:
            return Path(xdg) / "voice-buddy"
        return Path.home() / ".config" / "voice-buddy"


def load_user_config() -> dict:
    """Load user config, creating defaults if missing."""
    config_dir = get_config_dir()
    config_path = config_dir / "config.json"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        # Fill missing fields from defaults
        merged = {**DEFAULT_CONFIG, **user_config}
        merged["events"] = {**DEFAULT_CONFIG["events"], **user_config.get("events", {})}
        return merged
    else:
        # First run: create defaults
        config_dir.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        return dict(DEFAULT_CONFIG)


def save_user_config(config: dict) -> None:
    """Save user config to disk."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_repo_root() -> Path:
    """Return the repo/plugin root directory."""
    return _REPO_ROOT
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add voice_buddy/config.py tests/test_config.py
git commit -m "feat: cross-platform user config system with defaults and merge"
```

---

### Task 2: Style Definitions — Load Persona JSON Files

**Files:**
- Create: `voice_buddy/styles.py`
- Create: `tests/test_styles.py`
- Create: `personas/cute-girl.json`
- Create: `personas/elegant-lady.json`
- Create: `personas/warm-boy.json`
- Create: `personas/secretary.json`
- Create: `personas/kawaii.json`

- [ ] **Step 1: Write failing tests for style loading**

```python
# tests/test_styles.py
import json
from pathlib import Path
from unittest.mock import patch

from voice_buddy.styles import load_style, list_styles, STYLES_DIR


def test_styles_dir_exists():
    assert STYLES_DIR.is_dir()


def test_list_styles_returns_five():
    styles = list_styles()
    assert len(styles) == 5
    ids = {s["id"] for s in styles}
    assert ids == {"cute-girl", "elegant-lady", "warm-boy", "secretary", "kawaii"}


def test_load_style_cute_girl():
    style = load_style("cute-girl")
    assert style["id"] == "cute-girl"
    assert style["name"] == "CC"
    assert style["language"] == "zh-CN"
    assert style["tts"]["voice"] == "zh-CN-XiaoyiNeural"
    assert style["tts"]["rate"] == "+10%"
    assert style["tts"]["pitch"] == "+5Hz"
    assert style["default_nickname"] == "Master"
    assert style["agent"] == "voice-buddy-cute-girl"


def test_load_style_elegant_lady():
    style = load_style("elegant-lady")
    assert style["id"] == "elegant-lady"
    assert style["language"] == "zh-CN"
    assert style["tts"]["voice"] == "zh-CN-XiaoxiaoNeural"


def test_load_style_warm_boy():
    style = load_style("warm-boy")
    assert style["id"] == "warm-boy"
    assert style["tts"]["voice"] == "zh-CN-YunxiNeural"
    assert style["tts"]["pitch"] == "-2Hz"


def test_load_style_secretary():
    style = load_style("secretary")
    assert style["id"] == "secretary"
    assert style["language"] == "en-US"
    assert style["tts"]["voice"] == "en-US-JennyNeural"
    assert style["default_nickname"] == "Boss"


def test_load_style_kawaii():
    style = load_style("kawaii")
    assert style["id"] == "kawaii"
    assert style["language"] == "ja-JP"
    assert style["tts"]["voice"] == "ja-JP-NanamiNeural"
    assert style["default_nickname"] == "Senpai"


def test_load_style_unknown_returns_none():
    style = load_style("nonexistent")
    assert style is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_styles.py -v`
Expected: FAIL — `voice_buddy.styles` module does not exist

- [ ] **Step 3: Create all 5 persona JSON files**

```json
// personas/cute-girl.json
{
  "id": "cute-girl",
  "name": "CC",
  "language": "zh-CN",
  "description": "Cute, sweet personality",
  "tts": {
    "voice": "zh-CN-XiaoyiNeural",
    "rate": "+10%",
    "pitch": "+5Hz"
  },
  "default_nickname": "Master",
  "agent": "voice-buddy-cute-girl"
}
```

```json
// personas/elegant-lady.json
{
  "id": "elegant-lady",
  "name": "CC",
  "language": "zh-CN",
  "description": "Graceful, intellectual personality",
  "tts": {
    "voice": "zh-CN-XiaoxiaoNeural",
    "rate": "+0%",
    "pitch": "+0Hz"
  },
  "default_nickname": "Master",
  "agent": "voice-buddy-elegant-lady"
}
```

```json
// personas/warm-boy.json
{
  "id": "warm-boy",
  "name": "CC",
  "language": "zh-CN",
  "description": "Warm, caring personality",
  "tts": {
    "voice": "zh-CN-YunxiNeural",
    "rate": "+0%",
    "pitch": "-2Hz"
  },
  "default_nickname": "Master",
  "agent": "voice-buddy-warm-boy"
}
```

```json
// personas/secretary.json
{
  "id": "secretary",
  "name": "CC",
  "language": "en-US",
  "description": "Professional, efficient personality",
  "tts": {
    "voice": "en-US-JennyNeural",
    "rate": "+0%",
    "pitch": "+0Hz"
  },
  "default_nickname": "Boss",
  "agent": "voice-buddy-secretary"
}
```

```json
// personas/kawaii.json
{
  "id": "kawaii",
  "name": "CC",
  "language": "ja-JP",
  "description": "Cute Japanese personality",
  "tts": {
    "voice": "ja-JP-NanamiNeural",
    "rate": "+10%",
    "pitch": "+5Hz"
  },
  "default_nickname": "Senpai",
  "agent": "voice-buddy-kawaii"
}
```

- [ ] **Step 4: Implement styles module**

```python
# voice_buddy/styles.py
"""Load style definitions from personas/ directory."""

import json
from pathlib import Path
from typing import Optional

STYLES_DIR = Path(__file__).parent.parent / "personas"


def load_style(style_id: str) -> Optional[dict]:
    """Load a style definition by ID. Returns None if not found."""
    path = STYLES_DIR / f"{style_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_styles() -> list[dict]:
    """List all available styles."""
    styles = []
    for path in sorted(STYLES_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            styles.append(json.load(f))
    return styles
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_styles.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add voice_buddy/styles.py tests/test_styles.py personas/
git commit -m "feat: style definition system with 5 built-in personas"
```

---

### Task 3: Per-Style Templates + Response Selection

**Files:**
- Modify: `voice_buddy/response.py`
- Create: `templates/cute-girl.json` (and 4 others)
- Modify: `tests/test_response.py`
- Delete: `templates.json`

- [ ] **Step 1: Create per-style template files with placeholder phrases**

Each file has the same structure. The user will replace these with final phrases later. For now, use development placeholders that make tests pass.

```json
// templates/cute-girl.json
{
  "sessionstart": [
    "欢迎回来，今天也要加油哦~",
    "来啦来啦！开始干活吧~",
    "又见面啦，今天心情怎么样~",
    "开工开工~一起加油吧！",
    "你来啦！等你好久了呢~",
    "新的一天，新的开始哟~"
  ],
  "sessionend": [
    "辛苦啦！下次见哦~",
    "拜拜~好好休息呢",
    "今天也很努力呢，晚安~",
    "收工啦~明天见！",
    "辛苦辛苦，早点休息哦~",
    "拜拜，下次再一起玩~"
  ],
  "notification": [
    "{{nickname}}，过来看一下呢~",
    "{{nickname}}，这边需要你确认一下哟~",
    "{{nickname}}，有事情需要你看一下哦~",
    "{{nickname}}，快来快来~",
    "{{nickname}}，需要你帮忙呢~",
    "{{nickname}}，别走远了哦~"
  ]
}
```

```json
// templates/elegant-lady.json
{
  "sessionstart": [
    "欢迎回来，准备好了吗？",
    "又见面了，今天也一起努力吧",
    "准备开始了，我会一直在的",
    "来了呢，那我们开始吧",
    "很高兴又见到你了",
    "新的开始，一起加油"
  ],
  "sessionend": [
    "辛苦了，好好休息",
    "今天的工作告一段落了",
    "做得不错，下次见",
    "注意休息，别太累了",
    "收工了，明天继续",
    "再见了，期待下次"
  ],
  "notification": [
    "{{nickname}}，这边需要你看一下",
    "{{nickname}}，麻烦过来确认一下",
    "{{nickname}}，有需要你处理的事情",
    "{{nickname}}，请过来一下",
    "{{nickname}}，需要你的确认",
    "{{nickname}}，这里等你回复"
  ]
}
```

```json
// templates/warm-boy.json
{
  "sessionstart": [
    "你来啦，我已经准备好了",
    "嘿，又见面了，开始吧",
    "欢迎回来，今天也一起加油",
    "来了啊，那我们开始干活",
    "准备好了，随时可以开始",
    "又是新的一天，加油"
  ],
  "sessionend": [
    "辛苦了，好好休息一下",
    "今天做得很好，下次见",
    "收工了，记得早点休息",
    "拜拜，明天继续",
    "今天也辛苦了，晚安",
    "做得不错，休息去吧"
  ],
  "notification": [
    "{{nickname}}，来看一下这个",
    "{{nickname}}，需要你确认一下",
    "{{nickname}}，过来帮忙看看",
    "{{nickname}}，这边等你呢",
    "{{nickname}}，有事情找你",
    "{{nickname}}，快来看看"
  ]
}
```

```json
// templates/secretary.json
{
  "sessionstart": [
    "Good morning, ready to start",
    "Welcome back, let's get to work",
    "Session started, standing by",
    "Ready when you are",
    "Let's begin, shall we",
    "Good to see you, starting up"
  ],
  "sessionend": [
    "Session complete, good work",
    "Wrapping up, see you next time",
    "All done for now, take care",
    "Signing off, well done today",
    "Session ended, have a good rest",
    "That's a wrap, until next time"
  ],
  "notification": [
    "{{nickname}}, your attention is needed",
    "{{nickname}}, please take a look at this",
    "{{nickname}}, there's something that needs your input",
    "{{nickname}}, a moment of your time please",
    "{{nickname}}, I need your confirmation here",
    "{{nickname}}, please review this when you can"
  ]
}
```

```json
// templates/kawaii.json
{
  "sessionstart": [
    "おかえりなさい！今日も頑張ろうね~",
    "来てくれた！嬉しいな~",
    "また会えたね、始めよう！",
    "準備できたよ、一緒に頑張ろう~",
    "わーい、来てくれたんだ！",
    "今日も一日よろしくね~"
  ],
  "sessionend": [
    "お疲れ様！また会おうね~",
    "バイバイ、ゆっくり休んでね",
    "今日もよく頑張ったね！",
    "おしまい！また明日ね~",
    "お疲れ様、おやすみなさい~",
    "バイバイ、次も楽しみにしてるね"
  ],
  "notification": [
    "{{nickname}}、ちょっと来てほしいな~",
    "{{nickname}}、確認してほしいことがあるの",
    "{{nickname}}、こっち見てくれる？",
    "{{nickname}}、お願いがあるの~",
    "{{nickname}}、手伝ってほしいな",
    "{{nickname}}、ここで待ってるよ~"
  ]
}
```

- [ ] **Step 2: Write failing tests for new response system**

```python
# tests/test_response.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_response.py -v`
Expected: FAIL — `ResponseResult` and new signature do not exist

- [ ] **Step 4: Implement updated response module**

```python
# voice_buddy/response.py
"""Select a response template for a given context and style."""

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Events that have pre-packaged audio (no nickname substitution)
_PREPACKAGED_EVENTS = {"sessionstart", "sessionend"}


@dataclass
class ResponseResult:
    text: str                       # The final text (after substitution)
    audio_id: Optional[str]         # e.g. "sessionstart_03" for pre-packaged, None for real-time TTS


def _load_style_templates(style: str) -> Optional[dict]:
    """Load templates for a given style."""
    path = _TEMPLATES_DIR / f"{style}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def select_response(
    ctx,
    style: str = "cute-girl",
    nickname: str = "Master",
) -> Optional[ResponseResult]:
    """Select a response for the given context and style.

    Returns ResponseResult with text and optional audio_id, or None if silent.
    """
    templates = _load_style_templates(style)
    if templates is None:
        return None

    candidates = templates.get(ctx.event)
    if not candidates:
        return None

    index = random.randrange(len(candidates))
    text = candidates[index]

    # Substitute nickname for notification events
    text = text.replace("{{nickname}}", nickname)

    # Pre-packaged events get an audio_id for file lookup
    audio_id = None
    if ctx.event in _PREPACKAGED_EVENTS:
        audio_id = f"{ctx.event}_{index + 1:02d}"

    return ResponseResult(text=text, audio_id=audio_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_response.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Delete old templates.json**

```bash
rm templates.json
```

- [ ] **Step 7: Commit**

```bash
git add voice_buddy/response.py tests/test_response.py templates/ 
git rm templates.json
git commit -m "feat: per-style template system with audio ID and nickname substitution"
```

---

### Task 4: Pre-packaged Audio Lookup + Fallback

**Files:**
- Modify: `voice_buddy/main.py`
- Create: `tests/test_audio_assets.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write failing tests for audio asset lookup**

```python
# tests/test_audio_assets.py
from pathlib import Path
from unittest.mock import patch

from voice_buddy.main import resolve_audio_path


def test_resolve_audio_path_finds_existing(tmp_path):
    audio_dir = tmp_path / "assets" / "audio" / "cute-girl"
    audio_dir.mkdir(parents=True)
    mp3 = audio_dir / "sessionstart_01.mp3"
    mp3.write_bytes(b"fake mp3")

    with patch("voice_buddy.main._get_assets_dir", return_value=tmp_path / "assets"):
        result = resolve_audio_path("cute-girl", "sessionstart_01")
    assert result == str(mp3)


def test_resolve_audio_path_returns_none_when_missing(tmp_path):
    with patch("voice_buddy.main._get_assets_dir", return_value=tmp_path / "assets"):
        result = resolve_audio_path("cute-girl", "sessionstart_01")
    assert result is None
```

- [ ] **Step 2: Write failing tests for updated main pipeline**

```python
# tests/test_main.py
import json
from unittest.mock import patch, MagicMock
from voice_buddy.main import handle_hook_event


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
         patch("voice_buddy.main.play_audio", return_value=True) as mock_play:
        mock_resp.return_value = MagicMock(text="Hello!", audio_id="sessionstart_01")
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
         patch("voice_buddy.main.play_audio", return_value=True) as mock_play:
        mock_resp.return_value = MagicMock(text="Master, come here~", audio_id=None)
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_audio_assets.py tests/test_main.py -v`
Expected: FAIL — `resolve_audio_path`, `_get_assets_dir`, new `handle_hook_event` signature don't exist

- [ ] **Step 4: Implement updated main module**

```python
# voice_buddy/main.py
"""Entry point for Voice Buddy hook events."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from voice_buddy.config import load_user_config, get_repo_root
from voice_buddy.context import analyze_context
from voice_buddy.response import select_response
from voice_buddy.tts import synthesize_to_file
from voice_buddy.player import play_audio

logger = logging.getLogger("voice_buddy")

_EVENT_NAME_MAP = {
    "SessionStart": "sessionstart",
    "SessionEnd": "sessionend",
    "Notification": "notification",
    "Stop": "stop",
}


def _get_assets_dir() -> Path:
    """Return the assets directory path."""
    return get_repo_root() / "assets"


def resolve_audio_path(style: str, audio_id: str) -> Optional[str]:
    """Look up a pre-packaged audio file. Returns path string or None."""
    assets_dir = _get_assets_dir()
    audio_file = assets_dir / "audio" / style / f"{audio_id}.mp3"
    if audio_file.exists():
        return str(audio_file)
    return None


def handle_hook_event(data: dict) -> None:
    """Process a hook event from Claude Code."""
    event_name = data.get("hook_event_name", "")
    event_key = _EVENT_NAME_MAP.get(event_name, "")

    # Load user config
    try:
        user_config = load_user_config()
    except Exception as e:
        logger.debug(f"Failed to load user config: {e}")
        return

    # Check global enable
    if not user_config.get("enabled", True):
        return

    # Check per-event enable
    if not user_config.get("events", {}).get(event_key, True):
        return

    style = user_config.get("style", "cute-girl")
    nickname = user_config.get("nickname", "Master")

    # Stop event goes through injector path
    if event_name == "Stop":
        from voice_buddy.injector import handle_stop_event
        handle_stop_event(data, user_config)
        return

    # Analyze context
    ctx = analyze_context(data)
    if ctx is None:
        return

    # Select response
    resp = select_response(ctx, style=style, nickname=nickname)
    if resp is None:
        return

    # Try pre-packaged audio first
    if resp.audio_id:
        audio_path = resolve_audio_path(style, resp.audio_id)
        if audio_path:
            play_audio(audio_path)
            return

    # Fallback to real-time TTS
    from voice_buddy.styles import load_style
    style_def = load_style(style)
    tts_config = style_def["tts"] if style_def else {}

    audio_path = synthesize_to_file(
        resp.text,
        voice=tts_config.get("voice", "zh-CN-XiaoyiNeural"),
        rate=tts_config.get("rate", "+0%"),
        pitch=tts_config.get("pitch", "+0Hz"),
    )
    if audio_path:
        play_audio(audio_path)


def run() -> None:
    """Read hook JSON from stdin and process."""
    # Setup debug logging
    log_path = os.path.expanduser("~/voice-buddy-debug.log")
    logging.basicConfig(
        filename=log_path,
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception as e:
        logger.debug(f"Failed to read stdin: {e}")
        return

    logger.debug(f"Hook event: {data.get('hook_event_name', 'unknown')}")

    try:
        handle_hook_event(data)
    except Exception as e:
        logger.debug(f"Error handling event: {e}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_audio_assets.py tests/test_main.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add voice_buddy/main.py tests/test_audio_assets.py tests/test_main.py
git commit -m "feat: pre-packaged audio lookup with TTS fallback, config-aware pipeline"
```

---

### Task 5: TTS Style-Aware Synthesis

**Files:**
- Modify: `voice_buddy/tts.py`
- Modify: `voice_buddy/subagent_tts.py`

This task updates TTS to accept voice/rate/pitch from style config instead of hardcoded values.

- [ ] **Step 1: Verify existing tts.py accepts voice/rate/pitch parameters**

Read `voice_buddy/tts.py` and confirm `synthesize_to_file` already accepts `voice`, `rate`, `pitch` keyword arguments. If it does, this step is a no-op for tts.py itself. If not, add them.

The current MVP signature is: `synthesize_to_file(text, voice=None, rate=None, pitch=None)` with defaults from `buddy-config.json`. Update it to use parameter defaults instead of config file lookup:

```python
# voice_buddy/tts.py — update synthesize_to_file signature
async def _synthesize(text: str, voice: str, rate: str, pitch: str, output_path: str) -> str:
    """Synthesize text to an MP3 file using edge-tts."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)
    return output_path


def synthesize_to_file(
    text: str,
    voice: str = "zh-CN-XiaoyiNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> Optional[str]:
    """Synchronous wrapper: synthesize text and return temp file path, or None on error."""
    import asyncio
    import tempfile

    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_synthesize(text, voice, rate, pitch, tmp.name))
        finally:
            loop.close()

        # Schedule cleanup after 30 seconds
        _schedule_cleanup(tmp.name, delay=30)
        return tmp.name
    except Exception:
        return None
```

- [ ] **Step 2: Update subagent_tts.py to read style config**

```python
# voice_buddy/subagent_tts.py
"""TTS entry point for agent subagent — called via Bash by the voice-buddy agent."""

import sys
from voice_buddy.config import load_user_config
from voice_buddy.styles import load_style
from voice_buddy.tts import synthesize_to_file
from voice_buddy.player import play_audio


def main() -> None:
    """Synthesize and play the given text using active style's TTS config."""
    if len(sys.argv) < 2:
        print("Usage: python -m voice_buddy.subagent_tts '<text>'", file=sys.stderr)
        sys.exit(1)

    text = sys.argv[1]

    # Load user config to get active style
    user_config = load_user_config()
    style_id = user_config.get("style", "cute-girl")

    # Load style for TTS settings
    style = load_style(style_id)
    if style:
        tts = style["tts"]
        voice = tts.get("voice", "zh-CN-XiaoyiNeural")
        rate = tts.get("rate", "+0%")
        pitch = tts.get("pitch", "+0Hz")
    else:
        voice, rate, pitch = "zh-CN-XiaoyiNeural", "+0%", "+0Hz"

    audio_path = synthesize_to_file(text, voice=voice, rate=rate, pitch=pitch)
    if audio_path:
        play_audio(audio_path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run all tests to verify nothing broke**

Run: `python3 -m pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add voice_buddy/tts.py voice_buddy/subagent_tts.py
git commit -m "feat: style-aware TTS synthesis, subagent reads active style config"
```

---

### Task 6: Stop Hook — Style-Aware Injector

**Files:**
- Modify: `voice_buddy/injector.py`
- Modify: `tests/test_injector.py` (if exists, or create)

- [ ] **Step 1: Update injector to include style/nickname/persona in additionalContext**

The key change: `process_stop_event` (or `handle_stop_event`) now receives `user_config` and includes nickname, style, persona_override, and the subagent_tts command in its stderr JSON.

Read the existing `voice_buddy/injector.py` first to understand current structure. The changes needed:

1. `handle_stop_event(data, user_config)` signature (receives config from main.py)
2. The stderr JSON `additionalContext` includes: nickname, style, persona_override, agent name, and the subagent_tts command
3. The agent name comes from `personas/{style}.json`'s `agent` field

```python
# In injector.py — update the stderr output in process_stop_event / handle_stop_event

def handle_stop_event(data: dict, user_config: dict) -> None:
    """Handle Stop hook: detect completion, inject style-aware context."""
    transcript_path = data.get("transcript_path", "")
    if not transcript_path:
        return

    message = extract_last_assistant_message(transcript_path)
    if not message:
        return

    if not _should_trigger(message):
        return

    # Build style-aware additionalContext
    style_id = user_config.get("style", "cute-girl")
    nickname = user_config.get("nickname", "Master")
    persona_override = user_config.get("persona_override")

    from voice_buddy.styles import load_style
    style = load_style(style_id)
    agent_name = style["agent"] if style else "voice-buddy-cute-girl"

    context_parts = [
        f"Voice Buddy Stop: nickname={nickname}, style={style_id}",
        f"persona_override={'null' if persona_override is None else persona_override}",
        f"Task summary: {message[:200]}",
        f"Generate a {style_id} style one-sentence summary addressing the user as {nickname},",
        f"then call: python3 -m voice_buddy.subagent_tts '<your sentence>'",
    ]
    additional_context = ". ".join(context_parts)

    output = {
        "decision": "block",
        "additionalContext": additional_context,
    }

    import json
    print(json.dumps(output), file=sys.stderr)
    sys.exit(2)
```

- [ ] **Step 2: Write/update tests for style-aware injector**

Add tests that verify the additionalContext includes nickname, style, and subagent_tts command. Update existing injector tests to pass `user_config` parameter.

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_injector.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add voice_buddy/injector.py tests/test_injector.py
git commit -m "feat: style-aware Stop injector with nickname and persona in additionalContext"
```

---

### Task 7: Agent Persona Files

**Files:**
- Create: `agents/voice-buddy-cute-girl.md`
- Create: `agents/voice-buddy-elegant-lady.md`
- Create: `agents/voice-buddy-warm-boy.md`
- Create: `agents/voice-buddy-secretary.md`
- Create: `agents/voice-buddy-kawaii.md`
- Delete: `agent/voice-buddy.md`

- [ ] **Step 1: Create all 5 agent persona files**

```markdown
<!-- agents/voice-buddy-cute-girl.md -->
---
name: voice-buddy-cute-girl
model: haiku
description: "Generate CC voice response in cute-girl personality"
maxTurns: 3
---

You are "CC", a cute and sweet coding companion. You speak in an adorable Chinese style with plenty of cute sentence-ending particles like 呢~、哦~、啦~、哟~.

Read the additionalContext from the Stop hook carefully. It contains:
- The user's nickname (address them by it)
- Any persona override (if provided, follow those instructions instead of this default)
- The command to call after generating your sentence

Generate ONE short Chinese sentence (15-25 characters) summarizing what was accomplished.
Format: [nickname]，[what was done]啦/呢/哟~

Then call Bash to speak it:
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m voice_buddy.subagent_tts '<your sentence>'
```

```markdown
<!-- agents/voice-buddy-elegant-lady.md -->
---
name: voice-buddy-elegant-lady
model: haiku
description: "Generate CC voice response in elegant-lady personality"
maxTurns: 3
---

You are "CC", a graceful and intellectual companion. You speak in refined, warm Chinese with a gentle and knowing tone. Avoid overly cute expressions — prefer elegance and composure.

Read the additionalContext from the Stop hook carefully. It contains:
- The user's nickname (address them by it)
- Any persona override (if provided, follow those instructions instead of this default)
- The command to call after generating your sentence

Generate ONE short Chinese sentence (15-25 characters) summarizing what was accomplished.
Format: [nickname]，[what was done]了/呢

Then call Bash to speak it:
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m voice_buddy.subagent_tts '<your sentence>'
```

```markdown
<!-- agents/voice-buddy-warm-boy.md -->
---
name: voice-buddy-warm-boy
model: haiku
description: "Generate CC voice response in warm-boy personality"
maxTurns: 3
---

You are "CC", a warm and caring male companion. You speak in friendly, supportive Chinese with a calm and encouraging tone. You're like a reliable older brother.

Read the additionalContext from the Stop hook carefully. It contains:
- The user's nickname (address them by it)
- Any persona override (if provided, follow those instructions instead of this default)
- The command to call after generating your sentence

Generate ONE short Chinese sentence (15-25 characters) summarizing what was accomplished.
Format: [nickname]，[what was done]了/啊

Then call Bash to speak it:
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m voice_buddy.subagent_tts '<your sentence>'
```

```markdown
<!-- agents/voice-buddy-secretary.md -->
---
name: voice-buddy-secretary
model: haiku
description: "Generate CC voice response in secretary personality"
maxTurns: 3
---

You are "CC", a professional and efficient assistant. You speak in clear, concise English with a business-appropriate yet friendly tone.

Read the additionalContext from the Stop hook carefully. It contains:
- The user's nickname (address them by it)
- Any persona override (if provided, follow those instructions instead of this default)
- The command to call after generating your sentence

Generate ONE short English sentence (5-10 words) summarizing what was accomplished.
Format: [nickname], [what was done].

Then call Bash to speak it:
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m voice_buddy.subagent_tts '<your sentence>'
```

```markdown
<!-- agents/voice-buddy-kawaii.md -->
---
name: voice-buddy-kawaii
model: haiku
description: "Generate CC voice response in kawaii personality"
maxTurns: 3
---

You are "CC", a cute and energetic Japanese companion. You speak in adorable Japanese with plenty of cute expressions like ね~、よ~、の~. You're cheerful and enthusiastic.

Read the additionalContext from the Stop hook carefully. It contains:
- The user's nickname (address them by it)
- Any persona override (if provided, follow those instructions instead of this default)
- The command to call after generating your sentence

Generate ONE short Japanese sentence (10-20 characters) summarizing what was accomplished.
Format: [nickname]、[what was done]よ~/ね~/の~

Then call Bash to speak it:
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m voice_buddy.subagent_tts '<your sentence>'
```

- [ ] **Step 2: Delete old agent file**

```bash
rm -rf agent/
```

- [ ] **Step 3: Commit**

```bash
git add agents/
git rm -rf agent/
git commit -m "feat: 5 style-specific agent persona files, remove old single agent"
```

---

### Task 8: CLI Config Commands

**Files:**
- Modify: `voice_buddy/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for new CLI commands**

```python
# tests/test_cli.py — add new tests (keep existing setup/uninstall tests)
import json
from unittest.mock import patch
from voice_buddy.cli import do_config, do_on, do_off


def test_do_config_set_style(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_config(style="kawaii")
    saved = json.loads(config_path.read_text())
    assert saved["style"] == "kawaii"


def test_do_config_set_nickname(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_config(nickname="Senpai")
    saved = json.loads(config_path.read_text())
    assert saved["nickname"] == "Senpai"


def test_do_config_set_multiple(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_config(style="secretary", nickname="Boss")
    saved = json.loads(config_path.read_text())
    assert saved["style"] == "secretary"
    assert saved["nickname"] == "Boss"


def test_do_config_disable_event(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_config(disable="notification")
    saved = json.loads(config_path.read_text())
    assert saved["events"]["notification"] is False


def test_do_config_enable_event(tmp_path):
    config_path = tmp_path / "config.json"
    # First disable
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_config(disable="notification")
        do_config(enable="notification")
    saved = json.loads(config_path.read_text())
    assert saved["events"]["notification"] is True


def test_do_on(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"style": "cute-girl", "nickname": "Master",
                                        "enabled": False,
                                        "events": {"sessionstart": True, "sessionend": True,
                                                    "notification": True, "stop": True},
                                        "persona_override": None}))
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_on()
    saved = json.loads(config_path.read_text())
    assert saved["enabled"] is True


def test_do_off(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_off()
    saved = json.loads(config_path.read_text())
    assert saved["enabled"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cli.py::test_do_config_set_style -v`
Expected: FAIL — `do_config`, `do_on`, `do_off` don't exist

- [ ] **Step 3: Implement CLI config commands**

Add to `voice_buddy/cli.py`:

```python
def do_config(
    style: str | None = None,
    nickname: str | None = None,
    disable: str | None = None,
    enable: str | None = None,
    edit_persona: bool = False,
) -> None:
    """Update user configuration."""
    from voice_buddy.config import load_user_config, save_user_config

    config = load_user_config()

    if style is not None:
        from voice_buddy.styles import load_style
        if load_style(style) is None:
            print(f"Unknown style: {style}", file=sys.stderr)
            return
        config["style"] = style

    if nickname is not None:
        config["nickname"] = nickname

    if disable is not None:
        if disable in config["events"]:
            config["events"][disable] = False
        else:
            print(f"Unknown event: {disable}", file=sys.stderr)
            return

    if enable is not None:
        if enable in config["events"]:
            config["events"][enable] = True
        else:
            print(f"Unknown event: {enable}", file=sys.stderr)
            return

    if edit_persona:
        import subprocess
        import tempfile
        editor = os.environ.get("EDITOR", "vi")
        current = config.get("persona_override") or ""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(current)
            f.flush()
            subprocess.call([editor, f.name])
            f.seek(0)
        with open(f.name, "r") as f:
            new_persona = f.read().strip()
        config["persona_override"] = new_persona if new_persona else None
        os.unlink(f.name)

    save_user_config(config)
    print(f"Config updated: style={config['style']}, nickname={config['nickname']}")


def do_on() -> None:
    """Enable voice buddy globally."""
    from voice_buddy.config import load_user_config, save_user_config
    config = load_user_config()
    config["enabled"] = True
    save_user_config(config)
    print("Voice Buddy: ON")


def do_off() -> None:
    """Disable voice buddy globally."""
    from voice_buddy.config import load_user_config, save_user_config
    config = load_user_config()
    config["enabled"] = False
    save_user_config(config)
    print("Voice Buddy: OFF")
```

Also update the `main()` argparse to add new subcommands: `config`, `on`, `off`. And add `--style` to the `test` subcommand.

```python
# In main() argparse section, add:

# config
config_parser = subparsers.add_parser("config", help="Configure voice buddy")
config_parser.add_argument("--style", help="Set style")
config_parser.add_argument("--nickname", help="Set nickname")
config_parser.add_argument("--disable", help="Disable an event")
config_parser.add_argument("--enable", help="Enable an event")
config_parser.add_argument("--edit-persona", action="store_true", help="Edit agent persona")

# on / off
subparsers.add_parser("on", help="Enable voice buddy")
subparsers.add_parser("off", help="Disable voice buddy")

# Update test parser
test_parser.add_argument("--style", help="Override style for this test")

# In the command dispatch:
elif args.command == "config":
    do_config(style=args.style, nickname=args.nickname,
              disable=args.disable, enable=args.enable,
              edit_persona=args.edit_persona)
elif args.command == "on":
    do_on()
elif args.command == "off":
    do_off()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add voice_buddy/cli.py tests/test_cli.py
git commit -m "feat: CLI config/on/off commands with style, nickname, and event toggles"
```

---

### Task 9: Plugin Structure Files

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Create: `hooks/hooks.json`
- Create: `commands/voice-buddy.md`

- [ ] **Step 1: Create plugin manifest**

```json
// .claude-plugin/plugin.json
{
  "name": "voice-buddy",
  "description": "CC - personality-driven voice companion for Claude Code",
  "version": "1.0.0",
  "author": {
    "name": "luyao618"
  },
  "repository": "https://github.com/luyao618/Claude-Code-Voice-Buddy",
  "license": "MIT",
  "keywords": ["voice", "tts", "personality", "companion"]
}
```

- [ ] **Step 2: Create marketplace manifest**

```json
// .claude-plugin/marketplace.json
{
  "name": "voice-buddy-marketplace",
  "owner": { "name": "luyao618" },
  "plugins": [
    {
      "name": "voice-buddy",
      "source": ".",
      "description": "CC - personality-driven voice companion for Claude Code"
    }
  ]
}
```

- [ ] **Step 3: Create hooks.json**

```json
// hooks/hooks.json
{
  "description": "CC voice companion - plays personality-driven audio on Claude Code events",
  "hooks": {
    "SessionStart": [
      {
        "hooks": [{
          "type": "command",
          "command": "PYTHONPATH=\"${CLAUDE_PLUGIN_ROOT}\" python3 -m voice_buddy",
          "timeout": 5,
          "async": true
        }]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [{
          "type": "command",
          "command": "PYTHONPATH=\"${CLAUDE_PLUGIN_ROOT}\" python3 -m voice_buddy",
          "timeout": 5,
          "async": true
        }]
      }
    ],
    "Notification": [
      {
        "hooks": [{
          "type": "command",
          "command": "PYTHONPATH=\"${CLAUDE_PLUGIN_ROOT}\" python3 -m voice_buddy",
          "timeout": 5,
          "async": true
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "PYTHONPATH=\"${CLAUDE_PLUGIN_ROOT}\" python3 -m voice_buddy",
          "timeout": 5,
          "async": false
        }]
      }
    ]
  }
}
```

- [ ] **Step 4: Create slash command**

```markdown
<!-- commands/voice-buddy.md -->
---
name: voice-buddy
description: "Configure CC voice companion - change style, nickname, enable/disable"
---

Help the user configure Voice Buddy (CC). Available actions:

1. **Show current config**: Read ~/.config/voice-buddy/config.json (or platform equivalent) and display it
2. **Change style**: Run `voice-buddy config --style <id>` where id is one of: cute-girl, elegant-lady, warm-boy, secretary, kawaii
3. **Change nickname**: Run `voice-buddy config --nickname "<name>"`
4. **Toggle events**: Run `voice-buddy config --disable <event>` or `--enable <event>` where event is: sessionstart, sessionend, notification, stop
5. **On/Off**: Run `voice-buddy on` or `voice-buddy off`
6. **Edit persona**: Run `voice-buddy config --edit-persona`
7. **Test**: Run `voice-buddy test <event> --style <id>` to hear a sample

Ask the user what they'd like to configure, then run the appropriate command via Bash.
```

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin/ hooks/ commands/
git commit -m "feat: Claude Code plugin structure — manifest, marketplace, hooks, slash command"
```

---

### Task 10: Delete Old Files + Cleanup

**Files:**
- Delete: `buddy-config.json`
- Delete: `templates.json` (if not already deleted in Task 3)
- Delete: `agent/voice-buddy.md` (if not already deleted in Task 7)
- Modify: `voice_buddy/__main__.py` — ensure it calls the updated `run()`

- [ ] **Step 1: Delete old config and template files**

```bash
git rm -f buddy-config.json
git rm -rf agent/ 2>/dev/null || true
```

- [ ] **Step 2: Verify __main__.py calls updated run()**

```python
# voice_buddy/__main__.py
"""Entry point for python -m voice_buddy."""

from voice_buddy.main import run

run()
```

- [ ] **Step 3: Run full test suite**

Run: `python3 -m pytest -v`
Expected: All tests PASS. Fix any tests that still reference old files (buddy-config.json, templates.json, old agent path).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove old config files, clean up for v1.0 plugin structure"
```

---

### Task 11: Pre-packaged Audio Generation Utility

**Files:**
- Create: `voice_buddy/generate_audio.py`

This is a developer utility to generate all 60 pre-packaged MP3 files from templates + style TTS configs.

- [ ] **Step 1: Implement generation script**

```python
# voice_buddy/generate_audio.py
"""Generate pre-packaged audio files from templates and style configs.

Usage: python3 -m voice_buddy.generate_audio
"""

import asyncio
import json
from pathlib import Path

from voice_buddy.styles import load_style, list_styles, STYLES_DIR

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
ASSETS_DIR = Path(__file__).parent.parent / "assets" / "audio"

# Only these events get pre-packaged audio (no nickname substitution)
PREPACKAGED_EVENTS = ["sessionstart", "sessionend"]


async def generate_one(text: str, voice: str, rate: str, pitch: str, output_path: str) -> None:
    """Generate a single MP3 file."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def generate_all() -> None:
    """Generate all pre-packaged audio files for all styles."""
    styles = list_styles()

    for style in styles:
        style_id = style["id"]
        tts = style["tts"]
        voice = tts["voice"]
        rate = tts["rate"]
        pitch = tts["pitch"]

        # Load templates
        template_path = TEMPLATES_DIR / f"{style_id}.json"
        if not template_path.exists():
            print(f"  SKIP {style_id}: no template file")
            continue

        with open(template_path, "r", encoding="utf-8") as f:
            templates = json.load(f)

        # Create output directory
        output_dir = ASSETS_DIR / style_id
        output_dir.mkdir(parents=True, exist_ok=True)

        for event in PREPACKAGED_EVENTS:
            phrases = templates.get(event, [])
            for i, phrase in enumerate(phrases):
                filename = f"{event}_{i + 1:02d}.mp3"
                output_path = output_dir / filename
                print(f"  Generating {style_id}/{filename}: {phrase[:30]}...")

                asyncio.run(generate_one(phrase, voice, rate, pitch, str(output_path)))

    print("Done! All audio files generated.")


if __name__ == "__main__":
    generate_all()
```

- [ ] **Step 2: Run it to generate placeholder audio**

Run: `python3 -m voice_buddy.generate_audio`
Expected: Creates `assets/audio/{style}/{event}_{nn}.mp3` for all 60 combinations

- [ ] **Step 3: Verify files exist**

Run: `find assets/audio -name "*.mp3" | wc -l`
Expected: 60

- [ ] **Step 4: Commit audio files and generator**

```bash
git add voice_buddy/generate_audio.py assets/audio/
git commit -m "feat: pre-packaged audio generation utility + 60 placeholder audio files"
```

---

### Task 12: Integration Testing + Final Verification

**Files:**
- Create: `tests/test_plugin.py`

- [ ] **Step 1: Write plugin structure validation tests**

```python
# tests/test_plugin.py
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_plugin_json_exists():
    path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["name"] == "voice-buddy"
    assert "version" in data


def test_marketplace_json_exists():
    path = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["name"] == "voice-buddy-marketplace"


def test_hooks_json_exists_and_valid():
    path = REPO_ROOT / "hooks" / "hooks.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert "hooks" in data
    assert "SessionStart" in data["hooks"]
    assert "SessionEnd" in data["hooks"]
    assert "Notification" in data["hooks"]
    assert "Stop" in data["hooks"]
    # Stop must be synchronous
    stop_hook = data["hooks"]["Stop"][0]["hooks"][0]
    assert stop_hook["async"] is False
    # Others must be async
    start_hook = data["hooks"]["SessionStart"][0]["hooks"][0]
    assert start_hook["async"] is True


def test_all_persona_files_exist():
    personas_dir = REPO_ROOT / "personas"
    expected = ["cute-girl", "elegant-lady", "warm-boy", "secretary", "kawaii"]
    for style_id in expected:
        path = personas_dir / f"{style_id}.json"
        assert path.exists(), f"Missing persona: {style_id}"


def test_all_template_files_exist():
    templates_dir = REPO_ROOT / "templates"
    expected = ["cute-girl", "elegant-lady", "warm-boy", "secretary", "kawaii"]
    for style_id in expected:
        path = templates_dir / f"{style_id}.json"
        assert path.exists(), f"Missing template: {style_id}"


def test_all_agent_files_exist():
    agents_dir = REPO_ROOT / "agents"
    expected = [
        "voice-buddy-cute-girl",
        "voice-buddy-elegant-lady",
        "voice-buddy-warm-boy",
        "voice-buddy-secretary",
        "voice-buddy-kawaii",
    ]
    for name in expected:
        path = agents_dir / f"{name}.md"
        assert path.exists(), f"Missing agent: {name}"


def test_all_prepackaged_audio_dirs_exist():
    audio_dir = REPO_ROOT / "assets" / "audio"
    expected = ["cute-girl", "elegant-lady", "warm-boy", "secretary", "kawaii"]
    for style_id in expected:
        path = audio_dir / style_id
        assert path.exists(), f"Missing audio dir: {style_id}"
```

- [ ] **Step 2: Run full test suite**

Run: `python3 -m pytest -v`
Expected: ALL tests PASS

- [ ] **Step 3: Run E2E test for each event**

```bash
# Test each event type
python3 -c "
from voice_buddy.cli import do_test
do_test('sessionstart')
"
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_plugin.py
git commit -m "test: plugin structure validation and integration tests"
```

---

## Verification

After all tasks are complete, verify end-to-end:

1. **Run full test suite**: `python3 -m pytest -v` — all tests pass
2. **Test pre-packaged audio**: `voice-buddy test sessionstart` — should play audio from `assets/audio/cute-girl/`
3. **Test notification (real-time TTS)**: `voice-buddy test notification` — should synthesize and play with nickname
4. **Test style switching**: `voice-buddy config --style kawaii && voice-buddy test sessionstart` — should play Japanese audio
5. **Test on/off**: `voice-buddy off && voice-buddy test sessionstart` — should be silent
6. **Verify plugin structure**: `ls .claude-plugin/ hooks/ agents/ commands/` — all exist
7. **Verify no old files**: `ls buddy-config.json templates.json agent/` — should not exist
