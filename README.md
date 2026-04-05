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
