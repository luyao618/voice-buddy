# Voice Buddy v1.0 Design Spec

## Goal

Evolve Voice Buddy from a single-personality MVP into a polished Claude Code plugin with 5 styles, 3 languages, pre-packaged audio caching, user configuration, and standard plugin distribution.

## Architecture Overview

CC is a personality-driven voice companion for Claude Code. v1.0 introduces a multi-style system where CC has 5 personality modes, each with its own language, TTS voice, phrase templates, and agent persona. Audio for fixed phrases is pre-packaged as MP3 assets for near-zero playback latency. User configuration lives outside the plugin directory to survive updates.

---

## 1. Styles

5 built-in styles, unified character name **CC**:

| Style ID | Name | Language | Description | TTS Voice | Rate | Pitch | Default Nickname |
|----------|------|----------|-------------|-----------|------|-------|-----------------|
| `cute-girl` | CC | zh-CN | Cute, sweet | zh-CN-XiaoyiNeural | +10% | +5Hz | Master |
| `elegant-lady` | CC | zh-CN | Graceful, intellectual | zh-CN-XiaoxiaoNeural | +0% | +0Hz | Master |
| `warm-boy` | CC | zh-CN | Warm, caring | zh-CN-YunxiNeural | +0% | -2Hz | Master |
| `secretary` | CC | en-US | Professional, efficient | en-US-JennyNeural | +0% | +0Hz | Boss |
| `kawaii` | CC | ja-JP | Cute Japanese | ja-JP-NanamiNeural | +10% | +5Hz | Senpai |

Default style: `cute-girl`. Default nickname: `Master`.

---

## 2. Phrase Templates

Each style has 18 phrases across 3 events (6 per event):

- **SessionStart** (6 phrases) - no `{{nickname}}`, pre-packaged audio
- **SessionEnd** (6 phrases) - no `{{nickname}}`, pre-packaged audio
- **Notification** (6 phrases) - contains `{{nickname}}` placeholder, real-time TTS

Total: 5 styles x 3 events x 6 phrases = **90 phrases** (provided by user).

Template file per style: `templates/{style}.json`

```json
{
  "sessionstart": [
    "Phrase 1 without nickname",
    "Phrase 2 without nickname",
    "..."
  ],
  "sessionend": ["..."],
  "notification": [
    "{{nickname}}, phrase with nickname~",
    "..."
  ]
}
```

Stop event does not use templates - it uses AI-generated summaries via the agent.

---

## 3. Audio Pipeline

Three distinct paths based on event type:

### 3.1 SessionStart / SessionEnd - Pre-packaged Audio

```
Hook fires
  -> context.py: parse event
  -> config.py: read user config (style, enabled, event toggles)
  -> if disabled: silent exit
  -> response.py: random select phrase, return audio file ID (e.g. sessionstart_03)
  -> player.py: play assets/audio/{style}/{event}_{nn}.mp3
  ~< 100ms latency
```

Audio files use fixed naming: `{event}_{01-06}.mp3`, mapped 1:1 to template array index.

If pre-packaged file is missing (e.g. user customized phrases): fallback to real-time TTS.

### 3.2 Notification - Real-time TTS

```
Hook fires
  -> context.py: parse event
  -> config.py: read config (style, nickname, enabled)
  -> if disabled: silent exit
  -> response.py: random select template, replace {{nickname}}
  -> tts.py: edge-tts synthesize with style's voice/rate/pitch
  -> player.py: play
  ~1 second latency
```

### 3.3 Stop - AI Summary + Real-time TTS

```
Hook fires (synchronous, async: false in hooks.json)
  -> injector.py: detect task completion, read user config (style, nickname, persona_override)
  -> exit code 2, inject additionalContext containing:
     - task summary context (from transcript)
     - user nickname
     - persona_override (if set)
     - style-specific agent name to call
  -> Claude reads additionalContext, calls style-specific agent (e.g. voice-buddy-cute-girl)
  -> agent receives nickname + persona context via additionalContext (NOT from agent .md file)
  -> agent generates one sentence incorporating nickname
  -> agent calls Bash to execute subagent_tts.py for synthesis + playback
  ~3 seconds latency
```

**Critical implementation detail:** The agent .md file contains the *default* personality instructions but does NOT contain runtime variables. Runtime values are injected via the Stop hook's stderr JSON output:

```json
{
  "decision": "block",
  "additionalContext": "Voice Buddy Stop: nickname=Master, style=cute-girl, voice=zh-CN-XiaoyiNeural, rate=+10%, pitch=+5Hz, persona_override=null. Task summary: fixed the parser bug and updated tests. Generate a cute-girl style one-sentence summary addressing the user by nickname, then call: PYTHONPATH=\"${CLAUDE_PLUGIN_ROOT}\" python3 -m voice_buddy.subagent_tts '<your sentence>'"
}
```

