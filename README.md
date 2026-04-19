# Voice Buddy

> **CC** — Your personality-driven voice companion for Claude Code.

---

**Voice Buddy** turns Claude Code into a more human experience. **CC** is a personality-driven voice companion that speaks at key moments in your coding workflow.

```
Open Claude Code       → "欢迎回来，今天也要加油哦~"         (cute-girl)
Needs your attention   → "Boss, your attention is needed"    (secretary)
Task completed         → "Senpai、バグ直したよ~"              (kawaii)
Close session          → "辛苦了，好好休息一下"               (warm-boy)
```

### 7 Styles, 3 Languages

| Style | Language | Description | TTS Voice | Default Nickname |
|-------|----------|-------------|-----------|-----------------|
| **cute-girl** | Chinese | Cute, sweet | zh-CN-XiaoyiNeural | Master |
| **elegant-lady** | Chinese | Graceful, intellectual | zh-CN-XiaoxiaoNeural | Master |
| **warm-boy** | Chinese | Warm, caring | zh-CN-YunxiNeural | Master |
| **secretary** | English | Professional, efficient | en-US-JennyNeural | Boss |
| **steward** | English | British butler, composed | en-GB-RyanNeural | Sir |
| **cyber-girl** | English | Cyberpunk femme, cold | en-GB-SoniaNeural | Commander |
| **kawaii** | Japanese | Cute, energetic | ja-JP-NanamiNeural | Senpai |

### How It Works

