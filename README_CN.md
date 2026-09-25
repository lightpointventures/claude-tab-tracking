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

五个 Claude Code hooks 协同工作：

| Hook | 功能 |
|------|------|
| `SessionStart` | 写入 `目录 [分支]` 作为初始标签（恢复会话 / 压缩时保留原任务）；刷新状态栏启动器 |
| `Stop` | 每次助手回复后：读取对话记录，更新任务描述，检测完成状态 |
| `SubagentStop` | 子代理结束时，把它（类型、描述、用时）记到今日备忘录的当前任务下 |
| `Notification` | 可选的桌面通知，附带会话当前任务（默认关闭） |
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

## 一眼看全部会话

`/tab:sessions` 列出这台机器上所有活着的 Claude Code 会话，不论是终端还是桌面应用启动的：

```
5 live session(s) · 2 busy
▶ [busy] plugin release  ·  task-tracking  ·  3m ago
      [WIP]  Ship the marketplace install and update the README
      agents 1 running / 6 total
        ◐ general-purpose: Searching GitHub for tmux/notify repos
      memo   8 entries today · last: Decide plugin command namespace
  [idle] GluGlu 项目梳理与进展  ·  xinguanying · desktop  ·  1h10m ago
      [WIP]  筹备明日 Hillsdale 周边零售门店线下调研走访
```

每个会话显示：原生会话名和忙/闲状态（读自 Claude Code 自己的 `~/.claude/sessions/` 注册表）、本插件的任务行、仍在运行的子代理及其一句话描述、该项目今天的备忘录条数。`▶` 标记你当前所在的会话。`/tab:sessions json` 输出 JSON；`/tab:sessions all` 包含进程已退出的会话。底层脚本 `scripts/sessions_overview.py` 也可单独运行。

## 对话记忆

插件会自动从每次对话中提取关键信息，保存为结构化备忘录。

### 工作原理

每次助手回复后（对话超过 3 轮时），插件自动提取带标签的内容：

- **决策** — 架构和设计选择
- **数据** — 事实、统计、发现
- **结论** — 原因分析、结果
- **待办** — 后续行动项

备忘录保存在 `~/.claude/memos/{项目名}/{YYYY-MM-DD}.md`，按项目和日期归类。

### 子代理入备忘录

子代理结束时（`SubagentStop` hook），会在当前任务条目下记一条：

```
## 14:02 | Ship the marketplace install
- 【决策】name the plugin "tab" so commands are /tab:*
- 【子代理】general-purpose「Research statusline tools on GitHub」 · 4m13s
```

运行不到 15 秒的子代理不记。在 `~/.claude/memos/config.yaml` 里设 `memo_subagents: false` 可关闭。

### 桌面通知（可选）

打开插件的 **Desktop notifications** 选项（`/plugin` → configure，或安装时 `claude plugin install … --config notifications=true`）后，会话等待输入、需要授权、或后台代理完成时会弹系统通知。通知里带着该会话的当前任务，同时开着几个会话也知道是哪个在叫你。macOS 用 `osascript`，Linux 有 `notify-send` 则用它。默认关闭。

### 恢复上下文

`/tab:recall` 在 token 预算内把备忘录加载回对话，分两段：放得下的条目全文加载，其余以一行一条的索引列出，可按 id 再取。

```
/tab:recall                       # 当前项目，最近 14 天，按预算加载
/tab:recall my-project            # 其他项目（"all" 为全部项目）
/tab:recall index                 # 只列索引不加载
/tab:recall general/2026-09-25#3  # 按 id 加载指定条目
/tab:recall --budget 4000         # 覆盖预算；--full 不限制
```

哪些条目入选由评分决定，而不只看日期：

| 标签 | 权重 | 半衰期 |
|------|------|--------|
| 【决策】 | 1.0 | 90 天 |
| 【TODO】未关闭 | 1.0 | 不衰减（已关闭的降到 0.1） |
| 【手记】手写笔记 | 1.0 | 90 天 |
| 【结论】 | 0.7 | 30 天 |
| 【数据】 | 0.4 | 14 天 |
| 【子代理】 | 0.3 | 7 天 |

hook 自动写的条目权重减半，`/tab:memo add` 手写的按全额计。同一项目里被后来相似决策取代的决策标为 *superseded*，权重 0.35。预算取自 `~/.claude/memos/config.yaml` 的 `recall_token_budget`（默认 8000）。底层脚本 `scripts/memo_recall.py` 可直接使用。

### 接着上次做

