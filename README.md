# Claude Code Voice Buddy

> **CC** — Your personality-driven voice companion for Claude Code.

---

## 中文

**Voice Buddy** 让 Claude Code 不再沉默。CC 是一个有性格的语音伙伴，在关键时刻用你选择的风格陪伴你编程。

```
打开 Claude Code  → "欢迎回来，今天也要加油哦~"         (cute-girl)
需要你注意时      → "Boss, your attention is needed"    (secretary)
任务完成          → "Senpai、バグ直したよ~"              (kawaii)
关闭会话          → "辛苦了，好好休息一下"               (warm-boy)
```

### 5 种风格，3 种语言

| 风格 | 语言 | 描述 | TTS 语音 | 默认称呼 |
|------|------|------|----------|----------|
| **cute-girl** | 中文 | 可爱甜美 | zh-CN-XiaoyiNeural | Master |
| **elegant-lady** | 中文 | 优雅知性 | zh-CN-XiaoxiaoNeural | Master |
| **warm-boy** | 中文 | 温暖体贴 | zh-CN-YunxiNeural | Master |
| **secretary** | 英文 | 专业干练 | en-US-JennyNeural | Boss |
| **kawaii** | 日文 | 元气可爱 | ja-JP-NanamiNeural | Senpai |

### 工作原理

