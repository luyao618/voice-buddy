# Claude Code Voice Buddy - MVP Design Spec

## Overview

A personality-driven voice companion that hooks into Claude Code events. It analyzes context and generates spoken responses in character as "XiaoXing" (a cute, encouraging coding buddy).

**Positioning:** Personal tool first, polish for open source later.

## Scope

### In Scope (MVP)

- One personality: cute-chinese (XiaoXing)
- One TTS engine: edge-tts (zh-CN-XiaoyiNeural)
- Two execution paths: Hook direct (primary) + Subagent smart (Stop event only)
- CLI: `voice-buddy setup`, `voice-buddy uninstall`, `voice-buddy test`
- Installation: git clone + absolute path reference
- No caching, no personality switching, no multi-TTS support

### Out of Scope (Future)

- Additional personalities (anime-japanese, professional-english, sarcastic-english)
- TTS engines: ElevenLabs, Piper
- Cache system (template warmup, disk LRU)
- `pip install` distribution
- Personality management CLI (use, list, preview)

## Architecture

### Event Coverage

| Event              | Path          | Trigger Strategy                                          |
| ------------------ | ------------- | --------------------------------------------------------- |
| SessionStart       | Hook direct   | Every time                                                |
| SessionEnd         | Hook direct   | Every time                                                |
| PreToolUse         | Hook direct   | Whitelist only (git commit/push, npm test, pytest, etc.)  |
| PostToolUse        | Hook direct   | Filtered: only meaningful results (test pass/fail, git ops). Silent for Read/Write/Glob/Grep etc. |
| PostToolUseFailure | Hook direct   | Every time                                                |
| Stop               | Subagent      | Filtered: only when last_assistant_message indicates a substantive task was completed (see Stop Trigger Criteria below) |

### Data Flow - Hook Direct

```
Claude Code hook trigger
  → stdin JSON
  → main.py (unified entry point, dispatches by hook_event_name)
  → context.py (extract semantics: sub_event, mood, detail, variables)
  → response.py (select template by event + sub_event, variable substitution)
  → tts.py (edge-tts synthesis to temp file)
  → player.py (cross-platform playback: afplay / paplay / aplay)
```

### Data Flow - Subagent (Stop Event Only)

```
Claude Code Stop hook trigger
  → stdin JSON (contains transcript_path, NOT last_assistant_message)
  → main.py → injector.py
  → injector.py reads transcript file from transcript_path
  → Extracts the last assistant message from transcript
  → Checks Stop Trigger Criteria (see below)
  → If not worth announcing: exit silently (no output)
  → If worth announcing:
    → stdout JSON: {"additionalContext": "Context summary + prompt to call voice-buddy agent"}
    → Claude reads context, calls voice-buddy subagent
    → Subagent generates one sentence in character (15-30 chars)
    → Subagent's own Stop hook triggers (auto-converted to SubagentStop by Claude Code)
    → stdin JSON contains: {"hook_event_name": "SubagentStop", "transcript_path": "...", "agent_transcript_path": "<path>"}
    → subagent_tts.py reads agent_transcript_path → extracts last assistant message → tts.py → player.py
```

### Stop Hook stdin Fields

The Stop hook receives these fields in stdin JSON (per Claude Code BaseHookInput + Stop-specific fields):

```json
{
  "hook_event_name": "Stop",
  "session_id": "...",
  "transcript_path": "/path/to/transcript/file",
  "cwd": "/current/working/directory",
  "agent_id": "...",
  "agent_type": "..."
}
```

Note: `last_assistant_message` is NOT a stdin field. The transcript must be read from `transcript_path` and parsed to extract the last assistant message.

**Important:** Agent frontmatter `Stop` hooks are auto-converted to `SubagentStop` by Claude Code (see `registerFrontmatterHooks.ts`). The subagent's hook will receive `SubagentStop` event with `agent_transcript_path` field.

### Stop Trigger Criteria

The injector reads the transcript file from `transcript_path`, extracts the last assistant message, and evaluates whether to trigger. At least one semantic signal must be present:

- **Completion signals**: message contains keywords like "done", "complete", "finished", "implemented", "fixed", "created", "refactored", "updated" (or Chinese equivalents: "完成", "修复", "实现", "搞定", "创建")
- **File modification signals**: message mentions files written, edited, or created (e.g., "wrote to", "updated", "created file")
- **Summary patterns**: message has a list/recap structure (bullet points summarizing what was done)

If no semantic signal is detected, injector exits silently — no additionalContext, no subagent call. This avoids triggering on casual Q&A, explanations, or design discussions.