This is the standard Claude Code hook protocol: exit code 2 tells Claude to block and read stderr as JSON. The `additionalContext` string is then visible to Claude when it invokes the agent.

The agent's **only TTS execution path** is calling Bash to run `subagent_tts.py`:
```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m voice_buddy.subagent_tts '<generated sentence>'
```

`subagent_tts.py` reads the voice/rate/pitch from the user's active style config and handles synthesis + playback. No inline `python3 -c` in agent prompts.

---

## 4. Pre-packaged Audio Assets

### 4.1 Directory Structure

```
assets/audio/
  cute-girl/
    sessionstart_01.mp3
    sessionstart_02.mp3
    ...
    sessionstart_06.mp3
    sessionend_01.mp3
    ...
    sessionend_06.mp3
  elegant-lady/
    ...
  warm-boy/
    ...
  secretary/
    ...
  kawaii/
    ...
```

Total: 5 styles x 2 events x 6 phrases = **60 pre-packaged MP3 files** (~5-10MB total).

### 4.2 Generation

Audio files are generated once at development time using edge-tts with each style's voice/rate/pitch settings, then committed to the repo as assets.

A dev utility `voice-buddy cache rebuild` re-generates all pre-packaged audio (for development use, not needed by end users).

---

## 5. Style Definition Files

Each style has a definition file: `personas/{style}.json`

```json
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

---

## 6. Agent Personas

One agent definition per style: `agents/voice-buddy-{style}.md`

Each agent has the same structure but different personality instructions:

```markdown
---
name: voice-buddy-{style}
model: haiku
description: "Generate CC voice response in {style} personality"
maxTurns: 3
---

You are "CC", a {personality description} assistant.
Summarize the completed task in one short sentence (15-25 characters).
Tone: {style-specific tone instructions}

IMPORTANT: Read the additionalContext from the Stop hook for:
- The user's nickname (use it to address the user)
- Any persona override (if provided, follow those instructions instead)
- The subagent_tts command to call after generating your sentence

