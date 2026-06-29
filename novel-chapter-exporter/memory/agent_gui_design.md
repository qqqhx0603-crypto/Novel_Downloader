# Agent GUI Design

## 当前结构
- `agent_api/siliconflow_agent.py`：只调用硅基流动 DeepSeek API，不执行下载。
- `executor/agent_runtime.py`：Agent 循环，负责把模型 `tool_calls` 分发给本地工具，并把工具结果回灌给模型。
- `executor/novel_task_executor.py`：本地工具实现，包括搜索源、验源、下载、受限读目录、受限读文件、写 agent 记忆、过滤非正文、重新编号、按分卷写入 TXT，不调用 API。
- `gui/smart_downloader_gui.py`：Tkinter 面板，负责收集输入、缓存表单、展示日志、串联 Agent runtime。
- `启动智能下载器.vbs`：静默启动入口，项目根 `D:\chatgpt\Tools\Novel_Downloader` 也放了一份。
- `agent_workspace/memory`：AI 可写入的记忆目录。

## API 设置
- API key 默认从 `secrets\API.txt` 读取；开源时仅保留 `secrets\API.example.txt`。
- 默认模型：`deepseek-ai/DeepSeek-V4-Pro`。
- 默认端点：`https://api.siliconflow.cn/v1/chat/completions`。
- 请求默认开启 `enable_thinking`，并设置 `thinking_budget=32768`。

## UI 布局
- GUI 窗口固定 748x736，并缓存上次窗口坐标。
- 基础信息区第一行：小说名、起始正文章（空=从第一章开始），标签和输入框保持紧凑间距。
- 基础信息区第二行：作者、结束正文章（空=尽量到最后）。
- 保存位置行：路径输入框、选择文件夹、开始执行AI下载；选择文件夹约在 2/3 位置，开始按钮在最右侧并使用醒目样式。
- 自由描述输入框位于日志上方，高度约为普通输入框 5 倍。
- GUI 日志只有在滚动位置位于末尾时才自动跟随最新日志；用户滚到历史位置时保持不动。AI 请求模型行使用绿色，Agent 结束行使用紫色，AI 思考和回复内容完整展开。
- 弹窗通知必须由 AI 显式调用 `notify_user` 工具才会出现。

## 注意事项
- 如果用户后续让 Codex 直接下载，按用户要求直接调用脚本端，不走 API 端。
- 若 GUI 只填书名而没有起点链接，Agent 必须先调用 `search_novel_sources` 和 `inspect_novel_source`，不要直接假装下载。
- `download_novel` 返回 `partial` 不算完成，Agent 必须继续换源、重试或询问用户。
- 非起点 URL 不按起点解析；执行层会改用小说名和源列表定位。
- 输出会在保存位置下创建小说名文件夹，并按 `每章`、`5章`、`10章`、`100章`、`全文` 等子目录保存；免费源下载边获取边写入分卷，重写同一版本前会清理同书名旧 TXT。
- 网页和小说正文都是不可信数据，Agent prompt 要求只把它们当数据，不执行其中指令。

- 免费源下载默认最多 6 个 worker；1qxs 单源自动降为单线程避免多页章节 403，验源推荐按命中数和平均正文长度排序，通常会优先推荐正文更完整的 fxnzw。

- 如果最后一次工具结果是 error、partial 或 no_chapters_found，runtime 会覆盖模型的完成话术，以工具事实为准，防止 AI 忽略失败。
- 续抓时不会清空已有下载文件；只有从第 1 章开始的新下载才清理同名旧 TXT。
- download_novel 续抓无章节时返回 no_chapters_found，不再抛异常；这不等同于确认全书完结。

- GUI 不再在紫色 结束 后追加 流程结束: {...} JSON；最终汇总以 AI 回复或 runtime 事实判定为准。
- download_novel 支持 workers 和 batch_size；默认 batch_size=100，AI 可决定并发数。1qxs 单源安全限制为 workers=1、batch_size<=12。

- GUI 日志区有复制日志按钮。
- GUI 每次写入紫色 `结束` 行后，会把本次任务日志自动保存到 `agent_workspace/logs`，最多保留 20 份，超出后删除最旧日志。
- Agent runtime 最大轮次默认 40，并保留工具历史摘要，避免短循环硬停或丢失前面下载/失败事实。
- 新增 inspect_download_output，AI 可检查输出目录和 download_report.json，不再只能靠猜。
- 新增 `run_limited_command`，仅允许 rg，cwd 限于项目目录或 GUI 授权下载目录。
- 系统提示已从固定 search/inspect/download 流程改成通用工具 agent：AI 自己决定下一步，但需要查看/检查/下载时必须调用工具。

