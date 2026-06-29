# Novel Downloader

Novel Downloader 是一个本地小说文本下载工具。它的目标很简单：把网页小说章节整理成你本地能长期保存、能按章节或分卷阅读的 `.txt` 文件。

项目目前主要面向 Windows 使用，提供两种入口：

- 图形界面：适合日常下载，填写小说名、作者、章节范围和保存位置即可使用。
- 命令行脚本：适合明确知道起点书籍链接或章节链接时快速导出。

它还内置了一个工具型 AI 下载流程。你可以只写自然语言要求，例如“下载某本小说前 100 章，每 10 章一个 txt”，AI 会先检索来源、验证正文、调用本地下载工具，再检查结果。AI 不是直接凭空生成文件，真正下载和写文件的步骤都由本地工具执行。

> 请在遵守版权、网站条款和当地法律的前提下使用。本项目只抓取和保存文本，不下载或执行网页中的程序文件。

## 使用教程

### 1. 准备环境

需要：

- Windows 10/11。
- Python 3.10 或更高版本。
- Tkinter，通常随 Windows Python 一起安装。
- 可选：ripgrep，也就是 `rg`。AI 的受限搜索工具会用到它；普通下载脚本不强制依赖。

如果只使用命令行下载，不需要 API key。

如果使用 AI 面板，需要硅基流动 API key。

### 2. 打开项目目录

克隆或下载项目后，进入核心目录：

```powershell
cd novel-chapter-exporter
```

### 3. 配置 API key（只在使用 AI 面板时需要）

复制示例文件：

```powershell
copy secrets\API.example.txt secrets\API.txt
```

然后打开 `secrets\API.txt`，填入你的硅基流动 API key：

```powershell
notepad secrets\API.txt
```

`API.txt` 可以只写密钥本身，也可以写成：

```text
API_KEY=你的硅基流动 API key
```

仓库不会提交真实 `API.txt`。

### 4. 启动图形界面

在 `novel-chapter-exporter` 目录执行：

```powershell
python -B gui\smart_downloader_gui.py
```

Windows 下也可以双击启动脚本：

```text
启动智能下载器.vbs
novel-chapter-exporter\启动智能下载器.cmd
```

### 5. 使用 GUI 下载

在窗口中填写：

- 小说名：必填，AI 会用它检索来源。
- 作者：可选，用于辅助判断同名小说。
- 起始正文章：空或 `1` 表示从第一章开始。
- 结束正文章：空表示尽量下载到目录末章。
- 输出版本：可勾选每章一个 TXT、按 N 章分卷、全文合并。
- 保存位置：程序会在这里创建 `小说名` 文件夹。
- 自由描述：可写自然语言要求，例如“如果起点付费，就换免费源，只要正文”。

点击“开始执行AI下载”后，AI 会按工具流程执行：

1. 判断信息是否足够。
2. 检索候选来源。
3. 验证章节正文是否可用。
4. 调用本地下载工具。
5. 检查输出目录和下载报告。
6. 如有缺章、失败或只下载了部分章节，继续换源、续抓或说明缺口。

“引导”按钮用于任务进行过一次以后继续处理。你可以在自由描述里写“检查刚才有没有下完”“换个源继续”“从 201 章续下”，再点“引导”。它会带着前面的日志一起交给 AI 判断。

### 6. 查看输出文件

GUI 下载会在保存位置下创建小说名文件夹，例如：

```text
保存位置/
  小说名/
    每章/
    10章/
    100章/
    全文/
    download_report.json
```

实际生成哪些目录取决于你在 GUI 中勾选了哪些输出版本。

### 7. 使用命令行下载

单章导出：

```powershell
python scripts\qidian_export.py chapter --chapter-url "https://www.qidian.com/chapter/1015504449/469165658/"
```

整本导出前 50 章并生成合并文件：

```powershell
python scripts\qidian_export.py book --book-url "https://www.qidian.com/book/1015504449/" --max-chapters 50 --merge
```

更多参数见 `novel-chapter-exporter/README.md`。

## 支持的来源

当前支持起点页面解析，并在章节付费、锁定或正文不可用时尝试免费文本源回退。

默认免费源链路：

```text
1qxs -> fxnzw -> czbooks -> bqg2
```

可显式调用但不默认启用的配置源：

```text
piaotia, sto55
```

AI 可以通过工具测试新的免费源配置。新增源只能写结构化 JSON 配置，不能写 Python provider 代码；注册前必须通过搜索、目录和章节正文验证。

## AI 功能说明

AI 面板使用硅基流动 Chat Completions API。当前可选模型：

- `deepseek-ai/DeepSeek-V4-Pro`
- `zai-org/GLM-5.2`

AI 负责决策和调度，本地工具负责真正执行。也就是说：

- AI 可以决定先检索哪个源。
- AI 可以决定用多少并发、每批下载多少章。
- AI 可以检查下载报告和输出文件。
- AI 不能直接绕过程序权限去读整个电脑。
- AI 不能运行自己生成的 Python、PowerShell、cmd 或系统脚本。

项目保留了声明式 `.agent.json` 脚本能力。它不是系统脚本，而是由程序解释执行的受控任务，只能做列目录、读小文本、搜索文本、解析 JSON、统计章节文件、写记忆等有限操作。

## 安全边界

这个项目按本地工具边界设计，避免 AI 或网页内容拿到过大的权限：

- GUI/API 层和下载执行层分离，只通过 JSON 参数交换数据。
- API key 放在本机 `novel-chapter-exporter/secrets/API.txt`，仓库只保留 `API.example.txt`。
- 小说网页抓取强制本地直连，不读取系统代理。
- HTTP 重定向每一跳都会重新校验 URL，拒绝跳转到 localhost、内网和 link-local 地址。
- AI 只能读取项目工作区和本次小说输出目录，也就是 `保存位置/小说名`，不能读取整个桌面或保存位置父目录。
- 受限命令只允许安全参数的 `rg`，拒绝 `--pre`、`--pre-glob`、`--search-zip`、`--hidden`、`--no-ignore`、`-u` 等危险参数。
- 配置化源正则包含 ReDoS 静态拦截，拒绝明显高风险嵌套无界量词和反向引用。

## 手动使用和 Codex 说明

本项目可以手动使用，不依赖 Codex。仓库中保留的 `.codex-plugin/` 和 `skills/` 只是给 Codex 识别项目能力的辅助元数据；普通用户可以忽略它们，直接使用 GUI 或命令行脚本。

## 项目结构

```text
Novel_Downloader/
  README.md
  启动智能下载器.vbs
  novel-chapter-exporter/
    README.md
    agent_api/                 # 硅基流动 API 调用层
    executor/                  # 本地工具执行层和安全边界
    gui/                       # Tkinter 面板
    scripts/qidian_export.py   # 命令行下载脚本
    config/free_sources.json   # 配置化免费源
    secrets/API.example.txt    # API key 示例文件
    memory/                    # 项目设计记录
    skills/                    # Codex 技能说明，手动运行不依赖它
```

## 详细文档

- `novel-chapter-exporter/README.md`：命令行参数、GUI 行为、免费源和安全边界的详细说明。
- `novel-chapter-exporter/memory/agent_gui_design.md`：项目设计记录。