Voice Buddy 接入 [Claude Code 的 Hook 系统](https://docs.anthropic.com/en/docs/claude-code/hooks)，在关键事件触发时播放语音。

**三层音频架构：**

| 通道 | 延迟 | 适用场景 | 实现方式 |
|------|------|----------|----------|
| **Pre-packaged** | <100ms | 开始、结束 | 预生成 MP3 直接播放 |
| **实时 TTS** | ~1s | 通知提醒 | edge-tts 实时合成（含 nickname 替换） |
| **AI 总结** | ~3s | 任务完成 | Claude subagent 生成 + TTS |

### 快速开始

#### 环境要求

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- Python 3.9+
- 音频播放器（macOS: `afplay` 内置, Linux: `paplay`/`aplay`/`mpg123`）

#### 安装方式

**方式 A：Self-hosted Marketplace（推荐）**

在 Claude Code 中运行：
```
/plugin marketplace add luyao618/Claude-Code-Voice-Buddy
/plugin install voice-buddy
```

安装完成后 Hook 自动注册，无需手动配置。

**方式 B：Official Marketplace**

> 🚧 Coming Soon — 提交审核中，通过后可在 Claude Code Discover 面板一键安装。

**方式 C：开发者手动安装**

```bash
git clone https://github.com/luyao618/Claude-Code-Voice-Buddy.git
cd Claude-Code-Voice-Buddy
pip install -r requirements.txt

# 安装到当前项目
python3 -m voice_buddy.cli setup

# 全局安装（所有项目生效）
python3 -m voice_buddy.cli setup --global

# 安装到指定项目
python3 -m voice_buddy.cli setup --project /path/to/your/project
```

#### 试一试

```bash
python3 -m voice_buddy.cli test sessionstart     # 听到问候语
python3 -m voice_buddy.cli test sessionend        # 听到告别语
python3 -m voice_buddy.cli test notification      # 听到通知提醒
```

### 配置

```bash
# 切换风格
python3 -m voice_buddy.cli config --style kawaii

# 修改称呼
python3 -m voice_buddy.cli config --nickname Senpai

# 同时修改
python3 -m voice_buddy.cli config --style secretary --nickname Boss

# 禁用/启用特定事件
python3 -m voice_buddy.cli config --disable notification
python3 -m voice_buddy.cli config --enable notification

# 全局开关
python3 -m voice_buddy.cli on
python3 -m voice_buddy.cli off
```

配置文件位置：
- macOS: `~/Library/Application Support/voice-buddy/config.json`
- Linux: `~/.config/voice-buddy/config.json`
- Windows: `%APPDATA%\voice-buddy\config.json`

### 支持的事件

| 事件 | 触发时机 | 音频来源 |
|------|----------|----------|
| **SessionStart** | 打开 Claude Code | Pre-packaged MP3 |
| **SessionEnd** | 关闭会话 | Pre-packaged MP3 |
| **Notification** | Claude 发送通知 | 实时 TTS（含称呼） |
| **Stop** | Claude 完成任务 | AI 生成个性化总结 |

### CLI 命令

| 命令 | 说明 |
|------|------|
| `setup` | 安装 Hook |
| `setup --global` | 全局安装 |
| `uninstall` | 卸载 Hook |
| `test <event>` | 测试事件（sessionstart/sessionend/notification/stop） |
| `config --style <id>` | 切换风格 |
| `config --nickname <name>` | 修改称呼 |
| `config --disable <event>` | 禁用事件 |
| `config --enable <event>` | 启用事件 |
| `on` / `off` | 全局开关 |

---

## English

**Voice Buddy** turns Claude Code into a more human experience. **CC** is a personality-driven voice companion that speaks at key moments in your coding workflow.

```
Open Claude Code       → "欢迎回来，今天也要加油哦~"         (cute-girl)
Needs your attention   → "Boss, your attention is needed"    (secretary)
Task completed         → "Senpai、バグ直したよ~"              (kawaii)
Close session          → "辛苦了，好好休息一下"               (warm-boy)
```

### 5 Styles, 3 Languages

| Style | Language | Description | TTS Voice | Default Nickname |
|-------|----------|-------------|-----------|-----------------|
| **cute-girl** | Chinese | Cute, sweet | zh-CN-XiaoyiNeural | Master |
| **elegant-lady** | Chinese | Graceful, intellectual | zh-CN-XiaoxiaoNeural | Master |
| **warm-boy** | Chinese | Warm, caring | zh-CN-YunxiNeural | Master |
| **secretary** | English | Professional, efficient | en-US-JennyNeural | Boss |
| **kawaii** | Japanese | Cute, energetic | ja-JP-NanamiNeural | Senpai |

### How It Works

Voice Buddy hooks into [Claude Code's hook system](https://docs.anthropic.com/en/docs/claude-code/hooks), playing audio at key events.

**Three-tier audio architecture:**

| Tier | Latency | Used For | How |
|------|---------|----------|-----|
| **Pre-packaged** | <100ms | Session start/end | Pre-generated MP3 playback |
| **Real-time TTS** | ~1s | Notifications | edge-tts synthesis with nickname substitution |
| **AI Summary** | ~3s | Task completion | Claude subagent generates summary + TTS |

### Quick Start

#### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- Python 3.9+
- Audio player (macOS: `afplay` built-in, Linux: `paplay`/`aplay`/`mpg123`)

#### Installation

**Path A: Self-hosted Marketplace (Recommended)**

Run inside Claude Code:
```
/plugin marketplace add luyao618/Claude-Code-Voice-Buddy
/plugin install voice-buddy
```

Hooks are auto-registered on install — no manual setup needed.

**Path B: Official Marketplace**

> 🚧 Coming Soon — pending approval. Once approved, one-click install from the Claude Code Discover panel.

**Path C: Developer Manual Install**

```bash
git clone https://github.com/luyao618/Claude-Code-Voice-Buddy.git
cd Claude-Code-Voice-Buddy
pip install -r requirements.txt

# Install to current project
python3 -m voice_buddy.cli setup

# Install globally (all projects)
python3 -m voice_buddy.cli setup --global

# Install to a specific project
python3 -m voice_buddy.cli setup --project /path/to/your/project
```

#### Try It Out

```bash
python3 -m voice_buddy.cli test sessionstart     # Hear a greeting
python3 -m voice_buddy.cli test sessionend        # Hear a goodbye
python3 -m voice_buddy.cli test notification      # Hear a notification alert
```

### Configuration

```bash
# Switch style
python3 -m voice_buddy.cli config --style kawaii

# Change nickname
python3 -m voice_buddy.cli config --nickname Senpai

# Set both at once
python3 -m voice_buddy.cli config --style secretary --nickname Boss

# Disable/enable specific events
python3 -m voice_buddy.cli config --disable notification
python3 -m voice_buddy.cli config --enable notification

# Global on/off
python3 -m voice_buddy.cli on
python3 -m voice_buddy.cli off
```

Config file location:
- macOS: `~/Library/Application Support/voice-buddy/config.json`
- Linux: `~/.config/voice-buddy/config.json`
- Windows: `%APPDATA%\voice-buddy\config.json`

### Supported Events

| Event | When | Audio Source |
|-------|------|-------------|
| **SessionStart** | Open Claude Code | Pre-packaged MP3 |
| **SessionEnd** | Close session | Pre-packaged MP3 |
| **Notification** | Claude sends a notification | Real-time TTS (with nickname) |
| **Stop** | Claude finishes a task | AI-generated summary |

### CLI Reference

| Command | Description |
|---------|-------------|
| `setup` | Install hooks |
| `setup --global` | Install hooks globally |
| `uninstall` | Remove hooks |
| `test <event>` | Test an event (sessionstart/sessionend/notification/stop) |
| `config --style <id>` | Switch style |
| `config --nickname <name>` | Change nickname |
| `config --disable <event>` | Disable an event |
| `config --enable <event>` | Enable an event |
| `on` / `off` | Global toggle |

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Claude Code                          │
│                                                          │
│  Hook Event ──► voice_buddy (stdin JSON)                 │
│                      │                                   │
│            ┌─────────┼─────────┐                         │
│            │         │         │                         │
│     SessionStart  Notification  Stop                     │
│     SessionEnd       │         │                         │
│            │         │    injector.py                     │
│     Pre-packaged  Real-time   (exit code 2)              │
│       MP3 file    TTS via      │                         │
│            │     edge-tts   voice-buddy-*                │
│            │         │      subagent                     │
│         player.py  player.py  (haiku)                    │
│            │         │         │                         │
│         🔊 <100ms  🔊 ~1s   subagent_tts.py             │
│                               │                         │
│                            🔊 ~3s                        │
└──────────────────────────────────────────────────────────┘
```

#### Project Structure

```
Claude-Code-Voice-Buddy/
├── .claude-plugin/          # Plugin manifest
│   ├── plugin.json
│   └── marketplace.json
├── hooks/hooks.json         # Hook declarations
├── agents/                  # 5 style-specific agent personas
│   ├── voice-buddy-cute-girl.md
│   ├── voice-buddy-elegant-lady.md
│   ├── voice-buddy-warm-boy.md
│   ├── voice-buddy-secretary.md
│   └── voice-buddy-kawaii.md
├── commands/voice-buddy.md  # /voice-buddy slash command
├── personas/                # Style definitions (TTS voice, rate, pitch)
├── templates/               # Per-style phrase templates
├── assets/audio/            # 60 pre-packaged MP3 files
├── voice_buddy/             # Python core
│   ├── main.py              # Hook entry point
│   ├── config.py            # Cross-platform user config
│   ├── styles.py            # Style definition loader
│   ├── context.py           # Event analysis
│   ├── response.py          # Template selection + audio ID
│   ├── tts.py               # edge-tts synthesis
│   ├── player.py            # Cross-platform audio playback
│   ├── injector.py          # Stop hook handler
│   ├── subagent_tts.py      # Agent TTS entry point
│   ├── generate_audio.py    # Dev utility: generate MP3 assets
│   └── cli.py               # CLI commands
└── tests/                   # 79 tests
```

### Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
python3 -m pytest tests/ -v

# Regenerate pre-packaged audio (after editing templates)
python3 -m voice_buddy.generate_audio
```

79 tests covering: config system, style loading, response selection, audio asset lookup, main pipeline, CLI commands, injector, and plugin structure validation.

## License

MIT
