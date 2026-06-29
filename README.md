# Novel Downloader

本项目是一个本地小说文本下载器，支持 GUI 面板、命令行脚本和工具型 AI 下载流程。当前主要功能位于 `novel-chapter-exporter/`。

> 请在遵守版权、网站条款和当地法律的前提下使用。本项目只保存文本内容，不下载或执行网页中的程序文件。

## 主要能力

- 支持起点书籍/章节链接导出为本地 TXT。
- 起点章节付费或锁定时，可回退到已验证的免费文本源抓取正文。
- 支持每章一个 TXT、按 N 章分卷、全文合并等输出形式。
- 提供固定尺寸 Tkinter GUI 面板，缓存上次表单和窗口位置。
- 接入硅基流动 Chat Completions API，可使用 `deepseek-ai/DeepSeek-V4-Pro` 和 `zai-org/GLM-5.2`。
- AI 会按“检索源 -> 验源 -> 下载 -> 检查结果 -> 必要时续抓/换源”的循环执行，不把计划当结果。
- 支持 AI 引导入口：可在原自由描述框里补充新指令，让 AI 结合先前日志继续处理。
- 下载日志支持复制和自动保存，最多保留 20 份历史日志。

## 安全边界

- GUI/API 层和本地下载执行层分离，只通过 JSON 参数交换数据。
- API key 放在 `novel-chapter-exporter/secrets/API.txt`，不会提交到仓库；仓库只保留 `API.example.txt`。
- 小说网页抓取强制本地直连，不读取系统代理；HTTP 重定向每一跳都会重新校验公网 URL，拒绝跳转到 localhost、内网和 link-local。
- AI 只能读取项目工作区和本次小说输出目录，也就是 `保存位置/小说名`，不能读取整个桌面或保存位置父目录。
- AI 不能执行模型生成的 Python、PowerShell、cmd 或系统脚本。
- 受限命令只允许安全参数的 `rg`，拒绝 `--pre`、`--pre-glob`、`--search-zip`、`--hidden`、`--no-ignore`、`-u` 等危险参数。
- AI 可写入和运行声明式 `.agent.json`，但由程序解释执行，只支持受控操作：`list_dir`、`read_text`、`search_text`、`parse_json`、`regex_extract`、`count_chapter_files`、`write_memory`。
- AI 新增小说源只能提交结构化 JSON 配置，不能写 provider 代码；配置源注册前会再次验源。
- 配置化源正则包含 ReDoS 静态拦截，拒绝明显高风险嵌套无界量词和反向引用。

## 快速启动

双击项目根目录的启动入口：

```text
启动智能下载器.vbs
```

或进入子目录手动启动：

```powershell
cd D:\chatgpt\Tools\Novel_Downloader\novel-chapter-exporter
python -B gui\smart_downloader_gui.py
```

首次使用 API 面板前，复制示例文件并填入硅基流动 API key：

```powershell
cd D:\chatgpt\Tools\Novel_Downloader\novel-chapter-exporter
copy secrets\API.example.txt secrets\API.txt
notepad secrets\API.txt
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

## 目录结构

```text
Novel_Downloader/
  README.md
  启动智能下载器.vbs
  novel-chapter-exporter/
    README.md
    agent_api/                 # 硅基流动 API 调用层
    executor/                  # 本地工具执行层
    gui/                       # Tkinter 面板
    scripts/qidian_export.py   # 命令行下载脚本
    config/free_sources.json   # 配置化免费源
    secrets/API.example.txt    # API key 示例文件
    memory/                    # 项目记忆和设计记录
```

## 详细文档

更多命令行参数、源配置、AI 工具流程和 GUI 行为见：

- `novel-chapter-exporter/README.md`
- `novel-chapter-exporter/memory/agent_gui_design.md`
