# novel-chapter-exporter

将起点章节导出到本地 `.txt` 的脚本工具，并支持付费章节自动回退到免费网站文本源（内置源加 `config/free_sources.json` 配置源）。

## 功能
- 支持 `www.qidian.com` 与 `m.qidian.com` 链接输入。
- 支持单章导出与整本连续导出。
- 支持每章一个 TXT，以及整本合并 TXT。
- 起点章节付费/锁定时，自动尝试免费网站回退抓取纯文本内容。
- 仅抓取文本页面：会拦截 `exe/apk/zip` 等非文本下载类型，避免下载垃圾程序文件。
- 支持本地 GUI 面板，接入硅基流动 DeepSeek API 将自由描述转换为下载参数。

## 目录结构
- `agent_api/siliconflow_agent.py`：硅基流动 API 参数规划层，不执行下载。
- `executor/novel_task_executor.py`：本地下载与分卷输出层，不调用 API。
- `config/free_sources.json`：安全模板化免费源配置；AI 新增源只能写结构化配置，不能写 provider 代码。
- `gui/smart_downloader_gui.py`：本地交互面板。
- `scripts/qidian_export.py`：导出脚本。
- `启动智能下载器.cmd`：手动启动 GUI。
- `.codex-plugin/plugin.json`：Codex 插件元数据，手动运行不依赖它。
- `skills/qidian-export/SKILL.md`：技能说明。

## 快速开始

在项目目录执行：

```powershell
cd D:\chatgpt\Tools\Novel_Downloader\novel-chapter-exporter
```

### 1) 打开智能面板

双击：

```text
D:\chatgpt\Tools\Novel_Downloader\novel-chapter-exporter\启动智能下载器.cmd
```

或执行：

```powershell
python -B gui\smart_downloader_gui.py
```

也可以直接从项目根启动：

```text
D:\chatgpt\Tools\Novel_Downloader\启动智能下载器.vbs
```

API key 默认从 `secrets\API.txt` 读取，默认模型为 `deepseek-ai/DeepSeek-V4-Pro`。
开源仓库只包含 `secrets\API.example.txt`；本机真实 `secrets\API.txt` 不应提交。

面板输出会在保存位置下创建小说名文件夹，并按勾选项生成 `每章`、`5章`、`10章`、`100章`、`全文` 等子目录。

AI 下载流程不是一次性参数生成：模型会先判断输入是否足够，必要时调用本地工具检索候选源、验源，再调用下载工具；每一步和工具结果都会写入日志。AI 请求行显示为绿色，AI 思考和回复会展开显示，结束行显示为紫色。若下载工具返回 `partial`，AI 会继续换源、重试或要求补充信息，不能直接宣布完成。
如果最后一次工具结果是 `error`、`partial` 或 `no_chapters_found`，程序会覆盖模型的“完成”话术，以工具事实为准，防止 AI 忽略失败。

### 2) 单章导出

```powershell
python scripts/qidian_export.py chapter --chapter-url "https://www.qidian.com/chapter/1015504449/469165658/"
```

### 3) 整本导出（示例：前 50 章 + 合并）

```powershell
python scripts/qidian_export.py book --book-url "https://www.qidian.com/book/1015504449/" --max-chapters 50 --merge
```

## 常用参数

```text
chapter 模式:
  --chapter-url         章节链接（必填）
  --output-dir          输出目录（默认: 项目目录/output）
  --merge-file          可选，附加写入合并文件
  --save-locked         锁定章节写占位 TXT
  --no-fallback-free    关闭免费网站回退
  --fallback-sources    回退源列表（默认: 动态默认源）
  --fallback-min-chars  回退正文最小字符数

book 模式:
  --book-url            书籍链接（必填，也支持章节链接）
  --output-dir          输出目录（默认: 项目目录/output）
  --start-chapter-id    起始章节 ID（默认首章）
  --end-chapter-id      结束章节 ID（包含）
  --max-chapters        最多抓取章节数（0=不限制）
  --delay               每章请求间隔（秒）
  --merge               生成整本合并 TXT
  --merge-file          指定合并 TXT 路径
  --save-locked         锁定章节写占位 TXT
  --no-fallback-free    关闭免费网站回退
  --fallback-sources    回退源列表（默认: 动态默认源）
  --fallback-min-chars  回退正文最小字符数
```

