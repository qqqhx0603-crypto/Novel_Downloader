---
name: qidian-export
description: 将起点章节导出为本地 TXT，支持付费章节自动回退到免费网站文本源（1qxs、fxnzw、bqg2）。
---

# 起点章节导出

## 使用场景
- 用户提供起点书籍或章节链接，需要批量导出文本。
- 用户希望遇到付费章节时自动去免费网站抓取同章节文本。

## 工作流程
1. 识别输入链接（章节或书籍）。
2. 运行脚本导出（默认开启免费源回退）。
3. 在 `output/` 或用户指定目录读取导出的 TXT 文件。

## 命令示例
- 单章导出：
  ```powershell
  python scripts/qidian_export.py chapter --chapter-url "https://www.qidian.com/chapter/1015504449/469165658/"
  ```
- 整本导出（前 20 章 + 合并）：
  ```powershell
  python scripts/qidian_export.py book --book-url "https://www.qidian.com/book/1015504449/" --max-chapters 20 --merge
  ```
- 关闭免费网站回退：
  ```powershell
  python scripts/qidian_export.py book --book-url "https://www.qidian.com/book/1015504449/" --no-fallback-free
  ```

## 关键参数
- `--fallback-sources`：回退站点列表，默认使用内置源和 `config/free_sources.json` 中 `default=true` 的配置源（顺序即尝试顺序）。
- `--fallback-min-chars`：回退正文最小字符数，过短则丢弃。
- `--save-locked`：锁章时输出占位文件（默认不输出）。
- `--merge`：生成整本合并 TXT。

## 安全约束
- 仅抓取文本页面（`text/html` / `xhtml` / `text/plain`）。
- 自动拦截 `exe/apk/zip` 等非文本下载类型，避免误下载程序文件。
