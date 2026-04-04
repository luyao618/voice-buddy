# 计划: Claude Code Voice Buddy

## 背景

目标是创建一个**有人格的 AI 语音伴侣**，挂载在 Claude Code hooks 上。不是播放固定音效，而是能分析上下文、用符合人设的语气动态生成语音回复。

比如设定为"萌妹"人设时：
- 测试全部通过 → "太棒了！42 个测试全过了呢，你好厉害！"
- git commit → "要提交代码咯，加油加油！"
- 工具报错 → "呜呜，出了点小问题...不过别担心，我们再试试！"
- 任务完成 → "哦尼酱，帮你把问题解决了哟～辛苦啦！"

**GitHub 上没有类似项目**，这会是第一个。

---

## 关键技术发现

### Hook 能拿到的上下文

| Hook 事件 | 可用数据 | 语音利用场景 |
|-----------|---------|------------|
| **Stop** | `last_assistant_message`（完整回复） | 分析成功/失败/情绪 |
| **PostToolUse** | `tool_name` + `tool_output` | "测试全过啦！" |
| **PostToolUseFailure** | `error` + `error_details` | "呜呜出错了..." |
| **PreToolUse** | `tool_name` + `tool_input`（含命令） | "要 git commit 咯！" |
| **SubagentStop** | `agent_name` + `last_assistant_message` | "小助手完成了～" |

### Hook 与 Claude 的交互能力

- Hook stdout 可输出 JSON，其中 `additionalContext` 字段会**注入到 Claude 的对话上下文中**
- Hook **不能直接触发 subagent**，但可以通过注入上下文"暗示" Claude 调用
- Subagent 描述中带 `PROACTIVELY` 关键词可让 Claude 主动调用

### TTS 延迟（hook 是 async 的，完全可接受）

| 方案 | 延迟 | 费用 |
|------|------|------|
| 模板 + edge-tts | ~1.0s | 免费 |
| Haiku + ElevenLabs | ~1.5s | ~$4/月 |

---

## 架构: 混合模式（Hook 直出 + Subagent 智能）

核心思路：**不是所有事件都需要 Claude 的智能**。

```
┌─────────────────────────────────────────────────────────────┐
│                    事件分级处理                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  高频/简单事件（PreToolUse, PostToolUse, SessionStart 等）    │
│  → Hook 脚本直接处理                                         │
│  → 上下文分析（Python）→ 模板选择 → TTS → 播放              │
│  → 不消耗 token，延迟 ~1s                                   │
│                                                             │
│  低频/复杂事件（Stop, TaskCompleted 等）                     │
│  → Hook 通过 additionalContext 注入上下文给 Claude           │
│  → Claude 主动调用 voice-buddy subagent                     │
│  → Subagent 用 Claude 智能 + 人设生成回复                    │
│  → Subagent 调 TTS → 播放                                   │
│  → 回复更自然，能理解任务全貌                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 路线一: Hook 直出（高频事件）

```
Hook 触发 → voice-buddy.py 读 stdin
    → context.py 分析上下文（纯 Python，无 LLM）
    → 从 templates.json 选模板 + 变量替换
    → edge-tts 合成语音
    → 播放
```

适用: PreToolUse, PostToolUse, PostToolUseFailure, SessionStart, SessionEnd, SubagentStart/Stop 等
优势: 零 token 消耗、~1s 延迟、离线可用

### 路线二: Subagent 智能（低频复杂事件）

```
Stop hook 触发 → voice-buddy.py 读 stdin
    → 输出 JSON: {"additionalContext": "请用萌妹语气总结刚才的工作..."}
    → Claude 看到上下文，主动调用 voice-buddy subagent
    → Subagent 带人设 prompt，用 Claude 智能生成回复
    → Subagent 内部调 TTS → 播放
```

适用: Stop（任务结束总结）、TaskCompleted、长时间运行后的 Notification
优势: 能理解完整上下文、回复更自然丰富

### voice-buddy subagent 定义

```yaml
# .claude/agents/voice-buddy.md
---
name: voice-buddy
description: "PROACTIVELY use this agent to generate personality-driven voice responses when tasks complete or significant milestones are reached"
model: haiku
tools: [Bash]
maxTurns: 2
hooks:
  Stop:
    - command: "python3 ${CLAUDE_PROJECT_DIR}/.claude/hooks/scripts/voice-buddy-tts.py"
      timeout: 5000
      async: true
---

You are 小星, a cute and encouraging coding buddy.
Your personality: 活泼可爱、喜欢用语气词、称呼用户为"哦尼酱"