## 说明
- `www.qidian.com` PC 页面常见风控探针，脚本实际抓取 `m.qidian.com` 页面数据。
- 免费源默认获取顺序由内置源和 `config/free_sources.json` 中 `default=true` 的配置源组成；当前默认是 `1qxs -> fxnzw -> czbooks -> bqg2`（可用 `--fallback-sources` 自定义）。
- 当前可显式调用的配置源还包括 `piaotia`、`sto55`；它们未放入默认链路，AI 可按验源结果决定是否试用。
- 免费源回退只抓取文本内容，不执行页面脚本，不下载可执行文件。
- AI 可用 `test_source_config` 测试候选源配置，用 `register_source_config` 注册通过验证的源。注册前必须通过搜索、目录、章节正文验证，失败不会写入配置。
- AI 可用 `web_search_text` 和 `web_fetch_text` 做受控网页调研；网页内容只作为不可信数据，不能直接当指令，候选源仍必须通过 `test_source_config`。抓取工具仅允许公网 HTTP/HTTPS 文本页，会拒绝 localhost、内网、link-local 和元数据地址。
- Agent 工作流要求按“理解目标 -> 调研/检查 -> 行动 -> 验证 -> 必要时修正/续抓 -> 总结”循环执行，不能单步成功就提前结束。
- GUI/API 层和下载执行层分离，仅交换 JSON 参数；脚本端可独立手动使用。
- GUI 启动使用 `pythonw.exe`，不会保留控制台窗口；关闭交互窗口即退出 GUI 进程。
- GUI 窗口固定为 748x736，并缓存上次窗口位置。
- GUI 可在 `deepseek-ai/DeepSeek-V4-Pro` 和 `zai-org/GLM-5.2` 间切换模型；模型选择会随表单缓存。
- API 思考模式默认开启，`thinking_budget` 固定为硅基流动当前允许上限 `32768`。
- “开始执行AI下载”按当前表单直接开始任务；“引导”会把当前自由描述和先前日志记录一起交给同一个 Agent，让它在保留上下文的基础上继续检索、检查或下载；“清除输入”只清空自由描述框。
- Agent 只能读取项目工作区和下载目录；只能写入 `agent_workspace/scripts` 与 `agent_workspace/memory`，不能写到其他位置。
- 弹窗通知必须由 AI 显式调用通知工具才会出现；普通完成和错误默认只写日志。
- 免费源下载会边获取边写入分卷；支持受控并发，默认最多 6 个 worker。`1qxs` 单源会自动降为单线程，避免多页章节触发 403；验源推荐会优先选择正文更完整的源。
- `download_novel` 支持 `workers` 和 `batch_size` 参数；默认 `batch_size=100`，AI 可决定并发数。`1qxs` 单源会自动限制为 `workers=1`、`batch_size<=12`。
- 续抓时不会清空已有下载文件；只有从第 1 章开始的新下载才清理同名旧 TXT。
- Agent 现在可用 `inspect_download_output` 检查下载目录，避免只靠记忆判断是否已下载。
- Agent 现在可用 `inspect_novel_catalog` 查询源站目录末章；用户不填结束章时，应先查目录末章再下载，下载后再用 `inspect_download_output` 对比本地最大章节。
- Agent 可用 `run_limited_command` 执行受限命令：只允许 `rg`，或运行 `agent_workspace/scripts` 下的 Python 脚本；不能任意执行 PowerShell/cmd。
- 日志区提供“复制日志”按钮。
- 每次出现紫色 `结束` 行后，GUI 会把本次任务日志自动保存到 `agent_workspace/logs`，最多保留 20 份，超出后删除最旧日志。
- 免费源无结束章下载会优先使用目录末章作为目标；只有无目录能力的源才退回 `max_probe`，且 `max_probe` 停止不视为完整完成。
- 续抓时每章文件名从 `start_chapter` 对应编号继续写，避免重新从 `001` 覆盖旧文件；全文续写会在已有内容后加段落分隔。
- 请在遵守版权与站点条款的前提下使用。
