# claude-tab-tracking

[English](README.md)

> 一眼掌握每个 Claude Code 会话的工作状态。

![demo](assets/demo.svg)

为 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 提供实时任务追踪。自动显示每个会话正在做什么，并随对话进展实时更新。

同时运行多个 Claude Code 会话时，切换窗口即可一眼看到每个会话的当前任务。

## 效果展示

```
[WIP]  修复 api/routes.py 中的认证 bug
[DONE] 部署模型到生产服务器
       my-project  |  ctx 14%  |  23min
```

**状态标识：**
- `[---]` — 会话刚启动，显示目录和 git 分支
- `[WIP]` — 任务进行中，每轮对话自动更新
- `[DONE]` — 任务已完成（自动检测）
- `[SET]` — 通过 `/task` 手动设置的任务

当完成一个任务并开始新任务时，上一个任务会以暗色 `[DONE]` 保留在当前任务下方。

## 工作原理

四个 Claude Code hooks 协同工作：

| Hook | 功能 |
|------|------|
| `SessionStart` | 写入 `目录 [分支]` 作为初始标签 |
| `Stop` | 每次助手回复后：读取对话记录，更新任务描述，检测完成状态 |
| `TaskCompleted` | Claude 明确完成任务时标记为 `[DONE]` |
| `SessionEnd` | 清理会话状态文件 |

### 摘要生成后端

插件自动选择最佳可用后端：

| 优先级 | 后端 | 质量 | 速度 | 成本 |
|--------|------|------|------|------|
| 1 | Claude API（需设置 `ANTHROPIC_API_KEY`） | 最佳 | ~2 秒 | 约 $1/月 |
| 2 | Ollama（本地模型） | 良好 | ~2 秒 | 免费 |
| 3 | Claude Code CLI（Max 订阅） | 最佳 | ~10 秒（异步） | 包含在订阅内 |
| 4 | 关键词匹配 | 基础 | 即时 | 免费 |

无需额外设置，开箱即用。

#### 选择后端

设置 `CLAUDE_TAB_BACKEND` 环境变量来指定后端：

```bash
# 仅使用 Claude Code CLI（Max 订阅，无需 API key）
export CLAUDE_TAB_BACKEND=cli

# 仅使用 Anthropic API
export CLAUDE_TAB_BACKEND=api

# 仅使用本地 Ollama
export CLAUDE_TAB_BACKEND=ollama

# 仅使用关键词匹配（零网络请求）
export CLAUDE_TAB_BACKEND=keyword

# 自动检测最佳后端（默认）
export CLAUDE_TAB_BACKEND=auto
```

指定某个后端时，如果该后端失败则不会回退。设为 `auto`（或不设置）时，按优先级依次尝试所有后端。

### Token 预算

控制 `/recall` 注入的上下文量，以及备忘录条目的去重合并。

在 `~/.claude/memos/config.yaml` 中添加：

```yaml
# 每次 /recall 加载的最大 token 数（默认: 8000，0 = 不限制）
recall_token_budget: 8000

# 合并相似备忘录条目的时间窗口，单位秒（默认: 300，0 = 禁用）
memo_merge_window: 300

# 标题相似度合并阈值（0.0-1.0，默认: 0.6）
memo_merge_threshold: 0.6
```

**Recall 加载模式：**
- **完整模式**：文件在预算内 → 原样加载
- **摘要模式**：文件超出预算 → 仅加载标题 + 结论
- **截断模式**：摘要仍超预算 → 从最新条目向前加载至预算用完

单次覆盖：`/recall --budget 4000` 或 `/recall --full`（不限制）。

## 安装

