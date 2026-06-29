# Novel Downloader

本项目是一个本地小说文本下载器，提供命令行脚本、Windows GUI 面板和工具型 AI 下载流程。核心代码位于 `novel-chapter-exporter/`。

> 使用前请确认你有权保存相关文本内容，并遵守版权、网站条款和当地法律。本项目只抓取和保存文本，不下载或执行网页中的程序文件。

## 功能概览

- 支持起点书籍页、章节页导出为本地 `.txt`。
- 支持单章导出、整本连续导出、每章一个 TXT、按 N 章分卷和全文合并。
- 起点章节付费或锁定时，可回退到已验证的免费文本源抓取正文。
- 内置免费源和配置化免费源结合使用，默认源链可动态扩展。
- 提供 Tkinter GUI 面板，可填写小说名、作者、章节范围、分卷方式和保存位置。
- GUI 支持硅基流动 Chat Completions API，当前模型可选：
  - `deepseek-ai/DeepSeek-V4-Pro`
  - `zai-org/GLM-5.2`
- AI 会按“检索源 -> 验源 -> 下载 -> 检查结果 -> 必要时续抓/换源”的循环执行，不把计划当成结果。
- 支持“引导”入口：可以让 AI 结合先前日志继续检查、修正或续下。
- 日志支持复制和自动保存，最多保留 20 份历史日志。

## 安全设计

- GUI/API 层和本地下载执行层分离，只通过 JSON 参数交换数据。
- API key 放在本机 `novel-chapter-exporter/secrets/API.txt`，仓库只保留 `API.example.txt`。
- 小说网页抓取强制本地直连，不读取系统代理。
- HTTP 重定向每一跳都会重新校验 URL，拒绝跳转到 localhost、内网和 link-local 地址。
- AI 只能读取项目工作区和本次小说输出目录，也就是 `保存位置/小说名`，不能读取整个桌面或保存位置父目录。
- AI 不能执行模型生成的 Python、PowerShell、cmd 或系统脚本。
- 受限命令只允许安全参数的 `rg`，拒绝 `--pre`、`--pre-glob`、`--search-zip`、`--hidden`、`--no-ignore`、`-u` 等危险参数。
- AI 可写入和运行声明式 `.agent.json`，但由程序解释执行，只支持受控操作：`list_dir`、`read_text`、`search_text`、`parse_json`、`regex_extract`、`count_chapter_files`、`write_memory`。
- AI 新增小说源只能提交结构化 JSON 配置，不能写 provider 代码；配置源注册前会再次验源。
- 配置化源正则包含 ReDoS 静态拦截，拒绝明显高风险嵌套无界量词和反向引用。

## 环境要求

- Windows 10/11。
- Python 3.10+。
- Tkinter，通常随 Windows Python 安装。
- 可选：`rg`/ripgrep。AI 的受限搜索工具会使用它；没有它时普通下载脚本仍可运行。
- 如果使用 AI 面板，需要硅基流动 API key。

## 使用方式说明

本项目可以手动使用，不依赖 Codex。仓库中保留的 `.codex-plugin/` 和 `skills/` 只是给 Codex 识别项目能力的辅助元数据；普通用户可以忽略它们，直接使用 GUI 或命令行脚本。

## 快速开始

进入核心目录：

```powershell
cd novel-chapter-exporter
```

首次使用 AI 面板前，复制示例 API 文件并填入硅基流动 API key：

```powershell
copy secrets\API.example.txt secrets\API.txt
notepad secrets\API.txt
```

启动 GUI：

```powershell
python -B gui\smart_downloader_gui.py
```

Windows 下也可以双击项目根目录或核心目录中的启动脚本：

```text
启动智能下载器.vbs
novel-chapter-exporter\启动智能下载器.cmd
```

## 命令行示例

单章导出：

```powershell
python scripts\qidian_export.py chapter --chapter-url "https://www.qidian.com/chapter/1015504449/469165658/"
```

整本导出前 50 章并合并：

```powershell
python scripts\qidian_export.py book --book-url "https://www.qidian.com/book/1015504449/" --max-chapters 50 --merge
```

## 输出结构

GUI 下载会在保存位置下创建小说名文件夹，例如：

```text
保存位置/
  小说名/
    每章/
    5章/
    10章/
    100章/
    全文/
    download_report.json
```

具体生成哪些目录取决于 GUI 勾选项。

## 项目结构

```text
Novel_Downloader/
  README.md
  启动智能下载器.vbs
  novel-chapter-exporter/
    README.md
    agent_api/                 # 硅基流动 API 调用层
    executor/                  # 本地工具执行层和安全工具边界
    gui/                       # Tkinter 面板
    scripts/qidian_export.py   # 命令行下载脚本
    config/free_sources.json   # 配置化免费源
    secrets/API.example.txt    # API key 示例文件
    memory/                    # 项目设计记录
    skills/                    # Codex 技能说明，手动运行不依赖它
```

## 更多文档

- 详细使用说明：`novel-chapter-exporter/README.md`
- 设计记录：`novel-chapter-exporter/memory/agent_gui_design.md`