Voice Buddy hooks into [Claude Code's hook system](https://docs.anthropic.com/en/docs/claude-code/hooks), playing audio at key events.

**Three-tier audio architecture:**

| Tier | Latency | Used For | How |
|------|---------|----------|-----|
| **Pre-packaged** | <100ms | Session start/end | Pre-generated MP3 playback |
| **Real-time TTS** | ~1s | Notifications | edge-tts synthesis with nickname substitution |
| **AI Summary** | ~3s | Task completion | Claude subagent generates summary + TTS |

### Installation

#### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- Python 3.9+
- Audio player (macOS: `afplay` built-in, Linux: `paplay`/`aplay`/`mpg123`)

#### Install from Plugin Marketplace

Run these two commands in Claude Code, one after the other:
```bash
/plugin marketplace add luyao618/voice-buddy   # 1. Add plugin source
/plugin install voice-buddy                                 # 2. Install plugin
```

During installation you'll be prompted to choose a **style** and **nickname**. Press Enter to use defaults (cute-girl / Master).

Hooks are auto-registered on install — no manual setup needed.

#### Recommended: Add Permission Allowlist

Add the following rules to the `allow` list in `.claude/settings.json` to skip permission prompts for voice playback:

```json
"Bash(PYTHONPATH=* python3 -m voice_buddy*)",
"Bash(PYTHONPATH=* python3 -m voice_buddy.*)"
```

### Configuration

After installation, type `/voice-buddy` in Claude Code to open the configuration panel.

You can also tell Claude what you want in natural language:
- "Switch Voice Buddy to kawaii style"
- "Change my nickname to Senpai"
- "Disable notification voice"

**Or use CLI commands** (the `voice-buddy` command is automatically available after plugin install):

```bash
# Switch style
voice-buddy config --style kawaii

# Change nickname
voice-buddy config --nickname Senpai

# Set both at once
voice-buddy config --style secretary --nickname Boss

# Disable/enable specific events
voice-buddy config --disable notification
voice-buddy config --enable notification

# Global on/off
voice-buddy on
voice-buddy off

# Test
voice-buddy test sessionstart
voice-buddy test notification
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

### 🔇 Global Hotkey to Stop Current Playback (macOS)

Press **F2** at any time to immediately silence whatever Voice Buddy is currently playing — useful when a colleague walks over, you take a phone call, or a meeting starts unexpectedly.

**Required system settings:**

1. **System Settings → Keyboard → "Use F1, F2, etc. as standard function keys"** must be **enabled**, otherwise F2 sends "brightness up" instead of a key event the listener can see. (You can also use `fn+F2` if you prefer to leave the default behavior.)
2. **System Settings → Privacy & Security → Accessibility** must list and check the Python interpreter that runs voice-buddy. Run `voice-buddy hotkey-doctor` to see the exact path that needs to be granted.

**CLI surface:**

```bash
# Stop without using the hotkey (e.g. from another terminal)
voice-buddy stop

# Change the bound key
voice-buddy config --hotkey F3

# Disable / re-enable the hotkey listener
voice-buddy config --disable-hotkey
voice-buddy config --enable-hotkey

# Diagnose Accessibility, fn-key mode, listener liveness, etc.
voice-buddy hotkey-doctor
voice-buddy hotkey-doctor --non-interactive   # CI-friendly
voice-buddy hotkey-doctor --json              # machine-readable
```

**Behavior notes:**

- F2 only stops the **currently playing** audio — it does not cancel queued TTS that hasn't started yet.
- macOS only. The dependency `pyobjc-framework-Quartz` is installed automatically on Darwin.
- The listener subprocess starts when you open Claude Code and self-exits ~30 s after the last session closes.
- If you recreate your virtualenv or upgrade Python, Accessibility may silently revoke (it is bound to the executable path). `voice-buddy hotkey-doctor` will warn you when this happens — re-grant the new path.
- See `docs/manual-tests.md` for the full QA checklist.

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
voice-buddy/
├── .claude-plugin/          # Plugin manifest
│   ├── plugin.json
│   └── marketplace.json
├── hooks/hooks.json         # Hook declarations (auto-registered)
├── bin/voice-buddy          # CLI wrapper (auto-added to PATH)
├── agents/                  # 7 style-specific agent personas
│   ├── voice-buddy-cute-girl.md
│   ├── voice-buddy-elegant-lady.md
│   ├── voice-buddy-warm-boy.md
│   ├── voice-buddy-secretary.md
│   ├── voice-buddy-steward.md
│   ├── voice-buddy-cyber-girl.md
│   └── voice-buddy-kawaii.md
├── commands/voice-buddy.md  # /voice-buddy slash command
├── personas/                # Style definitions (TTS voice, rate, pitch)
├── templates/               # Per-style phrase templates
├── assets/audio/            # 84 pre-packaged MP3 files
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
└── tests/                   # 86 tests
```

### Development

```bash
git clone https://github.com/luyao618/voice-buddy.git
cd voice-buddy
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
python3 -m pytest tests/ -v

# Regenerate pre-packaged audio (after editing templates)
python3 -m voice_buddy.generate_audio
```

---

## 中文

**Voice Buddy** 让 Claude Code 不再沉默。CC 是一个有性格的语音伙伴，在关键时刻用你选择的风格陪伴你编程。

```
打开 Claude Code  → "欢迎回来，今天也要加油哦~"         (cute-girl)
需要你注意时      → "Boss, your attention is needed"    (secretary)
任务完成          → "Senpai、バグ直したよ~"              (kawaii)
关闭会话          → "辛苦了，好好休息一下"               (warm-boy)
```

### 7 种风格，3 种语言

| 风格 | 语言 | 描述 | TTS 语音 | 默认称呼 |
|------|------|------|----------|----------|
| **cute-girl** | 中文 | 可爱甜美 | zh-CN-XiaoyiNeural | Master |
| **elegant-lady** | 中文 | 优雅知性 | zh-CN-XiaoxiaoNeural | Master |
| **warm-boy** | 中文 | 温暖体贴 | zh-CN-YunxiNeural | Master |
| **secretary** | 英文 | 专业干练 | en-US-JennyNeural | Boss |
| **steward** | 英文 | 英式管家 | en-GB-RyanNeural | Sir |
| **cyber-girl** | 英文 | 赛博机器姬 | en-GB-SoniaNeural | Commander |
| **kawaii** | 日文 | 元气可爱 | ja-JP-NanamiNeural | Senpai |

### 工作原理

Voice Buddy 接入 [Claude Code 的 Hook 系统](https://docs.anthropic.com/en/docs/claude-code/hooks)，在关键事件触发时播放语音。

**三层音频架构：**

| 通道 | 延迟 | 适用场景 | 实现方式 |
|------|------|----------|----------|
| **Pre-packaged** | <100ms | 开始、结束 | 预生成 MP3 直接播放 |
| **实时 TTS** | ~1s | 通知提醒 | edge-tts 实时合成（含 nickname 替换） |
| **AI 总结** | ~3s | 任务完成 | Claude subagent 生成 + TTS |

### 安装

#### 环境要求

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- Python 3.9+
- 音频播放器（macOS: `afplay` 内置, Linux: `paplay`/`aplay`/`mpg123`）

#### 从 Plugin Marketplace 安装

在 Claude Code 中依次运行以下两条命令：
```bash
/plugin marketplace add luyao618/voice-buddy   # 1. 添加插件源
/plugin install voice-buddy                                 # 2. 安装插件
```

安装时会提示选择**风格**和**称呼**，也可以直接回车使用默认值（cute-girl / Master）。

安装完成后 Hook 自动注册，无需手动配置。

#### 推荐：添加权限白名单

在 `.claude/settings.json` 的 `allow` 列表中加入以下规则，可以跳过每次语音播放的权限确认，体验更流畅：

```json
"Bash(PYTHONPATH=* python3 -m voice_buddy*)",
"Bash(PYTHONPATH=* python3 -m voice_buddy.*)"
```

### 配置

安装后，在 Claude Code 对话中输入 `/voice-buddy` 即可进入配置面板。

也可以直接告诉 Claude 你想要的设置，例如：
- "帮我把 Voice Buddy 切到 kawaii 风格"
- "把称呼改成 Senpai"
- "关掉 notification 的语音"

**或者使用 CLI 命令**（插件安装后 `voice-buddy` 命令自动可用）：

```bash
# 切换风格
voice-buddy config --style kawaii

# 修改称呼
voice-buddy config --nickname Senpai

# 同时修改
voice-buddy config --style secretary --nickname Boss

# 禁用/启用特定事件
voice-buddy config --disable notification
voice-buddy config --enable notification

# 全局开关
voice-buddy on
voice-buddy off

# 试听
voice-buddy test sessionstart
voice-buddy test notification
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

### 🔇 全局快捷键停止当前播放（macOS）

随时按 **F2** 可以立即让 Voice Buddy 安静下来——同事突然过来讲话、接电话、临时会议都不会被打扰。

**必备系统设置：**

1. **系统设置 → 键盘 → 「将 F1、F2 等键用作标准功能键」必须勾选**，否则 F2 会被识别成「亮度增加」，监听器收不到按键事件。（如果你想保留默认行为，也可以用 `fn+F2`。）
2. **系统设置 → 隐私与安全性 → 辅助功能** 中需要勾选运行 voice-buddy 的 Python 解释器。运行 `voice-buddy hotkey-doctor` 可以看到需要授权的具体路径。

**命令行：**

```bash
# 不用快捷键也能停（例如在另一个终端窗口）
voice-buddy stop

# 改键
voice-buddy config --hotkey F3

# 关闭 / 开启快捷键监听
voice-buddy config --disable-hotkey
voice-buddy config --enable-hotkey

# 体检：辅助功能、fn 键模式、监听器存活等
voice-buddy hotkey-doctor
voice-buddy hotkey-doctor --non-interactive   # 跳过交互按键
voice-buddy hotkey-doctor --json              # 机器可读输出
```

**行为说明：**

- F2 只会打断**当前正在播**的那一段音频，不会取消还没开始的 TTS 队列。
- 仅支持 macOS。`pyobjc-framework-Quartz` 在 Darwin 上会自动安装。
- 监听器进程在 Claude Code 打开时启动；最后一个会话关闭后约 30 秒自动退出。
- 如果你重建虚拟环境或升级 Python，「辅助功能」授权可能会悄悄失效（绑定可执行路径）。`voice-buddy hotkey-doctor` 会提示漂移——把新路径重新授权一次即可。
- 完整 QA 清单见 `docs/manual-tests.md`。

## License

MIT
