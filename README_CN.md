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
- `[SET]` — 通过 `/tab:task` 手动设置的任务

当完成一个任务并开始新任务时，上一个任务会以暗色 `[DONE]` 保留在当前任务下方。

## 工作原理

三个 Claude Code hooks 协同工作：

| Hook | 功能 |
|------|------|
| `SessionStart` | 写入 `目录 [分支]` 作为初始标签（恢复会话 / 压缩时保留原任务）；刷新状态栏启动器 |
| `Stop` | 每次助手回复后：读取对话记录，更新任务描述，检测完成状态 |
| `SessionEnd` | 清理会话状态文件 |

完成状态由对话内容判断（摘要器标记 `[完成]`），不使用 Claude Code 的 `TaskCompleted` 事件：该事件针对单个后台任务，而非整个会话。

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

控制 `/tab:recall` 注入的上下文量，以及备忘录条目的去重合并。

在 `~/.claude/memos/config.yaml` 中添加：

```yaml
# 每次 /tab:recall 加载的最大 token 数（默认: 8000，0 = 不限制）
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

单次覆盖：`/tab:recall --budget 4000` 或 `/tab:recall --full`（不限制）。

## 安装

需要 [jq](https://jqlang.github.io/jq/)（macOS `brew install jq`，Debian/Ubuntu `apt install jq`）和 Python 3（macOS 与多数 Linux 自带）。

### 通过插件市场安装（推荐）

在 Claude Code 里：

```
/plugin marketplace add lightpointventures/claude-tab-tracking
/plugin install claude-tab-tracking@claude-tab-tracking
/tab:setup
```

或在终端：

```bash
claude plugin marketplace add lightpointventures/claude-tab-tracking
claude plugin install claude-tab-tracking@claude-tab-tracking
```

然后在 Claude Code 里运行一次 `/tab:setup`。插件无法自行修改 `statusLine` 设置，这条命令替你写入（会先备份 `settings.json`）。装好插件后任务追踪和备忘录就已经在工作，`/tab:setup` 只决定你看不看得到。

升级无需重新设置：状态栏指向插件数据目录里的一个启动器，它总是解析到当前安装的版本，`claude plugin update claude-tab-tracking` 之后不用再跑 `/tab:setup`。

### 嵌入到其他状态栏工具

已经在用 [ccstatusline](https://github.com/sirmalloc/ccstatusline)、[claude-powerline](https://github.com/Owloops/claude-powerline) 或 [claude-hud](https://github.com/jarrodwatts/claude-hud)？可以保留。启动器支持 `--segment` 模式，只输出 `[WIP] …` 这一行，可作为自定义命令段接进去：

```bash
~/.claude/plugins/data/claude-tab-tracking-claude-tab-tracking/statusline.sh --segment
```

`/tab:setup` 检测到已有状态栏时会直接给出这条路径。

### 手动安装（不走插件市场）

```bash
git clone https://github.com/lightpointventures/claude-tab-tracking.git
cd claude-tab-tracking && ./install.sh
```

脚本复制到 `~/.claude/scripts/`，hooks 与状态栏写入 `~/.claude/settings.json`，命令安装为 `/task`、`/memo`、`/recall`（无 `tab:` 前缀）。不要与插件安装同时使用；`/tab:setup` 发现手动安装时会提议移除。

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

使用 `/tab:recall` 加载历史备忘录：

```
/tab:recall              # 列出最近项目，交互选择
/tab:recall my-project   # 直接跳到某个项目的日期选择
/tab:recall 3-20         # 加载指定日期的所有备忘录
```

启动会话时，插件会提示是否有历史记录：
```
[memo] 最近项目: my-app (今天, 3条) | api-server (3-20, 5条)
输入 /tab:recall 查看详情
```

### 查看备忘录

使用 `/tab:memo` 浏览备忘录（不加载到上下文）：

```
/tab:memo                # 查看今天的备忘录
/tab:memo 3-20           # 查看指定日期的备忘录
/tab:memo my-project     # 列出某项目最近的备忘录文件
/tab:memo search JWT     # 跨所有备忘录全文搜索
```

## 手动设置任务

使用 `/tab:task` 为当前会话设置自定义描述：

```
/tab:task 审查 Q1 策略报告
```

这会写入 `MANUAL:` 前缀，锁定描述并停止自动更新。状态显示为 `[SET]`。

## 文件

插件布局（插件市场安装）：

| 路径 | 用途 |
|------|------|
| `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json` | 插件与市场清单 |
| `hooks/hooks.json` | 注册 SessionStart / Stop / SessionEnd hooks |
| `commands/setup.md` | `/tab:setup`：写入状态栏设置 |
| `commands/task.md`、`memo.md`、`recall.md` | `/tab:task`、`/tab:memo`、`/tab:recall` |
| `scripts/session_start.sh` | SessionStart hook；同时生成状态栏启动器 |
| `scripts/dynamic_task_update.sh` + `.py` | Stop hook：对话解析 + 摘要后端 |
| `scripts/cli_background.py`、`claude_cli_common.py` | Claude Code CLI 后端的后台执行脚本 |
| `scripts/session_statusline.sh` | 状态栏渲染（`--segment` 用于嵌入） |
| `scripts/session_end.sh` | SessionEnd 清理 |
| `scripts/memo_search.py` | 备忘录全文搜索 |

写到本机的数据（两种安装方式相同）：

| 路径 | 用途 |
|------|------|
| `~/.claude/session-tasks/` | 会话任务状态（7 天后自动清理） |
| `~/.claude/session-tasks/_errors.log` | 后端失败记录（hook 本身永远不会报错） |
| `~/.claude/memos/` | 对话备忘录（按项目/日期归类） |
| `~/.claude/plugins/data/claude-tab-tracking-claude-tab-tracking/statusline.sh` | 稳定的状态栏启动器（仅插件安装） |

## 卸载

插件安装：

```
/plugin uninstall claude-tab-tracking@claude-tab-tracking
```

然后从 `~/.claude/settings.json` 删除 `/tab:setup` 写入的 `statusLine` 键。`~/.claude/` 下的备忘录和会话状态会保留。

手动安装：`./uninstall.sh`（移除 hooks、脚本和命令，保留数据）。

## 更新日志

### 1.0.0 — 2026-09-25

- **新增：官方插件格式** — `/plugin marketplace add lightpointventures/claude-tab-tracking` 后 `/plugin install claude-tab-tracking@claude-tab-tracking` 即可安装。hooks 通过 `hooks/hooks.json` 注册；命令为 `/tab:task`、`/tab:memo`、`/tab:recall`，新增 `/tab:setup`。
- **新增：`/tab:setup`** — 写入 `statusLine`（插件自身做不到），指向插件数据目录里一个不随升级变化的启动器。发现旧的手动安装时会提议移除，避免 hooks 跑两遍。
- **新增：`--segment` 模式** — 状态栏只输出任务那一行，可嵌入 ccstatusline、claude-powerline 或 claude-hud。
- **移除：`TaskCompleted` hook** — 当前 Claude Code 里该事件在后台任务/子代理完成时触发，而不是会话工作完成，会提前把会话标成 `[DONE]`。完成状态现在只来自摘要器。
- **修复：主路径下关键词后端从未生效** — `keyword_fallback()` 不接受后端循环传给每个后端的参数，`CLAUDE_TAB_BACKEND=keyword`（以及自动模式的最终兜底）静默失效。
- **修复：会话结束时丢掉最后一轮** — SessionEnd 曾删除代次标记，仍在运行的后台摘要器误判为「已被取代」而放弃写入，最后一轮的任务和备忘录随之丢失。

### 2026-09-25

- **修复：CLI 后端从未运行（session 一直停在 `[---]`）** — `CLAUDE_TAB_SKIP_HOOK` 防递归检查原本写在 `dynamic_task_update.py` 的 import 阶段，而后台 helper 恰好带着该变量启动并 import 这个模块，导致它在调用 `claude -p` 之前就退出。没有 `ANTHROPIC_API_KEY` 也没有 Ollama 的机器上，任务更新和备忘录都静默失效。检查已移入 `main()`。
- **修复：CLI 失败时状态栏不更新** — `claude -p` 失败、超时或返回未登录提示时，helper 改为写入关键词摘要，而不是保留旧描述。失败原因记录在 `~/.claude/session-tasks/_errors.log`。
- **修复：后台结果乱序** — 每次 Stop hook 写入一个代次标记，上一轮较慢的 helper 不会再覆盖较新的结果；helper 运行期间用户执行 `/task` 锁定的描述也会被保留。
- **修复：注入消息污染摘要** — 读取对话记录时跳过斜杠命令回显、`<system-reminder>` 块、任务通知、子代理消息和被中断的请求，它们不会再成为「第一条用户消息」锚点。
- **修复：resume / compact 重置任务** — `SessionStart` 在恢复会话、`/clear` 和自动压缩时也会触发；现在只在全新启动或任务文件不存在时写占位符，备忘录概览也只在启动时输出。
- **修复：`session_start.sh` 整数报错** — 没有条目的备忘录文件会在 stderr 产生 `integer expression expected`。
- **修复：Stop hook 输出** — `dynamic_task_update.sh` 所有退出路径统一输出 `{"continue":true,"suppressOutput":true}`，并固定 `PATH`。
- **改进：状态栏** — 优先使用 Claude Code 提供的 `context_window.used_percentage`（保留 token 计数回退），显示模型名，任务文本用 `printf` 原样输出反斜杠，输入异常时不再刷 stderr。
- **改进：安装脚本** — 重复运行 `install.sh` 不会再给已用绝对路径注册的 hook 添加重复项，并会打印将使用的摘要后端。`uninstall.sh` 补上 `memo_search.py` 和 `claude_cli_common.py`，解释器选择逻辑与安装脚本一致。
- **改进：附属文件清理** — `.lock` / `.gen` 文件在会话结束时删除，并纳入 7 天清理。
- **测试** — 125 个测试，包含在临时 `HOME` 下对每个 shell hook 的端到端运行。

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

由 [Lightpoint Ventures](https://github.com/lightpointventures) 构建

## 许可证

MIT