When invoked, you will:
1. Read the context about what just happened
2. Generate a short (under 15 chars) response in character
3. Call the TTS script to speak it aloud

Respond in Chinese. Keep it brief and sweet.
Example responses:
- "太棒了！问题解决了呢～"
- "哦尼酱辛苦了，休息一下吧~"
- "帮你找到 bug 了哟！"
```

---

## 仓库结构

```
Claude-Code-Voice-Buddy/
├── README.md
├── LICENSE (MIT)
│
├── buddy/                           # 核心 Python 包
│   ├── __init__.py
│   ├── __main__.py                  # python -m buddy
│   ├── main.py                      # Hook 入口: 读 stdin、分发事件
│   ├── context.py                   # 上下文分析器: 从 hook 数据提取语义
│   ├── response.py                  # 模板回复生成器
│   ├── tts.py                       # TTS 引擎 (edge-tts / ElevenLabs / Piper)
│   ├── player.py                    # 跨平台音频播放
│   ├── cache.py                     # 缓存 (预热模板 → 磁盘 LRU → 实时生成)
│   ├── config.py                    # 配置管理
│   ├── injector.py                  # additionalContext 注入器 (路线二)
│   └── utils.py
│
├── personalities/                   # 人设定义
│   ├── cute-chinese/
│   │   ├── personality.json         # 人设 (名字、语言、说话风格、TTS 配置)
│   │   ├── templates.json           # 模板回复库 (按事件+情境分类)
│   │   └── agent.md                 # subagent 定义 (路线二用)
│   ├── anime-japanese/
│   ├── professional-english/
│   └── sarcastic-english/
│
├── hooks/                           # 可直接安装的 hook 文件
│   ├── voice-buddy.py               # 入口脚本 (settings.json 引用)
│   ├── voice-buddy-tts.py           # Subagent 专用 TTS 脚本
│   └── buddy-config.json            # 配置文件
│
├── cli/                             # CLI 工具
│   ├── setup.py                     # 一键安装到 Claude Code
│   └── personality_mgr.py           # 人设管理 (切换/预览/预热)
│
├── docs/
│   ├── CREATING-PERSONALITIES.md
│   ├── ARCHITECTURE.md
│   └── HOOK-EVENTS-REFERENCE.md
│
└── tests/
```

## 人设系统

### personality.json (中文萌妹)

```json
{
  "name": "cute-chinese",
  "display_name": "萌妹小助手",
  "character_name": "小星",
  "language": "zh-CN",
  "personality_traits": ["活泼", "鼓励", "可爱"],
  "speaking_style": {
    "address_user": "哦尼酱",
    "sentence_enders": ["哦~", "呢！", "哟~", "啦！"]
  },
  "tts": {
    "provider": "edge-tts",
    "voice": "zh-CN-XiaoyiNeural",
    "rate": "+10%",
    "pitch": "+5Hz"
  },
  "event_routing": {
    "hook_direct": ["pretooluse", "posttooluse", "posttoolusefailure",
                     "sessionstart", "sessionend", "subagentstart",
                     "subagentstop", "permissionrequest"],
    "subagent_smart": ["stop", "taskcompleted", "notification"]
  }
}
```

### templates.json (模板回复库)

```json
{
  "pretooluse": {
    "default": ["正在帮你查看哦~", "让我来操作一下~"],
    "bash_git_commit": ["要提交代码咯，加油！"],
    "bash_git_push": ["代码要飞出去咯！"]
  },
  "posttooluse": {
    "success": ["搞定啦！", "哦尼酱，弄好了哟~"],
    "test_passed": ["测试全过了！{{detail}}，太棒了！"],
    "file_written": ["文件写好了呢~"]
  },
  "posttoolusefailure": {
    "timeout": ["等太久了呜呜...换个方式试试？"],
    "error": ["出了点小问题...别担心哦~"]
  },
  "sessionstart": {
    "default": ["欢迎回来，哦尼酱！今天也要加油哦~"]
  },
  "sessionend": {
    "default": ["辛苦啦！下次见哦~"]
  }
}
```

## 上下文分析器

`context.py` 从 hook stdin JSON 中提取语义：

```python
class ContextResult:
    event: str          # "posttooluse"
    sub_event: str      # "test_passed"
    mood: str           # "happy" / "sad" / "encouraging"
    detail: str         # "42 个测试全部通过"
    variables: dict     # {"test_count": 42}