需要 [jq](https://jqlang.github.io/jq/)：
```bash
brew install jq  # macOS
apt install jq   # Debian/Ubuntu
```

然后：
```bash
git clone https://github.com/lighthouse-strategy/claude-tab-tracking.git
cd claude-tab-tracking && ./install.sh
```

打开新的 Claude Code 会话，状态栏立即生效。

## 对话记忆

插件会自动从每次对话中提取关键信息，保存为结构化备忘录。

### 工作原理

每次助手回复后（对话超过 3 轮时），插件自动提取带标签的内容：

- **决策** — 架构和设计选择
- **数据** — 事实、统计、发现
- **结论** — 原因分析、结果
- **待办** — 后续行动项

备忘录保存在 `~/.claude/memos/{项目名}/{YYYY-MM-DD}.md`，按项目和日期归类。

### 恢复上下文

使用 `/recall` 加载历史备忘录：

```
/recall              # 列出最近项目，交互选择
/recall my-project   # 直接跳到某个项目的日期选择
/recall 3-20         # 加载指定日期的所有备忘录
```

启动会话时，插件会提示是否有历史记录：
```
[memo] 最近项目: my-app (今天, 3条) | api-server (3-20, 5条)
输入 /recall 查看详情
```

### 查看备忘录

使用 `/memo` 浏览备忘录（不加载到上下文）：

```
/memo                # 查看今天的备忘录
/memo 3-20           # 查看指定日期的备忘录
/memo my-project     # 列出某项目最近的备忘录文件
/memo keyword        # 跨所有备忘录搜索关键词
```

## 手动设置任务

使用 `/task` 命令为当前会话设置自定义描述：

```
/task 审查 Q1 策略报告
```

这会写入 `MANUAL:` 前缀，锁定描述并停止自动更新。状态显示为 `[SET]`。

## 安装的文件

| 文件 | 用途 |
|------|------|
| `~/.claude/scripts/session_start.sh` | SessionStart hook |
| `~/.claude/scripts/dynamic_task_update.sh` | Stop hook（bash 封装） |
| `~/.claude/scripts/dynamic_task_update.py` | Stop hook（对话解析 + LLM 摘要） |
| `~/.claude/scripts/cli_background.py` | Claude Code CLI 后端的后台执行脚本 |
| `~/.claude/scripts/task_completed.sh` | TaskCompleted hook |
| `~/.claude/scripts/session_statusline.sh` | 状态栏渲染 |
| `~/.claude/scripts/session_end.sh` | SessionEnd 清理 |
| `~/.claude/commands/task.md` | `/task` 命令 |
| `~/.claude/commands/memo.md` | `/memo` 命令 |
| `~/.claude/commands/recall.md` | `/recall` 命令 |
| `~/.claude/session-tasks/` | 会话状态（7 天后自动清理） |
| `~/.claude/memos/` | 对话备忘录（按项目/日期归类） |

## 卸载

```bash
rm -f ~/.claude/scripts/session_start.sh \
      ~/.claude/scripts/dynamic_task_update.sh \
      ~/.claude/scripts/dynamic_task_update.py \
      ~/.claude/scripts/cli_background.py \
      ~/.claude/scripts/task_completed.sh \
      ~/.claude/scripts/session_statusline.sh \
      ~/.claude/scripts/session_end.sh \
      ~/.claude/commands/task.md \
      ~/.claude/commands/memo.md \
      ~/.claude/commands/recall.md
rm -rf ~/.claude/session-tasks/
rm -rf ~/.claude/memos/
```

然后从 `~/.claude/settings.json` 的 `hooks` 中删除 `SessionStart`、`Stop`、`TaskCompleted`、`SessionEnd` 条目，并删除 `statusLine` 键。

## 更新日志

### 2026-09-25

- **修复:CLI 后端从未运行(session 一直停在 `[---]`/INIT)** — `CLAUDE_TAB_SKIP_HOOK` 防递归检查原本写在 `dynamic_task_update.py` 的模块 import 阶段,而 `cli_background.py` 恰好带着该变量启动并 import 这个模块,导致 helper 在调用 `claude -p` 之前就退出。没有 `ANTHROPIC_API_KEY` 也没有 Ollama 的机器上,任务更新和 memo 都静默失效。检查已移入 `main()`,并补了回归测试。
- **修复:Stop hook 输出** — `dynamic_task_update.sh` 所有退出路径统一输出 `{"continue":true,"suppressOutput":true}`,固定 hook 环境的 `PATH`,并吞掉 Python stderr,后端失败不再冒泡成 hook 报错。

### 2026-03-22

- **修复：CLI 后端死循环** — 子进程 `claude -p` 现在使用 `disableAllHooks` + 环境变量双重防护，防止 Stop hook 递归调用。感谢 [@GP2P](https://github.com/GP2P) 提交 PR #3。
- **修复：读取临时文件失败时崩溃** — `cli_background.py` 不再因读取失败抛出 `UnboundLocalError`。
- **修复：安装时 settings.json 格式错误** — 现在显示清晰的错误提示，而非 Python 报错。
- **修复：项目路径含空格时 memo 概览出错** — `session_start.sh` 不再错误地分割路径。
- **修复：`/task` 命令丢失上一个任务记录** — 手动设置任务时现在保留 PREV 行。
- **修复：memo 归档时单目录出错导致全部跳过** — 增加了逐目录的错误处理。
- **修复：任务文件竞争写入** — 使用文件锁防止并发后台进程损坏任务状态。
- **修复：Linux 兼容性** — 当 `/usr/bin/python3` 不存在时自动回退到 PATH 中的 `python3`。

### 2026-03-21

- **新增：对话记忆** — 自动从对话中提取决策、结论和待办事项，按项目和日期保存为结构化备忘录。
- **新增：`/recall` 命令** — 交互式加载历史备忘录到当前会话上下文。
- **新增：`/memo` 命令** — 浏览和搜索备忘录。
- **新增：会话启动 memo 提示** — 启动时显示最近项目的备忘录数量。

## 作者

由 [lighthouse-strategy](https://github.com/lighthouse-strategy) 构建

## 许可证

MIT