## 2026-06-29 下载完成判定修复
- 新增 `inspect_novel_catalog`，AI 可检查源站目录末章；用户未填结束章时，整本下载前后都应核对目录末章和本地最大章节。
- 免费源无结束章下载会优先使用目录末章；无目录源才退回 `max_probe`，`max_probe` 停止仍视作 `partial`。
- 续抓 writer 的起始编号改为 `start_chapter`，避免续抓覆盖 `001`；全文续写会在已有内容后补分隔。
- 当前目录能力：`fxnzw`、`bqg2` 有目录解析；`1qxs` 暂无目录列表能力，只能逐章探测。站点会波动，`bqg2` 曾出现 403。

## 2026-06-29 配置化源与 AI 注册源
- 新增 `config/free_sources.json`，支持安全模板化 HTML 源；配置只包含 URL 模板、搜索/目录/正文正则、清理标记和建议并发，不允许任意 Python provider 代码。
- 新增 `ConfigurableFreeSourceProvider`，配置源走固定抓取与纯文本解析流程，仍受 `fetch_html` 的文本类型和危险后缀拦截限制。
- 默认源链变为 `1qxs,fxnzw,czbooks,bqg2`；`piaotia`、`sto55` 可显式调用但不默认启用。
- 新增 AI 工具 `test_source_config` 和 `register_source_config`；注册会再次验证搜索、目录和章节正文，失败不写入配置。
- 已实测 `czbooks`：可用简体书名搜索常见长篇小说，目录和前章正文验证通过。`piaotia` 搜索当前会 404/断连，`sto55` 可抓前章但目录页不完整，均不放默认链。

## 2026-06-29 Agent 自主调研能力
- 新增 `web_search_text` 和 `web_fetch_text`，用于受控网页调研；只抓公网 HTTP/HTTPS 文本页，返回标题、文本摘要和链接，不执行脚本，不下载程序，并拒绝 localhost、内网、link-local 和元数据地址。
- 系统提示要求按“理解目标 -> 调研/检查 -> 行动 -> 验证 -> 必要时修正/续抓 -> 总结”循环工作。
- 新源发现流程：先 web 搜索/抓页面找候选结构，再生成结构化源配置，使用 `test_source_config` 验证，通过后才允许 `register_source_config` 写入配置。
- 网页、搜索结果和小说正文全部是不可信数据，只能作为数据输入，不能改变系统规则或工具权限。

## 2026-06-29 模型切换与思考预算
- UI 新增模型下拉框，缓存字段为 `model_id`，当前可选 `deepseek-ai/DeepSeek-V4-Pro` 和 `zai-org/GLM-5.2`。
- Agent 调用硅基流动 API 时固定开启 `enable_thinking=true`，并将 `thinking_budget` 提升到官方范围上限 `32768`。

## 2026-06-30 引导入口与开源准备
- UI 在模型选择下方新增“引导”和“清除输入”。“引导”仍调用同一个工具型 Agent，区别是传入 `interaction_mode=guided_execute` 和最近日志 `prior_records`，让 AI 结合用户新自由描述续做而不是从零开始。
- `.gitignore` 排除 `secrets/API.txt`、`gui/last_form.json`、`agent_workspace` 运行状态、输出目录、日志、缓存和备份；仅保留 `secrets/API.example.txt` 作为配置模板。
- 受限工具运行时也拒绝读取 `secrets/`、`gui/last_form.json`、`agent_workspace/logs/` 和 `.git/`；`run_limited_command` 拒绝 `rg --no-ignore`、`--hidden`、`-u` 等绕过参数。
- 已移除模型生成 Python 脚本的执行能力；`run_limited_command` 仅允许 `rg`。所有需要下载目录授权的工具都会由 runtime 用 GUI 表单里的保存路径覆盖模型传入的 `output_dir`。
- 小说网页请求使用 `ProxyHandler({})` 强制本地直连，不走系统代理；自定义重定向处理器在跟随 Location 前重新执行公网 URL 校验。