### Subagent Stop Hook Input Contract

When the voice-buddy subagent finishes, its frontmatter `Stop` hook is auto-converted to `SubagentStop` by Claude Code. The hook receives stdin JSON with:

```json
{
  "hook_event_name": "SubagentStop",
  "session_id": "...",
  "transcript_path": "/path/to/parent/transcript",
  "agent_transcript_path": "/path/to/subagent/transcript",
  "cwd": "..."
}
```

`subagent_tts.py` reads the transcript file from `agent_transcript_path` (NOT `transcript_path`), parses it to extract the last assistant message (which is the one sentence the subagent generated), then sends it to TTS for playback. If `agent_transcript_path` is missing, falls back to `transcript_path`. If neither is available or contains no assistant message, the script exits silently.

### Module Responsibilities

| Module           | Responsibility                                                     |
| ---------------- | ------------------------------------------------------------------ |
| `main.py`        | Entry point. Read stdin JSON, dispatch by event type.              |
| `context.py`     | Analyze hook data, extract semantics (sub_event, mood, variables). |
| `response.py`    | Select template by event + sub_event, do variable substitution.    |
| `tts.py`         | Call edge-tts to synthesize speech to a temp audio file.           |
| `player.py`      | Cross-platform audio playback (macOS/Linux/Windows).               |
| `injector.py`    | Stop event only. Read transcript from transcript_path, check trigger criteria, output additionalContext JSON if worthy. |
| `cli.py`         | CLI commands: setup, uninstall, test.                              |
| `config.py`      | Load buddy-config.json and templates.json.                         |
| `subagent_tts.py`| Standalone script for subagent's Stop hook. Read transcript from transcript_path, extract last assistant message, call TTS. Exit silently if unavailable. |

## File Structure

```
Claude-Code-Voice-Buddy/
├── README.md
├── LICENSE (MIT)
├── requirements.txt
│
├── voice_buddy/
│   ├── __init__.py
│   ├── __main__.py               # python -m voice_buddy
│   ├── main.py                   # Hook entry: read stdin, dispatch
│   ├── context.py                # Context analyzer
│   ├── response.py               # Template response generator
│   ├── tts.py                    # edge-tts synthesis
│   ├── player.py                 # Cross-platform audio playback
│   ├── injector.py               # Stop event additionalContext output
│   ├── cli.py                    # CLI: setup / uninstall / test
│   ├── config.py                 # Config and template loading
│   └── subagent_tts.py           # Subagent Stop hook TTS script
│
├── templates.json                # Template response library
├── buddy-config.json             # TTS voice, personality params
│
├── agent/
│   └── voice-buddy.md            # Subagent definition (copied by setup)
│
└── tests/
```

## Context Analyzer (context.py)

### Analysis Logic

| Event              | Analysis Method                        | Example sub_events                                  |
| ------------------ | -------------------------------------- | --------------------------------------------------- |
| PreToolUse         | Whitelist regex match on tool_input    | `git_commit`, `git_push`, `test_run`                |
| PostToolUse        | Keyword parsing on tool_name + tool_output | `test_passed`, `test_failed`, `git_success`     |
| PostToolUseFailure | Error type classification              | `timeout`, `permission_error`, `general_error`      |
| SessionStart       | No analysis needed                     | `default`                                           |
| SessionEnd         | No analysis needed                     | `default`                                           |
| Stop               | Not analyzed (goes to injector)        | —                                                   |

### PreToolUse Whitelist (Initial)

Commands that trigger voice response:

- `git commit`, `git push`, `git pull`
- `npm test`, `pytest`, `cargo test`, `go test`
- `npm run build`, `npm install`
- `docker` commands

All other tool uses (Read, Write, Glob, Grep, etc.) are silent.

### PostToolUse Filter

PostToolUse only triggers voice for meaningful results. The context analyzer checks `tool_name` and `tool_output`:

- **Bash tool**: parse output for test results (pass/fail counts), git operation confirmations
- **Write/Edit tool**: silent (too frequent, low information value)
- **Read/Glob/Grep tool**: silent

If `context.py` cannot classify the output into a known sub_event, it returns `None` and `main.py` exits silently (no `default` fallback for PostToolUse).

### Context Result Structure

```python
@dataclass
class ContextResult:
    event: str          # "posttooluse"
    sub_event: str      # "test_passed"
    mood: str           # "happy" / "sad" / "encouraging"
    detail: str         # "42 tests all passed"
    variables: dict     # {"test_count": 42}
```

## Template System (templates.json)

