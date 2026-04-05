# Claude Code Voice Buddy

> Your AI coding companion that **speaks** to you.

**Voice Buddy** turns Claude Code into a more human experience. Instead of staring at a silent terminal, you'll hear **XiaoXing** (小星) - a cheerful voice companion that reacts to what's happening in your coding session with encouraging words.

```
You commit code    → "要提交代码咯，加油！"
Tests all pass     → "测试全过了！太棒了！"
Something breaks   → "出了点小问题...别担心哦~"
Task completed     → "哦尼酱，bug修好啦~"
```

## How It Works

Voice Buddy hooks into [Claude Code's hook system](https://docs.anthropic.com/en/docs/claude-code/hooks). When Claude Code triggers events (starting a session, running a command, finishing a task), Voice Buddy analyzes the context, picks an appropriate response, and speaks it aloud via text-to-speech.

**Two-tier architecture:**

| Path | Latency | Used for | How |
|------|---------|----------|-----|
| **Fast** | ~1s | Greetings, tool use, errors | Template matching + edge-tts |
| **Smart** | ~3s | Task completion summaries | Claude subagent generates context-aware response + TTS |

## Quick Start

### Prerequisites

- Python 3.8+
- An audio player (macOS: `afplay` built-in, Linux: `paplay`/`aplay`/`mpg123`, Windows: `winsound`)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed

### Install

```bash
git clone https://github.com/luyao618/Claude-Code-Voice-Buddy.git
cd Claude-Code-Voice-Buddy
pip install -r requirements.txt
```

### Set up hooks

```bash
# Install to a specific project
python -m voice_buddy.cli setup --project /path/to/your/project

# Or install globally (all projects)
python -m voice_buddy.cli setup --global

# Or install to current directory
python -m voice_buddy.cli setup
```

### Try it out

```bash
python -m voice_buddy.cli test sessionstart    # Hear a greeting
python -m voice_buddy.cli test posttooluse     # Hear test-pass celebration
python -m voice_buddy.cli test pretooluse      # Hear git commit encouragement
```

Then start Claude Code in the project where you installed hooks - XiaoXing will greet you!

## CLI Reference

| Command | Description |
|---------|-------------|
| `python -m voice_buddy.cli setup` | Install hooks to current project |
| `python -m voice_buddy.cli setup --project /path` | Install hooks to a specific project |
| `python -m voice_buddy.cli setup --global` | Install hooks globally (~/.claude/) |
| `python -m voice_buddy.cli uninstall` | Remove hooks from current project |
| `python -m voice_buddy.cli uninstall --global` | Remove hooks globally |
| `python -m voice_buddy.cli test <event>` | Test a specific hook event |

Available test events: `sessionstart`, `sessionend`, `pretooluse`, `posttooluse`, `posttoolusefailure`, `stop`

## Supported Events

| Event | When | XiaoXing says... |
|-------|------|------------------|
| **SessionStart** | You open Claude Code | "欢迎回来，哦尼酱！今天也要加油哦~" |
| **SessionEnd** | You close the session | "辛苦啦！下次见哦~" |
| **PreToolUse** | Before git/test/docker commands | "要提交代码咯，加油！" |
| **PostToolUse** | Tests pass or git succeeds | "测试全过了！太棒了！" |
| **PostToolUseFailure** | A command fails or times out | "出了点小问题...别担心哦~" |
| **Stop** | Claude finishes a task | AI-generated summary like "哦尼酱，bug修好啦~" |

### Smart event detection

Voice Buddy doesn't speak on every tool use - it analyzes context to stay relevant:

- **PreToolUse**: Only triggers for recognized Bash commands (git, pytest, npm, docker)
- **PostToolUse**: Only triggers when test results or git outcomes are detected
- **PostToolUseFailure**: Only triggers for Bash tool failures
- **Stop**: Only triggers when a substantive task was completed (detects completion keywords in both English and Chinese)

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Claude Code                        │
│                                                      │
│  Hook Event ──► voice_buddy (stdin JSON)             │
│                      │                               │
│              ┌───────┴───────┐                       │
│              │               │                       │
│         Fast Path       Stop Event                   │
│              │               │                       │
│      context.py ──►    injector.py                   │
│      response.py       (exit code 2)                 │
│         tts.py              │                        │
│       player.py        voice-buddy                   │
│              │          subagent                      │
│              │         (haiku model)                  │
│           🔊 ~1s           │                         │
│                         tts.py                       │
│                       player.py                      │
│                           │                          │
│                        🔊 ~3s                        │
└──────────────────────────────────────────────────────┘
```

### Modules

| Module | Purpose |
|--------|---------|
| `main.py` | Hook entry point: reads stdin JSON, dispatches by event |
| `context.py` | Semantic analyzer: extracts event type, sub-event, mood from hook data |
| `response.py` | Template selector: picks a response from `templates.json` |
| `tts.py` | Text-to-speech via [edge-tts](https://github.com/rany2/edge-tts) (Microsoft Edge TTS, free) |
| `player.py` | Cross-platform async audio playback (macOS/Linux/Windows) |
| `injector.py` | Stop event handler: blocks Claude via exit code 2, triggers subagent |
| `config.py` | Configuration loader (`buddy-config.json`) |
| `cli.py` | CLI: setup, uninstall, test commands |

## Configuration

Edit `buddy-config.json` in the repo root:

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

### Available voices

| Voice | Language | Style |
|-------|----------|-------|
| `zh-CN-XiaoyiNeural` | Chinese | Cute, youthful (default) |
| `zh-CN-XiaoxiaoNeural` | Chinese | Warm, friendly |
| `ja-JP-NanamiNeural` | Japanese | Anime-style |
| `en-US-AriaNeural` | English | Professional |

See the full list: `edge-tts --list-voices`

### Response templates

Edit `templates.json` to customize what XiaoXing says:

```json
{
  "sessionstart": {
    "default": ["Your custom greeting here"]
  },
  "posttooluse": {
    "test_passed": ["Your custom celebration here"]
  }
}
```

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_context.py -v
```

### Test coverage

58 tests covering all core modules: context analysis, response selection, TTS synthesis, audio playback, CLI commands, configuration loading, and the Stop event injector.

### Debugging

Voice Buddy writes debug logs to `~/voice-buddy-debug.log`:

```bash
tail -f ~/voice-buddy-debug.log
```

## Roadmap

- [ ] More TTS engines (ElevenLabs, Piper for offline)
- [ ] Multiple personalities (anime Japanese, professional English, sarcastic English)
- [ ] Audio caching (pre-warm templates, LRU disk cache)
- [ ] `buddy use <personality>` command to switch characters
- [ ] `buddy preview <personality>` to audition voices

## License

MIT