会话结束时，插件记下这个目录正在做的任务和 git HEAD。7 天内在同一目录、HEAD 未变的情况下再开会话，开头会提示：

```
[tab] Last session in this directory (2h ago, HEAD unchanged): Migrate the parser to SQLite
[tab] Continue where it left off, or run /tab:recall to load that day's memos.
```

在 `~/.claude/memos/config.yaml` 设 `handoff: false` 可关闭。

### 与 Claude Code 原生记忆共存

Claude Code 有自己的 auto-memory（每个项目的 `MEMORY.md` 加主题文件）。本插件不往里写内容，只在项目已有备忘录时往 `MEMORY.md` 加一行指针（只加一次），说明每日备忘录在哪、怎么加载。`memory_pointer: false` 可关闭。

### 永远不会写入的内容

写备忘录前，形似凭据的字符串会替换成 `[REDACTED]`：API key（`sk-ant-…`、`AKIA…`、`ghp_…`、`xox…`、Google key）、JWT、bearer token、私钥块，以及 `password=` / `token=` / `api_key=` 这类键值对。

### 查看备忘录

使用 `/tab:memo` 浏览备忘录（不加载到上下文）：

```
/tab:memo                # 查看今天的备忘录
/tab:memo 3-20           # 查看指定日期的备忘录
/tab:memo my-project     # 列出某项目最近的备忘录文件
/tab:memo search JWT     # 跨所有备忘录全文搜索
/tab:memo add <text>     # 在当前任务下记一条手写笔记
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
| `commands/task.md`、`memo.md`、`recall.md`、`sessions.md` | `/tab:task`、`/tab:memo`、`/tab:recall`、`/tab:sessions` |
| `scripts/sessions_overview.py` | `/tab:sessions` 使用的会话总览脚本 |
| `scripts/subagent_stop.sh` + `subagent_memo.py` | SubagentStop hook：子代理写入备忘录 |
| `scripts/notify.sh` | Notification hook（可选桌面通知） |
| `scripts/session_start.sh` | SessionStart hook；同时生成状态栏启动器 |
| `scripts/dynamic_task_update.sh` + `.py` | Stop hook：对话解析 + 摘要后端 |
| `scripts/cli_background.py`、`claude_cli_common.py` | Claude Code CLI 后端的后台执行脚本 |
| `scripts/session_statusline.sh` | 状态栏渲染（`--segment` 用于嵌入） |
| `scripts/session_end.sh` | SessionEnd 清理 |
| `scripts/memo_search.py` | 备忘录全文搜索 |
| `scripts/memo_recall.py` | 评分 + 预算的召回（`auto` / `index` / `show` / `add`） |

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

### 1.2.0 — 2026-09-25

- **新增：评分 + 预算的召回** — `/tab:recall` 改由 `memo_recall.py` 执行：按标签权重、按标签半衰期、来源（手写 vs hook）和状态（被取代的决策、已关闭的 TODO）评分，在 `recall_token_budget` 内加载最有价值的条目，其余列成索引可按 id 再取（`show`）。`index` 只列不加载；`add` 记一条【手记】。
- **新增：`/tab:memo add`** — 在当前任务下记手写笔记，权重高于 hook 输出。
- **新增：交接锚** — SessionEnd 记下目录的任务和 git HEAD；7 天内同目录、同 HEAD 再开会话时以此开场。`handoff: false` 关闭。
- **新增：原生记忆指针** — 在 Claude Code 的 `MEMORY.md` 里加一行指向本项目备忘录的指针，只加一次，不写内容。`memory_pointer: false` 关闭。
- **新增：写盘脱敏** — API key、JWT、bearer token、私钥和 `password=` 类键值对在写入备忘录前替换成 `[REDACTED]`。
- 未做：`PreCompact` 捕获点。Stop hook 每轮都写备忘录，磁盘上的对话记录也不受压缩影响，它没有可保存的东西。

### 1.1.0 — 2026-09-25

- **新增：`/tab:sessions`** — 所有活跃会话总览：原生会话名与忙/闲、本插件任务行、运行中的子代理及描述、今日备忘录条数。终端与桌面应用会话都能看到；支持 `json` 和 `all` 参数。
- **新增：子代理入备忘录** — `SubagentStop` 把每个结束的子代理（类型、描述、用时）记到当前任务下；不足 15 秒的跳过；`memo_subagents: false` 关闭。
- **新增：可选桌面通知** — 插件选项 `notifications`（默认关）：会话等待输入、需要授权或后台代理完成时弹通知，附带该会话的任务。

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