After generating your sentence, call Bash to speak it:
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m voice_buddy.subagent_tts '<YOUR_SENTENCE>'
```

### 6.1 Runtime Injection Mechanism

Agent .md files are **static** and contain no runtime variables. Dynamic values are injected via `additionalContext` in the Stop hook's stderr JSON (see Section 3.3 for exact format).

- **nickname**: injected by `injector.py` from user config
- **persona_override**: if non-null, included in additionalContext, instructing the agent to use custom persona instead of its default
- **TTS config**: `subagent_tts.py` reads voice/rate/pitch from the active style's `personas/{style}.json` at runtime — the agent does NOT need to pass TTS parameters

This avoids any template rendering of agent files and keeps them as pure static assets.

---

## 7. User Configuration

### 7.1 Config File Location

Cross-platform config directory resolution:

| Platform | Path |
|----------|------|
| Linux | `$XDG_CONFIG_HOME/voice-buddy/config.json` (default: `~/.config/voice-buddy/config.json`) |
| macOS | `~/Library/Application Support/voice-buddy/config.json` |
| Windows | `%APPDATA%\voice-buddy\config.json` |

Implementation uses Python's `platformdirs` library (or equivalent logic) to resolve the correct path per platform. The config module exposes a `get_config_dir()` function used by all other modules.

### 7.2 Config Schema

```json
{
  "style": "cute-girl",
  "nickname": "Master",
  "enabled": true,
  "events": {
    "sessionstart": true,
    "sessionend": true,
    "notification": true,
    "stop": true
  },
  "persona_override": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `style` | string | Active style ID |
| `nickname` | string | How CC addresses the user (used in Notification and Stop) |
| `enabled` | bool | Global on/off switch |
| `events` | object | Per-event on/off toggles |
| `persona_override` | string or null | Custom agent persona text, overrides preset when non-null |

### 7.3 First-run Behavior

When config file does not exist at hook trigger time, create it with defaults:
- style: `cute-girl`
- nickname: `Master`
- enabled: `true`
- all events: `true`

### 7.4 CLI Commands

**Interactive mode** (no args):
```bash
voice-buddy config
# Step-by-step guided setup:
# 1. Choose style (1-5 with descriptions)
# 2. Enter nickname
# Done
```

**Parametric mode**:
```bash
voice-buddy config --style kawaii --nickname "Senpai"
```

**On/off controls**:
```bash
voice-buddy on                          # Global enable
voice-buddy off                         # Global disable
voice-buddy config --disable notification   # Disable specific event
voice-buddy config --enable notification    # Enable specific event
```

**Persona editing**:
```bash
voice-buddy config --edit-persona       # Opens $EDITOR with current persona
```

---

## 8. Plugin Structure

Restructure project to Claude Code plugin standard format:

```
Claude-Code-Voice-Buddy/
├── .claude-plugin/
│   ├── plugin.json                 # Plugin manifest
│   └── marketplace.json            # Self-hosted marketplace manifest
├── hooks/
│   ├── hooks.json                  # Hook event declarations (auto-registered)
│   └── voice_buddy_hook.py         # Hook entry script
├── agents/
│   ├── voice-buddy-cute-girl.md
│   ├── voice-buddy-elegant-lady.md
│   ├── voice-buddy-warm-boy.md
│   ├── voice-buddy-secretary.md
│   └── voice-buddy-kawaii.md
├── commands/
│   └── voice-buddy.md              # /voice-buddy slash command
├── voice_buddy/                    # Python core logic
│   ├── __init__.py
│   ├── __main__.py
│   ├── main.py
│   ├── context.py
│   ├── response.py
│   ├── tts.py
│   ├── player.py
│   ├── injector.py
│   ├── subagent_tts.py             # Agent's TTS entry point (called by agent via Bash)
│   ├── config.py
│   └── cli.py                      # Retained as dev fallback
├── assets/
│   └── audio/
│       ├── cute-girl/
│       ├── elegant-lady/
│       ├── warm-boy/
│       ├── secretary/
│       └── kawaii/
├── personas/
│   ├── cute-girl.json
│   ├── elegant-lady.json
│   ├── warm-boy.json
│   ├── secretary.json
│   └── kawaii.json
├── templates/
│   ├── cute-girl.json
│   ├── elegant-lady.json
│   ├── warm-boy.json
│   ├── secretary.json
│   └── kawaii.json
├── tests/
├── requirements.txt
└── README.md
```

---

## 9. Plugin Distribution

### 9.1 Plugin Manifest `.claude-plugin/plugin.json`

```json
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

### 9.2 Self-hosted Marketplace `.claude-plugin/marketplace.json`

```json
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

### 9.3 Hook Declarations `hooks/hooks.json`

```json
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

**Critical:** Stop hook MUST be `async: false` (synchronous) so Claude reads the exit code 2 and additionalContext. All other hooks are `async: true` to avoid blocking Claude.

### 9.4 Installation Paths

**Path A: Self-hosted marketplace (recommended, zero approval needed)**
```bash
/plugin marketplace add luyao618/Claude-Code-Voice-Buddy
/plugin install voice-buddy
```

**Path B: Official marketplace (if approved)**
One-click install from Claude Code Discover panel.

**Path C: Developer fallback**
```bash
git clone https://github.com/luyao618/Claude-Code-Voice-Buddy.git
cd Claude-Code-Voice-Buddy
voice-buddy setup
```

---

## 10. Testing Strategy

### 10.1 Updated Existing Tests

- **test_config.py** - Load user config, style definitions, fallback defaults
- **test_context.py** - Unchanged (event analysis logic unchanged)
- **test_response.py** - Per-style template loading, `{{nickname}}` substitution, audio file ID return
- **test_main.py** - Pre-packaged audio path, real-time TTS path, disabled silent exit
- **test_cli.py** - `config` command, `on/off` commands, interactive setup

### 10.2 New Tests

- **test_audio_cache.py** - Pre-packaged audio file lookup, missing file fallback to real-time TTS
- **test_persona.py** - Style definition loading, additionalContext generation with nickname/persona_override, `subagent_tts.py` invocation
- **test_plugin.py** - Plugin structure validation (plugin.json exists, hooks.json format correct)

### 10.3 E2E Testing

The existing `voice-buddy test <event>` command is extended with a `--style` parameter:

```bash
voice-buddy test sessionstart                      # Uses current config style
voice-buddy test sessionstart --style cute-girl     # Override style for testing
voice-buddy test notification --style secretary
voice-buddy test stop --style kawaii
```

The `--style` flag temporarily overrides the active style for that test run only, without modifying the user's config file.

---

## 11. User-Provided Content (External Task)

The following content will be provided by the user separately:

- **90 phrase templates**: 5 styles x 3 events x 6 phrases each
  - SessionStart phrases (no nickname): 30 total
  - SessionEnd phrases (no nickname): 30 total
  - Notification phrases (with `{{nickname}}`): 30 total

- **60 pre-packaged audio files**: generated from the SessionStart + SessionEnd phrases using edge-tts with each style's voice settings

---

## 12. Out of Scope for v1.0

- Multiple TTS engines (ElevenLabs, Piper) - architecture uses single provider, future extensible
- Audio caching for Notification phrases - always real-time TTS
- Web UI for configuration
- Per-project style settings (global config only)
