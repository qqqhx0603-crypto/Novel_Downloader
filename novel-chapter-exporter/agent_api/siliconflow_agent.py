"""SiliconFlow Chat Completions client for the novel downloader agent.

This module is API-only. It sends message/tool schemas to SiliconFlow and
returns raw assistant messages. Local tool execution lives outside this module.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_KEY_FILE = PROJECT_ROOT / "secrets" / "API.txt"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Pro"
AVAILABLE_MODELS = (
    "deepseek-ai/DeepSeek-V4-Pro",
    "zai-org/GLM-5.2",
)
DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1/chat/completions"
MAX_THINKING_BUDGET = 32768


def read_api_key(path: Path = DEFAULT_API_KEY_FILE) -> str:
    if not path.exists():
        raise RuntimeError(f"API 密钥文件不存在: {path}")
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        raise RuntimeError(f"API 密钥文件为空: {path}")
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if "=" in first_line:
        first_line = first_line.split("=", 1)[1].strip().strip('"').strip("'")
    if first_line.lower().startswith("bearer "):
        first_line = first_line[7:].strip()
    if not first_line:
        raise RuntimeError(f"未能从 API 密钥文件解析密钥: {path}")
    return first_line


def _request_json(body: dict[str, Any], *, api_key: str, base_url: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"硅基流动 API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"硅基流动 API 网络错误: {exc.reason}") from exc
    return json.loads(raw)


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    api_key_file: Path = DEFAULT_API_KEY_FILE,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 90,
    enable_thinking: bool = True,
    thinking_budget: int = MAX_THINKING_BUDGET,
) -> dict[str, Any]:
    api_key = read_api_key(api_key_file)
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "top_p": 0.8,
        "max_tokens": 4096,
        "stream": False,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if enable_thinking:
        body["enable_thinking"] = True
        body["thinking_budget"] = int(thinking_budget)
    data = _request_json(body, api_key=api_key, base_url=base_url, timeout=timeout)
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("硅基流动 API 返回结构不符合预期。") from exc
    if not isinstance(message, dict):
        raise RuntimeError("硅基流动 API message 不是对象。")
    return message
