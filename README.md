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

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — tested against **v2.1.179**
- Python 3.10 – 3.14 (3.9 is not supported; see Development below)
- Audio player (macOS: `afplay` built-in, Linux: `paplay`/`aplay`/`mpg123`)

> **Claude Code compatibility.** Voice Buddy ships its skill under
> `skills/voice-buddy/SKILL.md` and launches its hooks in
> [exec form](https://code.claude.com/docs/en/hooks) (`command` + `args`)
> resolved through `${CLAUDE_PLUGIN_ROOT}`. Both are the current plugin
> contract — the flat `commands/` layout and shell-form hooks that earlier
> releases used still load, but are no longer the documented default.
> Exec form and `${CLAUDE_PLUGIN_ROOT}` substitution are verified on v2.1.179;
> the docs publish no explicit version floor for either, so older releases are
> untested rather than known-broken. Release validation is
> `claude plugin validate . --strict`.

#### Install from Plugin Marketplace

Run these two commands in Claude Code, one after the other:
```bash
/plugin marketplace add luyao618/voice-buddy   # 1. Add plugin source
/plugin install voice-buddy                                 # 2. Install plugin
```

During installation you'll be prompted to choose a **style** and **nickname**. Press Enter to use defaults (cute-girl / Master).

Hooks are auto-registered on install — no manual setup needed.

#### Upgrade

```bash
/plugin marketplace update voice-buddy-marketplace   # refresh the source
/plugin update voice-buddy@voice-buddy-marketplace   # apply the new version
```

Restart Claude Code afterwards. A listener left over from the previous version
is terminated and replaced, so exactly one stays running.

> Use the fully-qualified `voice-buddy@voice-buddy-marketplace`. The bare name
> reports `Plugin "voice-buddy" not found`.

#### Uninstall

```bash
/plugin uninstall voice-buddy
```

Your settings are **kept** on purpose, so reinstalling restores your style and
nickname. To remove them as well:

```bash
# macOS
rm -rf ~/Library/Application\ Support/voice-buddy
# Linux
rm -rf ~/.config/voice-buddy
```

That directory holds `config.json`, the debug log, and the hotkey listener's
runtime state — nothing else on your system is touched.

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

#### One-time setup (required after first install)

The marketplace installer copies plugin files but does **not** install Python dependencies or grant macOS permissions. You need to do these three things once:

##### Step 1 — Install the macOS dependency

```bash
pip3 install 'pyobjc-framework-Quartz>=10.0,<13'
```

If you have multiple Python interpreters (system, Homebrew, pyenv, conda, depot_tools), make sure to install into the **same one** that runs `voice-buddy`. To find out which one:

```bash
voice-buddy hotkey-doctor --non-interactive
# Look for the row: [OK] python interpreter   current=/path/to/python3
```

Install pyobjc into that exact interpreter:

```bash
/path/to/python3 -m pip install 'pyobjc-framework-Quartz>=10.0,<13'
```

##### Step 2 — Enable "Use F1, F2, etc. as standard function keys"

Open **System Settings → Keyboard → Keyboard Shortcuts… → Function Keys** and turn ON **"Use F1, F2, etc. keys as standard function keys"**.

Without this, F2 is intercepted by macOS as "brightness up" before any app can see it.

##### Step 3 — Grant Accessibility to your Python interpreter

Run the doctor to find the exact path:

```bash
voice-buddy hotkey-doctor --non-interactive
# Look for: [FAIL] Accessibility granted   grant Accessibility to: /path/to/python3
```

Then open **System Settings → Privacy & Security → Accessibility**:

1. Click the **+** button.
2. Press **⌘ + Shift + G** to open "Go to Folder", paste the directory of that python path, hit Enter.
3. **If `python3` is a symlink** (common with depot_tools / pyenv shims), it cannot be selected directly. Instead select the real binary it points to (e.g. `python3.11`). To check:
   ```bash
   ls -la /path/to/python3
   ```
4. If macOS still refuses to select the file, open the directory in Finder (`open /path/to/bin`) and **drag the python binary into the Accessibility list** instead.
5. Make sure the toggle next to the new entry is **green / on**.

##### Step 4 — Restart Claude Code

Close and reopen Claude Code so SessionStart fires and spawns the listener subprocess.

##### Verify everything works

```bash
voice-buddy hotkey-doctor
```

Expected (interactive mode will ask you to press F2):

```
[OK  ] python interpreter
[OK  ] pyobjc importable
[OK  ] Accessibility granted
[OK  ] EventTap reachability
[OK  ] F-key fn-mode          F2 keydown observed
[OK  ] coord.lock writable
[OK  ] listener liveness      pid=...
[OK  ] version handshake
[OK  ] sessions registry
[OK  ] playback_pids sanity
```

If any row says FAIL or WARN, the detail message tells you what to fix.

#### Daily use

```bash
# Stop without using the hotkey (e.g. from another terminal)
voice-buddy stop

# Restart the hotkey listener (stops it by PID; a new session respawns it)
voice-buddy hotkey-restart

# Change the bound key
voice-buddy config --hotkey F3

# Disable / re-enable the hotkey listener
voice-buddy config --disable-hotkey
voice-buddy config --enable-hotkey

# Diagnose
voice-buddy hotkey-doctor
voice-buddy hotkey-doctor --non-interactive   # CI-friendly, skips the F2 press
voice-buddy hotkey-doctor --json              # machine-readable
```

#### How the listener lifecycle works

- The listener is a singleton subprocess. **One per machine**, no matter how many Claude Code windows you open.
- **Spawn**: SessionStart hook checks if a live listener exists; if not, spawns one (detached, ~500 ms cold start).
- **Self-exit**: When the last Claude Code session ends, the listener notices via a 30 s idle timer and exits cleanly.
- **F2 = stop currently playing audio only.** Queued TTS that hasn't started playing yet is not cancelled.
- See `docs/manual-tests.md` for the full QA checklist.

#### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `voice-buddy hotkey-doctor` says `[FAIL] pyobjc importable` | pyobjc not installed in the right interpreter | Run Step 1 against the exact path the doctor reports |
| `[FAIL] Accessibility granted` after granting it | Granted the wrong interpreter, or the path is a symlink | Re-run doctor; grant the path it reports; if symlink, grant the real binary |
| F2 still doesn't work after all OK rows | Listener was spawned before pyobjc was installed | `voice-buddy hotkey-restart`, then start a new session |
| F2 stopped working and the doctor shows a listener that isn't running | The listener was killed uncleanly and its PID was recycled onto another process | `voice-buddy hotkey-restart` clears the stale record; a new session respawns it |
| F2 doesn't work after upgrading Python / recreating venv | Accessibility grant is bound to the executable path; the new python is a different file | Doctor will show `[WARN] python interpreter` with `DRIFT`; re-grant Accessibility to the new path |
| Want to verify in a CI pipeline | — | `voice-buddy hotkey-doctor --non-interactive --json` |

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
└── tests/                   # unit + contract + release-gate suites
```

### Development

```bash
git clone https://github.com/luyao618/voice-buddy.git
cd voice-buddy

# Editable install with dev extras, pinned to the verified versions
pip install -c constraints.txt -e ".[dev]"

# Run tests
python3 -m pytest tests/ -v

# Dependency advisory check
python3 -m pip_audit

# Regenerate pre-packaged audio (after editing templates)
python3 -m voice_buddy.generate_audio
```

#### Dependency files

| File | Role |
|------|------|
| `pyproject.toml` | Source of truth. Declares what versions are **allowed** (ranges). |
| `constraints.txt` | Fully-pinned direct **and** transitive versions — what was actually **verified**. |
| `requirements.txt` / `requirements-dev.txt` | Convenience installers that mirror `pyproject.toml`. |

Install reproducibly by passing the constraints file:

```bash
pip install -c constraints.txt .            # runtime only
pip install -c constraints.txt -e ".[dev]"  # development
```

Omitting `-c constraints.txt` still works and resolves anything inside the
declared ranges — use that to pick up newer versions deliberately.

**Updating dependencies:**

1. Edit the range in `pyproject.toml` (and mirror it in `requirements*.txt`).
2. Run `PYTHON=python3.10 bash scripts/regen-constraints.sh` to re-resolve and
   re-pin. It needs only CPython's bundled `venv`/`ensurepip` — no `uv`, no
   preinstalled pip.
   **Regenerate on the 3.10 floor, not a newer interpreter.** `aiohttp` and
   `pytest` gate transitives behind `python_version < "3.11"`
   (`async-timeout`, `exceptiongroup`), so a resolve on 3.11+ silently omits
   them and the result installs everywhere *except* the floor. The script
   enforces this and refuses any other version; the extra pins are inert on
   newer interpreters, since a constraint only binds a package actually being
   installed.
   A failed resolve exits non-zero and leaves `constraints.txt` untouched.
3. Run the suite and `python3 -m pip_audit`.

`tests/test_packaging.py` fails if the three files disagree — on an extra
dependency, a differing version range, a dropped environment marker, an
unpinned constraint, or a pin that falls outside its declared range. It also
walks the dependency closure, so removing any transitive pin from
`constraints.txt` fails the suite rather than silently weakening the lock, and
asserts the floor-gated pins are present so an off-floor regen is caught on
any interpreter.

#### Supported Python versions

`3.10` – `3.14`, each verified by installing the constrained dependency set
into a fresh virtualenv and running the full suite. `requires-python =
">=3.10,<3.15"` encodes that matrix on both ends, so anything outside it is
rejected at resolve time rather than installing and failing later.

**3.9 is not supported.** `pyobjc-core` publishes no 3.9 wheel and its source
build fails, and `pytest` 9.x / `pip` 26.x both declare `Requires-Python
>=3.10`. The floor makes installers reject 3.9 up front rather than failing
partway through a build.

**3.15+ is not supported yet** — it doesn't exist, so it can't have been
tested, and `pyobjc` tracks the CPython C-ABI closely enough that a new minor
is exactly where this package would break. To add one: append the minor to
`SUPPORTED_MINORS` in `tests/test_packaging.py`, add its classifier, raise the
cap, and run the matrix on it. The contract test fails if the cap and
`SUPPORTED_MINORS` disagree, so the cap can't be raised without the
declaration.

The packaging contracts run on every supported version, including the 3.10
floor: `tomllib` is 3.11+, so the dev extra carries a `tomli` backport for
3.10 rather than skipping the tests there.

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

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — 已在 **v2.1.179** 上验证
- Python 3.10 – 3.14（不支持 3.9，原因见下方 Development 小节）
- 音频播放器（macOS: `afplay` 内置, Linux: `paplay`/`aplay`/`mpg123`）

> **Claude Code 兼容性说明.** Voice Buddy 的 skill 位于
> `skills/voice-buddy/SKILL.md`，hooks 使用 exec form（`command` + `args`）
> 并通过 `${CLAUDE_PLUGIN_ROOT}` 解析路径，两者都是当前的 plugin contract。
> 旧的 `commands/` 扁平布局与 shell-form hooks 仍可加载，但已不是官方默认写法。
> exec form 与 `${CLAUDE_PLUGIN_ROOT}` 替换已在 v2.1.179 实测通过；官方文档
> 未给出这两项的最低版本要求，因此更早的版本属于「未测试」而非「已知不可用」。
> 发布前的校验命令为 `claude plugin validate . --strict`。

#### 从 Plugin Marketplace 安装

在 Claude Code 中依次运行以下两条命令：
```bash
/plugin marketplace add luyao618/voice-buddy   # 1. 添加插件源
/plugin install voice-buddy                                 # 2. 安装插件
```

安装时会提示选择**风格**和**称呼**，也可以直接回车使用默认值（cute-girl / Master）。

安装完成后 Hook 自动注册，无需手动配置。

#### 升级

```bash
/plugin marketplace update voice-buddy-marketplace   # 刷新插件源
/plugin update voice-buddy@voice-buddy-marketplace   # 应用新版本
```

之后重启 Claude Code。旧版本遗留的监听器会被终止并替换，保证同时只有一个在跑。

> 必须用完整的 `voice-buddy@voice-buddy-marketplace`。只写插件名会报
> `Plugin "voice-buddy" not found`。

#### 卸载

```bash
/plugin uninstall voice-buddy
```

配置会**特意保留**，重新安装即可恢复你的风格与称呼。如果想一并删除：

```bash
# macOS
rm -rf ~/Library/Application\ Support/voice-buddy
# Linux
rm -rf ~/.config/voice-buddy
```

该目录只存放 `config.json`、调试日志和快捷键监听器的运行时状态，不会影响系统其他部分。

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

#### 首次安装后必做的设置

Marketplace 安装器只会复制插件文件，**不会**安装 Python 依赖，也不会授权 macOS 权限。安装后需要做下面三件事，做一次就行：

##### 第 ① 步 — 安装 macOS 依赖

```bash
pip3 install 'pyobjc-framework-Quartz>=10.0,<13'
```

如果你电脑上有多个 Python 解释器（系统自带 / Homebrew / pyenv / conda / depot_tools 等），**必须装到运行 `voice-buddy` 的那一个**里。先用 doctor 查出来：

```bash
voice-buddy hotkey-doctor --non-interactive
# 看这一行：[OK] python interpreter   current=/path/to/python3
```

然后用那个路径直接装：

```bash
/path/to/python3 -m pip install 'pyobjc-framework-Quartz>=10.0,<13'
```

##### 第 ② 步 — 把 F1/F2 设成标准功能键

打开 **系统设置 → 键盘 → 键盘快捷键… → 功能键**，把 **「将 F1、F2 等键用作标准功能键」打勾**。

不勾的话 F2 会被 macOS 截为「亮度增加」，应用根本收不到这个键。

##### 第 ③ 步 — 给 Python 解释器授权辅助功能

跑 doctor 拿到精确路径：

```bash
voice-buddy hotkey-doctor --non-interactive
# 看这一行：[FAIL] Accessibility granted   grant Accessibility to: /path/to/python3
```

然后打开 **系统设置 → 隐私与安全性 → 辅助功能**：

1. 点 **+** 号
2. 弹出文件选择器后按 **⌘ + Shift + G**，把上面 python 所在目录粘进去回车
3. **如果 `python3` 是符号链接**（depot_tools / pyenv shim 经常这样），无法直接选中。改选它指向的真实二进制文件（例如 `python3.11`）。检查方法：
   ```bash
   ls -la /path/to/python3
   ```
4. 如果文件选择器还是不让选，**打开 Finder 把那个 python 二进制直接拖到「辅助功能」列表里**：
   ```bash
   open /path/to/bin
   ```
5. 确认新增那一行右边的开关是 **绿色（开）**

##### 第 ④ 步 — 重启 Claude Code

关闭并重新打开 Claude Code，让 SessionStart 钩子触发监听器进程启动。

##### 验证

```bash
voice-buddy hotkey-doctor
```

期望看到（互动模式会让你按一次 F2）：

```
[OK  ] python interpreter
[OK  ] pyobjc importable
[OK  ] Accessibility granted
[OK  ] EventTap reachability
[OK  ] F-key fn-mode          F2 keydown observed
[OK  ] coord.lock writable
[OK  ] listener liveness      pid=...
[OK  ] version handshake
[OK  ] sessions registry
[OK  ] playback_pids sanity
```

任何一行 FAIL 或 WARN，detail 列会告诉你怎么修。

#### 日常使用

```bash
# 不靠快捷键也能停（例如另一个终端窗口）
voice-buddy stop

# 重启快捷键监听器（按 PID 停止；下个 session 会自动重新拉起）
voice-buddy hotkey-restart

# 改键
voice-buddy config --hotkey F3

# 关闭 / 开启快捷键监听
voice-buddy config --disable-hotkey
voice-buddy config --enable-hotkey

# 体检
voice-buddy hotkey-doctor
voice-buddy hotkey-doctor --non-interactive   # CI 友好，跳过按键
voice-buddy hotkey-doctor --json              # 机器可读
```

#### 监听器生命周期

- 监听器是**单例**进程，整台机器**只有一个**，不管开几个 Claude Code 窗口
- **启动**：SessionStart 钩子检查是否有活监听器；没有就 spawn 一个（detached，约 500ms 冷启动）
- **退出**：最后一个 Claude Code 会话关闭后，监听器内置的 30 秒空闲定时器会发现 sessions/ 空了，自动退出
- **F2 只打断当前正在播的那一段音频**，不会取消还没开始播的 TTS 队列
- 完整 QA 清单见 `docs/manual-tests.md`

#### 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| doctor 显示 `[FAIL] pyobjc importable` | pyobjc 没装到对的解释器 | 用第 ① 步对着 doctor 报告的路径重装 |
| 已经授权了，doctor 还报 `[FAIL] Accessibility` | 授权了错的解释器，或路径是符号链接 | 重跑 doctor 看它给的路径；是符号链接就授权真实二进制 |
| 所有 OK 但 F2 还是不响应 | 监听器是在你装 pyobjc 之前 spawn 的，已经因为 import 失败退出 | 运行 `voice-buddy hotkey-restart`，然后开一个新 session |
| F2 突然失效，且 doctor 显示的监听器其实没在跑 | 监听器被强杀后 PID 被系统回收给了别的进程 | `voice-buddy hotkey-restart` 会清掉这条陈旧记录，新 session 会重新拉起 |
| 升级 Python / 重建 venv 后 F2 失效 | 辅助功能授权绑定可执行文件路径，新 python 是不同文件 | doctor 会显示 `[WARN] python interpreter` 含 `DRIFT`，重新授权新路径 |
| 想在 CI 里验证 | — | `voice-buddy hotkey-doctor --non-interactive --json` |

## License

MIT