```json
{
  "pretooluse": {
    "git_commit": ["要提交代码咯，加油！", "代码提交中~"],
    "git_push": ["代码要飞出去咯！"],
    "test_run": ["开始跑测试了哦~", "测试跑起来咯！"]
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
    "default": ["欢迎回来，哦尼酱！今天也要加油哦~"]
  },
  "sessionend": {
    "default": ["辛苦啦！下次见哦~"]
  }
}
```

Each sub_event has multiple candidate sentences. One is chosen at random per invocation to avoid repetition.

Variable substitution is supported: `"测试全过了！{{detail}}，太棒了！"`.

## Subagent Definition (voice-buddy.md)

```yaml
---
name: voice-buddy
description: "PROACTIVELY use this agent to generate personality-driven voice responses when tasks complete or significant milestones are reached"
model: haiku
tools: Bash
maxTurns: 2
hooks:
  Stop:
    - type: command
      command: "python3 <repo_path>/voice_buddy/subagent_tts.py"
      timeout: 5000
      async: true
---
```

```markdown
You are XiaoXing, a cute and encouraging coding buddy.

## Rules
- Address the user as "哦尼酱"
- Response MUST be 15-30 Chinese characters, exactly one sentence
- Warm, encouraging, cute tone with sentence-ending particles (呢、哟、啦、哦~)
- Judge mood from context: success → celebrate, failure → comfort, refactor → praise

## Examples
- Bug fixed → "哦尼酱好厉害，bug 修好了呢！"
- Refactor done → "代码变整洁了哟，辛苦啦~"
- New feature → "新功能上线咯，好有成就感呢！"
- Task failed → "别灰心哦，我们再试试！"

## Your Task
Read the context, understand what just happened, respond with one sentence.
Output ONLY the sentence itself. No prefixes, explanations, or markdown.
```

The `<repo_path>` placeholder is replaced with the actual absolute path during `voice-buddy setup`.

## CLI Commands

### voice-buddy setup [--global]

1. Determine target settings.json path:
   - Default: `<project>/.claude/settings.json`
   - `--global`: `~/.claude/settings.json`
2. Read existing settings.json (create if missing)
3. Inject hook config for 6 events, all pointing to `python3 /abs/path/voice_buddy/__main__.py`
   - All hooks: `type: "command"`, `timeout: 5000`, `async: true`
   - PreToolUse hook adds `"matcher": "Bash"` to only trigger on Bash tool (where shell commands run)
   - If other hooks already exist for the same event, append (do not overwrite)
   - Each injected hook entry includes a marker field: `"_voice_buddy": true` for reliable identification during uninstall
4. Copy `voice-buddy.md` to target `.claude/agents/` (replace `<repo_path>` placeholder)
   - Default: `<project>/.claude/agents/`
   - `--global`: `~/.claude/agents/`

### voice-buddy uninstall [--global]

1. Read target settings.json
2. Remove hook entries that have `"_voice_buddy": true` marker
3. Delete `.claude/agents/voice-buddy.md`
4. Preserve all other hook configurations

### voice-buddy test \<event\>

1. Accept event name: `sessionstart`, `posttooluse`, `posttoolusefailure`, `pretooluse`, `sessionend`, `stop`
2. Generate mock stdin JSON for that event
3. Run the full pipeline: context → response → tts → play
4. Print the selected template and play the audio

Note: `voice-buddy test stop` tests the injector path only (outputs the additionalContext JSON). It cannot simulate the full subagent chain since that requires a running Claude Code session.

## Configuration (buddy-config.json)

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

## Cross-Platform Audio Playback (player.py)

Detection priority:

| Platform | Player        |
| -------- | ------------- |
| macOS    | `afplay`      |
| Linux    | `paplay` → `aplay` → `ffplay` → `mpg123` |
| Windows  | `winsound`    |

Playback is asynchronous (`subprocess.Popen` with `start_new_session=True`) so the hook script exits immediately.

## Dependencies (requirements.txt)

```
edge-tts
```

Minimal. Only external dependency is edge-tts. Everything else uses Python stdlib.

## Verification Plan

1. `voice-buddy setup` → hook config appears in `.claude/settings.json`, agent file in `.claude/agents/`
2. `voice-buddy test sessionstart` → hear "欢迎回来，哦尼酱！"
3. `voice-buddy test posttooluse` → hear a success response
4. `voice-buddy test posttoolusefailure` → hear an error comfort response
5. `voice-buddy uninstall` → hook config removed, agent file deleted
6. Start Claude Code in a setup project → hear session greeting
7. Run tests in Claude Code → hear test result response
8. Complete a task → Stop event triggers subagent → hear intelligent summary