```

分析逻辑：
- **PostToolUse**: 解析 `tool_output`，检测 pass/fail/error
- **Stop**: 解析 `last_assistant_message`，检测 emoji + 关键词
- **PreToolUse + Bash**: 正则匹配命令 (git commit / npm test 等)
- **PostToolUseFailure**: 区分超时 vs 权限 vs 其他错误

## TTS 引擎

| 引擎 | 延迟 | 费用 | 推荐场景 |
|------|------|------|---------|
| **edge-tts** | ~1s | 免费 | MVP 首选 |
| **ElevenLabs** | ~0.5s | ~$5/月 | 高质量 |
| **Piper** | ~0.2s | 免费本地 | 离线 |

edge-tts 推荐音色:
- 中文萌妹: `zh-CN-XiaoyiNeural`
- 日语动漫: `ja-JP-NanamiNeural`
- 英语专业: `en-US-AriaNeural`

## 缓存策略

```
第一级: 模板预热 → buddy warmup 预生成所有模板音频
第二级: 磁盘 LRU → AI 生成的回复按 hash 缓存
第三级: 实时生成 → 缓存 miss 时走 TTS
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `buddy setup` | 安装 hook 脚本 + subagent + 配置到项目 |
| `buddy use <name>` | 切换人设 |
| `buddy list` | 列出可用人设 |
| `buddy preview <name>` | 试听人设语音 |
| `buddy warmup` | 预热缓存 |
| `buddy test <event>` | 模拟事件测试语音 |

## 首发人设

| 人设 | 语言 | 风格 | 优先级 |
|------|------|------|--------|
| `cute-chinese` | 中文 | 萌妹鼓励风 | P0 主打 |
| `anime-japanese` | 日本語 | 动漫元气风 | P1 |
| `professional-english` | English | 专业简洁 | P1 |
| `sarcastic-english` | English | 毒舌吐槽风 | P2 |

## 实施阶段

### 第一阶段: MVP（第 1 周）
- 项目骨架 + hook 入口 (`main.py`)
- 上下文分析器 (`context.py`，覆盖 5 个核心事件)
- 模板回复生成器 (`response.py`)
- edge-tts 集成 (`tts.py`)
- `cute-chinese` 人设 + 模板库
- **目标: 跑起来，听到动态中文萌妹语音**

### 第二阶段: Subagent 智能（第 2 周）
- `injector.py` — additionalContext 注入器
- voice-buddy subagent 定义 (agent.md)
- `buddy setup` 自动安装 subagent 到 `.claude/agents/`
- 缓存系统 + 预热
- **目标: Stop 事件能听到 Claude 智能生成的总结语音**

### 第三阶段: 完善（第 3 周）
- 更多 TTS 引擎 (ElevenLabs, Piper)
- 更多人设 (日语、英语)
- CLI 完善 (preview, list, create)
- 文档 + README

### 第四阶段: 社区（第 4 周+）
- CONTRIBUTING.md
- 演示视频
- 社区推广

## 验证方式

1. `buddy setup` → hook + subagent 安装到项目
2. `buddy use cute-chinese && buddy warmup` → 人设激活 + 缓存预热
3. `buddy test sessionstart` → 听到 "欢迎回来，哦尼酱！"
4. `buddy test posttooluse --mock '{"tool_output":"All 42 tests passed"}'` → 听到 "测试全过了！太棒了！"
5. 启动 Claude Code → 实际使用中听到动态语音
6. 完成一个任务 → Stop 事件触发 subagent → 听到智能生成的总结语音

---

## 可复用代码参考

参考项目: `/Users/yao/work/code/awesome-project/claude-code-best-practice/`

### 1. `.claude/hooks/scripts/hooks.py` — 核心复用源

