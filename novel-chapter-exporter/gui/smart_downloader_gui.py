"""Tkinter GUI for the local intelligent novel downloader."""

from __future__ import annotations

import json
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, IntVar, StringVar, Text, Tk, filedialog, messagebox, ttk

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_api.siliconflow_agent import AVAILABLE_MODELS, DEFAULT_MODEL  # noqa: E402
from executor.agent_runtime import run_agent  # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "gui" / "last_form.json"
LOG_DIR = PROJECT_ROOT / "agent_workspace" / "logs"
DEFAULT_OUTPUT = r"D:\Desktop"
WINDOW_WIDTH = 748
WINDOW_HEIGHT = 736
SCROLL_SEGMENT_LINES = 14
MAX_SAVED_LOGS = 20


class NovelDownloaderApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("智能小说下载器")
        self.root.resizable(False, False)
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.free_text: Text | None = None
        self.novel_name = StringVar()
        self.author = StringVar()
        self.start_chapter = StringVar(value="")
        self.end_chapter = StringVar(value="")
        self.output_dir = StringVar(value=DEFAULT_OUTPUT)
        self.model_id = StringVar(value=DEFAULT_MODEL)
        self.each_enabled = BooleanVar(value=True)
        self.five_enabled = BooleanVar(value=False)
        self.ten_enabled = BooleanVar(value=True)
        self.hundred_enabled = BooleanVar(value=True)
        self.full_enabled = BooleanVar(value=False)
        self.five_value = IntVar(value=5)
        self.ten_value = IntVar(value=10)
        self.hundred_value = IntVar(value=100)
        self.running = False
        self.task_log_start = "1.0"
        self.guide_button: ttk.Button | None = None

        self._build_ui()
        self._load_config()
        self._apply_geometry()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_queue()

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.configure(
            "Accent.TButton",
            font=("Microsoft YaHei UI", 10, "bold"),
            padding=(14, 5),
            foreground="#0b3d2e",
        )
        style.configure("Compact.TButton", padding=(8, 2))

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        form = ttk.LabelFrame(outer, text="基础信息", padding=10)
        form.pack(fill="x")
        form.columnconfigure(0, minsize=64, weight=0)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(2, minsize=176, weight=0)
        form.columnconfigure(3, weight=1)

        ttk.Label(form, text="小说名").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.novel_name).grid(row=0, column=1, sticky="ew", padx=(2, 12))
        ttk.Label(form, text="起始正文章（空=从第一章开始）").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.start_chapter).grid(row=0, column=3, sticky="ew", padx=(2, 0))

        ttk.Label(form, text="作者").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(form, textvariable=self.author).grid(row=1, column=1, sticky="ew", padx=(2, 12), pady=(8, 0))
        ttk.Label(form, text="结束正文章（空=尽量到最后）").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(form, textvariable=self.end_chapter).grid(row=1, column=3, sticky="ew", padx=(2, 0), pady=(8, 0))

        chunks = ttk.LabelFrame(outer, text="输出版本", padding=10)
        chunks.pack(fill="x", pady=8)
        ttk.Checkbutton(chunks, text="每章一个 TXT", variable=self.each_enabled).grid(row=0, column=0, sticky="w", padx=6)
        ttk.Checkbutton(chunks, text="按 N 章：", variable=self.five_enabled).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Entry(chunks, textvariable=self.five_value, width=6).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(chunks, text="按 N 章：", variable=self.ten_enabled).grid(row=0, column=3, sticky="w", padx=6)
        ttk.Entry(chunks, textvariable=self.ten_value, width=6).grid(row=0, column=4, sticky="w")
        ttk.Checkbutton(chunks, text="按 N 章：", variable=self.hundred_enabled).grid(row=0, column=5, sticky="w", padx=6)
        ttk.Entry(chunks, textvariable=self.hundred_value, width=6).grid(row=0, column=6, sticky="w")
        ttk.Checkbutton(chunks, text="全文合并", variable=self.full_enabled).grid(row=0, column=7, sticky="w", padx=6)

        dest = ttk.LabelFrame(outer, text="保存位置", padding=10)
        dest.pack(fill="x")
        for col in range(12):
            dest.columnconfigure(col, weight=1)
        ttk.Entry(dest, textvariable=self.output_dir).grid(row=0, column=0, columnspan=7, sticky="ew", padx=(0, 8))
        ttk.Button(dest, text="选择文件夹", command=self._choose_output_dir).grid(row=0, column=7, columnspan=2, sticky="ew", padx=(0, 18))
        self.start_button = ttk.Button(dest, text="开始执行AI下载", style="Accent.TButton", command=self._run_agent_download)
        self.start_button.grid(row=0, column=9, columnspan=3, sticky="ew")

        free_area = ttk.Frame(outer)
        free_area.pack(fill="x", pady=(4, 8))
        free_left = ttk.Frame(free_area)
        free_left.pack(side="left", fill="both", expand=True)
        ttk.Label(free_left, text="补充给 AI 的自由描述（可空）").pack(anchor="w")
        free_frame = ttk.Frame(free_left, height=110)
        free_frame.pack(fill="x", pady=(4, 0))
        free_frame.pack_propagate(False)
        self.free_text = Text(free_frame, height=5, wrap="word")
        self.free_text.pack(fill="both", expand=True)

        model_panel = ttk.Frame(free_area, width=176)
        model_panel.pack(side="right", fill="y", padx=(10, 0))
        model_panel.pack_propagate(False)
        ttk.Label(model_panel, text="模型").pack(anchor="w")
        self.model_combo = ttk.Combobox(
            model_panel,
            textvariable=self.model_id,
            values=list(AVAILABLE_MODELS),
            state="readonly",
            width=22,
        )
        self.model_combo.pack(fill="x", pady=(2, 0))
        ttk.Label(model_panel, text="思考预算：32768").pack(anchor="w", pady=(4, 0))
        self.guide_button = ttk.Button(model_panel, text="引导", style="Compact.TButton", command=self._run_guided_agent)
        self.guide_button.pack(fill="x", pady=(4, 0))
        ttk.Button(model_panel, text="清除输入", style="Compact.TButton", command=self._clear_free_input).pack(fill="x", pady=(3, 0))

        log_header = ttk.Frame(outer)
        log_header.pack(fill="x")
        ttk.Label(log_header, text="日志").pack(side="left")
        ttk.Button(log_header, text="复制日志", command=self._copy_log).pack(side="right")
        log_frame = ttk.Frame(outer)
        log_frame.pack(fill="both", expand=True)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = Text(log_frame, height=24, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.tag_configure("ai_request", foreground="#138a36")
        self.log_text.tag_configure("end_line", foreground="#7d2cff")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        nav = ttk.Frame(log_frame)
        nav.grid(row=0, column=2, sticky="ns", padx=(6, 0))
        ttk.Button(nav, text="上翻", width=6, command=lambda: self._scroll_log(-SCROLL_SEGMENT_LINES)).pack(fill="x", pady=(0, 6))
        ttk.Button(nav, text="下翻", width=6, command=lambda: self._scroll_log(SCROLL_SEGMENT_LINES)).pack(fill="x")

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir.get() or DEFAULT_OUTPUT)
        if selected:
            self.output_dir.set(selected)
            self._save_config()

    def _log(self, message: str) -> None:
        at_end = self.log_text.yview()[1] >= 0.999
        text = message.rstrip()
        tag = None
        if text.startswith("[[AI_REQUEST]]"):
            text = text.removeprefix("[[AI_REQUEST]]")
            tag = "ai_request"
        elif text.startswith("[[END]]"):
            text = text.removeprefix("[[END]]")
            tag = "end_line"
        if tag:
            self.log_text.insert("end", text + "\n", tag)
        else:
            self.log_text.insert("end", text + "\n")
        if tag == "end_line":
            self._save_log_snapshot()
        if at_end:
            self.log_text.see("end")

    def _scroll_log(self, lines: int) -> None:
        self.log_text.yview_scroll(lines, "units")

    def _copy_log(self) -> None:
        text = self.log_text.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._log("日志已复制到剪贴板。")

    def _clear_free_input(self) -> None:
        if self.free_text:
            self.free_text.delete("1.0", "end")
        self._save_config()

    def _safe_log_stem(self, value: str) -> str:
        cleaned = "".join("_" if char in '<>:"/\\|?*' else char for char in value.strip())
        cleaned = cleaned.strip(" .")
        return cleaned[:60] or "未命名小说"

    def _save_log_snapshot(self) -> None:
        text = self.log_text.get(self.task_log_start, "end-1c").lstrip("\n")
        if not text.strip():
            return
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        novel = self._safe_log_stem(self.novel_name.get() or "未命名小说")
        log_path = LOG_DIR / f"{timestamp}_{novel}.log.txt"
        log_path.write_text(text, encoding="utf-8")

        logs = sorted(
            LOG_DIR.glob("*.log.txt"),
            key=lambda path: (path.stat().st_mtime, path.name),
        )
        for old_log in logs[:-MAX_SAVED_LOGS]:
            try:
                old_log.unlink()
            except OSError:
                pass

    def _safe_int(self, value: object, default: int | None) -> int | None:
        try:
            text = str(value).strip()
            if text == "":
                return default
            return int(text)
        except (TypeError, ValueError):
            return default

    def _chunk_sizes(self) -> list[int]:
        chunks: list[int] = []
        if self.each_enabled.get():
            chunks.append(1)
        for enabled, value_var in (
            (self.five_enabled, self.five_value),
            (self.ten_enabled, self.ten_value),
            (self.hundred_enabled, self.hundred_value),
        ):
            if enabled.get():
                value = self._safe_int(value_var.get(), None)
                if value and value > 0 and value not in chunks:
                    chunks.append(value)
        if self.full_enabled.get():
            chunks.append(0)
        return chunks or [10]

    def _form_state(self) -> dict:
        return {
            "free_description": self.free_text.get("1.0", "end").strip() if self.free_text else "",
            "novel_name": self.novel_name.get().strip(),
            "author": self.author.get().strip(),
            "start_chapter": self._safe_int(self.start_chapter.get(), 1) or 1,
            "end_chapter": self._safe_int(self.end_chapter.get(), None),
            "chunk_sizes": self._chunk_sizes(),
            "output_dir": self.output_dir.get().strip() or DEFAULT_OUTPUT,
            "model_id": self.model_id.get().strip() or DEFAULT_MODEL,
            "source_names": "",
        }

    def _prior_records(self) -> str:
        text = self.log_text.get("1.0", "end-1c").strip()
        if len(text) > 12000:
            text = text[-12000:]
        return text

    def _apply_geometry(self) -> None:
        data = self._read_config()
        x = data.get("window_x")
        y = data.get("window_y")
        if isinstance(x, int) and isinstance(y, int):
            self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")
        else:
            self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

    def _read_config(self) -> dict:
        if not CONFIG_PATH.exists():
            return {}
        try:
            value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _load_config(self) -> None:
        data = self._read_config()
        self.novel_name.set(str(data.get("novel_name") or ""))
        self.author.set(str(data.get("author") or ""))
        self.start_chapter.set(str(data.get("start_chapter") or ""))
        self.end_chapter.set(str(data.get("end_chapter") or ""))
        self.output_dir.set(str(data.get("output_dir") or DEFAULT_OUTPUT))
        model = str(data.get("model_id") or DEFAULT_MODEL)
        self.model_id.set(model if model in AVAILABLE_MODELS else DEFAULT_MODEL)
        if data.get("free_description") and self.free_text:
            self.free_text.delete("1.0", "end")
            self.free_text.insert("1.0", str(data.get("free_description")))
        chunks = [int(x) for x in data.get("chunk_sizes") or [1, 10, 100] if str(x).lstrip("-").isdigit()]
        self.each_enabled.set(1 in chunks)
        self.full_enabled.set(0 in chunks)
        positives = [x for x in chunks if x > 1]
        self.five_enabled.set(len(positives) >= 1)
        self.ten_enabled.set(len(positives) >= 2)
        self.hundred_enabled.set(len(positives) >= 3)
        if positives:
            self.five_value.set(positives[0])
        if len(positives) >= 2:
            self.ten_value.set(positives[1])
        if len(positives) >= 3:
            self.hundred_value.set(positives[2])

    def _save_config(self) -> None:
        data = self._form_state()
        data["window_x"] = self.root.winfo_x()
        data["window_y"] = self.root.winfo_y()
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _start_agent_task(self, *, guided: bool) -> None:
        if self.running:
            self._log("任务正在执行中，当前版本不并发启动第二个任务。")
            return
        self._save_config()
        self.running = True
        self.start_button.configure(state="disabled")
        if self.guide_button:
            self.guide_button.configure(state="disabled")
        form = self._form_state()
        if guided:
            form["interaction_mode"] = "guided_execute"
            form["prior_records"] = self._prior_records()
        else:
            form["interaction_mode"] = "direct_download"
        self.task_log_start = self.log_text.index("end-1c")

        def work() -> None:
            try:
                if guided:
                    self.queue.put(("log", "开始执行 AI 引导续做流程。"))
                else:
                    self.queue.put(("log", "开始执行 AI 下载流程。"))
                result = run_agent(form, log=lambda m: self.queue.put(("log", m)))
                self.queue.put(("result", result))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("error", str(exc)))
            finally:
                self.queue.put(("idle", ""))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _run_agent_download(self) -> None:
        self._start_agent_task(guided=False)

    def _run_guided_agent(self) -> None:
        self._start_agent_task(guided=True)

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._log(str(payload))
                elif kind == "error":
                    self._log("错误: " + str(payload))
                elif kind == "result":
                    result = payload if isinstance(payload, dict) else {"message": str(payload)}
                    for notice in result.get("ui_notifications") or []:
                        message = str(notice.get("message") or "")
                        level = str(notice.get("level") or "info")
                        if not message:
                            continue
                        if level == "error":
                            messagebox.showerror("AI 通知", message)
                        elif level == "warning":
                            messagebox.showwarning("AI 通知", message)
                        else:
                            messagebox.showinfo("AI 通知", message)
                elif kind == "idle":
                    self.running = False
                    self.start_button.configure(state="normal")
                    if self.guide_button:
                        self.guide_button.configure(state="normal")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _on_close(self) -> None:
        self._save_config()
        self.root.destroy()


def main() -> None:
    root = Tk()
    NovelDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
