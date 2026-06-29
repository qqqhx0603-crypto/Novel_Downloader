# novel-chapter-exporter

`novel-chapter-exporter` 是 Novel Downloader 的核心模块，包含命令行下载脚本、Tkinter GUI、硅基流动 API 调用层和本地 AI 工具执行层。

> 请在遵守版权、网站条款和当地法律的前提下使用。本模块只保存文本内容，不下载或执行网页中的程序文件。

## 功能

- 支持 `www.qidian.com` 和 `m.qidian.com` 书籍/章节链接。
- 支持单章导出、整本连续导出、每章一个 TXT、按 N 章分卷和全文合并。
- 起点章节付费或锁定时，可自动尝试免费文本源回退。
- 免费源只抓取普通文本页面，不执行网页脚本，不下载可执行文件。
- GUI 面板支持小说名、作者、章节范围、输出版本、保存位置、模型选择和自由描述。
- AI 下载流程不是一次性参数生成，而是工具型 Agent 循环：检索、验源、下载、检查、续抓或总结。
- “引导”入口会结合已有日志和新自由描述继续处理，不等同于重新开始。
- 日志支持复制和自动保存，最多保留 20 份。

## 目录结构

```text
novel-chapter-exporter/
  agent_api/siliconflow_agent.py     # 硅基流动 Chat Completions 客户端
  executor/agent_runtime.py          # Agent 循环和工具分发
  executor/novel_task_executor.py    # 本地下载、验源、分卷和安全工具实现
  gui/smart_downloader_gui.py        # Tkinter GUI
  scripts/qidian_export.py           # 命令行导出脚本
  config/free_sources.json           # 配置化免费源
  secrets/API.example.txt            # API key 示例文件
  memory/agent_gui_design.md         # 设计记录
  启动智能下载器.cmd
  启动智能下载器.vbs
```

`.codex-plugin/` 和 `skills/` 仅用于 Codex 辅助识别项目能力；手动运行 GUI 或命令行脚本不依赖它们。

## API 配置

AI 面板默认从 `secrets/API.txt` 读取硅基流动 API key。仓库只保留示例文件：

```powershell
copy secrets\API.example.txt secrets\API.txt
notepad secrets\API.txt
```

`API.txt` 可以只写密钥本身，也可以写成：

```text
API_KEY=你的硅基流动 API key
```

当前模型列表：

- `deepseek-ai/DeepSeek-V4-Pro`
- `zai-org/GLM-5.2`

请求默认开启思考模式，`thinking_budget=32768`。

## 启动 GUI

在本目录执行：

```powershell
python -B gui\smart_downloader_gui.py
```

也可以双击：

```text
启动智能下载器.cmd
启动智能下载器.vbs
```

GUI 会缓存上次填写内容和窗口位置。下载结果会写入 `保存位置/小说名`，并按勾选项生成 `每章`、`5章`、`10章`、`100章`、`全文` 等子目录。

## GUI 下载逻辑

1. 用户填写小说名、作者、起止章节、保存位置和输出版本。
2. 可在自由描述中补充自然语言要求。
3. AI 判断信息是否足够。
4. 信息不足时，AI 可以先调用搜索/验源工具，再决定是否询问用户。
5. 信息足够时，AI 调用下载工具。
6. 下载后 AI 调用检查工具核对输出目录、章节范围和报告。
7. 如果工具返回 `partial`、`error`、`no_chapters_found`、`not_found` 或 `invalid`，AI 不能直接宣布完成，必须继续处理或明确说明缺口。
8. 弹窗通知必须由 AI 显式调用通知工具才会出现，普通完成和错误默认只写日志。

## 命令行用法

### 单章导出

```powershell
python scripts\qidian_export.py chapter --chapter-url "https://www.qidian.com/chapter/1015504449/469165658/"
```

常用参数：

```text
--chapter-url         章节链接，必填
--output-dir          输出目录，默认 scripts/output
--merge-file          可选，同时附加写入合并文件
--save-locked         锁定章节写占位 TXT
--no-fallback-free    关闭免费源回退
--fallback-sources    回退源列表
--fallback-min-chars  回退正文最小字符数
```

### 整本导出

```powershell
python scripts\qidian_export.py book --book-url "https://www.qidian.com/book/1015504449/" --max-chapters 50 --merge
```

常用参数：

```text
--book-url            书籍链接，必填，也支持章节链接
--output-dir          输出目录，默认 scripts/output
--start-chapter-id    起始章节 ID，默认自动使用首章
--end-chapter-id      结束章节 ID，包含该章节
--max-chapters        最多抓取章节数，0 表示不限制
--delay               每章请求间隔，秒
--merge               生成整本合并 TXT
--merge-file          指定合并 TXT 路径
--save-locked         锁定章节写占位 TXT
--no-fallback-free    关闭免费源回退
--fallback-sources    回退源列表
--fallback-min-chars  回退正文最小字符数
```

## 免费源

默认免费源顺序由内置源和 `config/free_sources.json` 中 `default=true` 的配置源组成。当前默认链路：

```text
1qxs -> fxnzw -> czbooks -> bqg2
```

可显式调用但不默认启用的配置源包括：

```text
piaotia, sto55
```

AI 可以通过工具测试和注册新的配置化源，但只能写结构化 JSON 配置，不能写 Python provider 代码。注册前必须通过搜索、目录和章节正文验证。

## 安全边界

- GUI/API 层和下载执行层分离，只交换 JSON 参数。
- 小说网页抓取强制本地直连，不读取系统代理。
- 抓取工具仅允许公网 HTTP/HTTPS 文本页，拒绝 localhost、内网、link-local、元数据地址和常见压缩/可执行下载后缀。
- HTTP 重定向每一跳都会重新校验目标 URL。
- AI 只能读取项目工作区和本次小说输出目录，不能读取整个保存位置。
- AI 只能写入 `agent_workspace/memory` 和声明式 `.agent.json`。
- AI 不能执行模型生成的 Python、PowerShell、cmd 或系统脚本。
- `run_limited_command` 只允许安全参数的 `rg`，拒绝 `--pre`、`--pre-glob`、`--search-zip`、`--hidden`、`--no-ignore`、`-u` 等危险参数。
- 声明式 `.agent.json` 只支持受控操作：`list_dir`、`read_text`、`search_text`、`parse_json`、`regex_extract`、`count_chapter_files`、`write_memory`。
- 配置化源正则会进行 ReDoS 静态拦截，拒绝明显高风险嵌套无界量词和反向引用。

## 输出和续抓

- 免费源下载会边获取边写入分卷，避免长任务结束前没有文件产物。
- `download_novel` 支持 `workers` 和 `batch_size`；默认 `batch_size=100`，AI 可决定并发数。
- `1qxs` 单源会自动限制为 `workers=1`、`batch_size<=12`，避免多页章节触发 403。
- 续抓不会清空已有下载文件；只有从第 1 章开始的新下载才清理同名旧 TXT。
- 续抓时每章文件名从 `start_chapter` 对应编号继续写，全文续写会在已有内容后追加段落分隔。
- 免费源无结束章下载会优先使用目录末章作为目标；无目录能力的源才退回 `max_probe`。