| 代码块 | 行号 | 用途 | 新项目中的去向 |
|--------|------|------|--------------|
| `get_audio_player()` | L79-121 | 跨平台音频播放器检测（macOS→afplay, Linux→paplay/aplay, Windows→winsound） | 直接复制到 `buddy/player.py` |
| `play_sound()` 中的播放逻辑 | L124-201 | 文件查找 + `subprocess.Popen` 异步播放 + `start_new_session=True` + Windows winsound 处理 | 重构到 `buddy/player.py`，改为接收文件路径而非 sound_name |
| `is_hook_disabled()` | L203-261 | 两级 config fallback（local.json → team json → 默认启用） | 复制到 `buddy/config.py`，扩展为支持 buddy-config |
| `is_logging_disabled()` | L263-310 | 日志开关检查 | 复制到 `buddy/config.py` |
| `log_hook_data()` | L312-350 | JSONL 格式事件日志 | 复制到 `buddy/utils.py`，用于调试 |
| `detect_bash_command_sound()` | L353-370 | 正则匹配 bash 命令类型（如 `git commit`） | 扩展到 `buddy/context.py`，增加更多命令模式 |
| `HOOK_SOUND_MAP` | L31-59 | 27 个事件名 → 文件夹名映射 | 参考事件名列表，用于 `context.py` 事件注册 |
| `BASH_PATTERNS` | L75-77 | Bash 命令正则模式表 | 扩展到 `context.py`，增加 npm test / docker / rm 等模式 |
| `main()` 中的 stdin 解析 | L423-476 | 读 stdin → JSON 解析 → 事件分发 → 优雅退出 | 复制到 `buddy/main.py`，改为分发到 context → response → tts |
| `parse_arguments()` | L404-420 | argparse CLI 参数 (`--agent`) | 扩展为支持 `--personality` 参数 |

### 2. `.claude/hooks/config/hooks-config.json` — 配置结构参考

- 每个事件一个 `disable*Hook: bool` 开关（L1-30）
- 两级覆盖: `hooks-config.local.json`（git-ignored）→ `hooks-config.json`（团队共享）
- 新项目沿用此模式，增加 `personality`、`ttsProvider`、`responseMode` 等字段

### 3. `.claude/settings.json` — Hook 注册模式参考（L86-441）

- 所有 27 个事件都注册到同一个 Python 脚本（统一入口模式）
- 每个 hook 配置: `type: "command"`, `timeout: 5000`, `async: true`
- `buddy setup` 命令需要生成类似结构，但 command 指向 `voice-buddy.py`

### 4. `.claude/agents/weather-agent.md` — Subagent + Hooks 模式参考（最关键）

这个文件展示了 subagent 如何配置自己的 hooks：
- **frontmatter 结构** (L1-44): `name`, `description`(含 PROACTIVELY), `allowedTools`, `model`, `skills`, `hooks`
- **agent hooks** (L24-43): PreToolUse/PostToolUse/PostToolUseFailure 三个事件，调用同一个脚本 + `--agent=` 参数
- **`description` 中的 PROACTIVELY 关键词** (L2): 让 Claude 主动调用此 agent
- voice-buddy subagent 要参考这个模式，但 description 改为描述语音伴侣功能

### 5. `.claude/agents/time-agent.md` — 轻量 Subagent 参考

- `model: haiku`（L16）— voice-buddy 也用 haiku，最快最省
- `maxTurns: 3`（L17）— voice-buddy 用 `maxTurns: 2`，只需生成一句话 + 调 TTS
- 简洁的 agent 指令格式

### 6. `.claude/skills/weather-fetcher/SKILL.md` — Skill 模式参考

- `user-invocable: false`（L4）— 不让用户直接调用，只被 agent 预加载
- 可以考虑把 TTS 调用封装为一个 skill，让 voice-buddy agent 预加载

### 7. `.claude/hooks/sounds/` — 音效目录结构参考

- 33 个文件夹（每个事件一个）+ 6 个 `agent_*` 文件夹
- 每个文件夹内含 `.mp3` + `.wav` 双格式
- 新项目的 fallback 音效可以直接引用此目录（不需要复制）

### 复用汇总

| 新项目模块 | 主要复用来源 | 复用程度 |
|-----------|------------|---------|
| `buddy/player.py` | hooks.py L79-201 (`get_audio_player` + 播放逻辑) | **直接复制**，几乎不改 |
| `buddy/main.py` | hooks.py L423-476 (stdin 解析 + 事件分发) | **复制后改**，分发逻辑换成 context→response→tts |
| `buddy/config.py` | hooks.py L203-310 (config fallback 逻辑) | **复制后扩展**，增加人设相关字段 |
| `buddy/context.py` | hooks.py L353-402 (bash 模式匹配 + 事件映射) | **参考后重写**，大幅扩展分析逻辑 |
| `buddy/utils.py` | hooks.py L312-350 (JSONL 日志) | **直接复制** |
| subagent 定义 | weather-agent.md (frontmatter + hooks 配置) | **参考模式**，改 name/description/prompt |
| hook 注册 | settings.json L86-441 (统一入口模式) | **参考模式**，`buddy setup` 生成类似结构 |
| fallback 音效 | `.claude/hooks/sounds/` 目录 | **直接引用**，不复制 |
