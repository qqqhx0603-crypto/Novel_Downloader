#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export Qidian chapters to local TXT files with free-site fallback."""

from __future__ import annotations

import argparse
import gzip
import html
import http.client
import http.cookiejar
import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = PLUGIN_ROOT / "output"
SOURCE_CONFIG_PATH = PLUGIN_ROOT / "config" / "free_sources.json"
BUILTIN_SOURCE_NAMES = ("1qxs", "fxnzw", "bqg2")

CHAPTER_URL_RE = re.compile(r"/chapter/(\d+)/(\d+)", re.IGNORECASE)
BOOK_URL_RE = re.compile(r"/book/(\d+)", re.IGNORECASE)
ONEQXS_BOOK_PATH_RE = re.compile(r"^/xs_\d+/\d+$")
ONEQXS_BOOK_DETAIL_RE = re.compile(r"^/xs_\d+/\d+\.html$")
FXNZW_BOOK_PATH_RE = re.compile(r"^/fxnbook/(\d+)\.html$", re.IGNORECASE)
FXNZW_CHAPTER_PATH_RE = re.compile(r"^/fxnread/\d+_\d+\.html$", re.IGNORECASE)
BQG2_BOOK_PATH_RE = re.compile(r"^/html/\d+/\d+/$", re.IGNORECASE)
BQG2_CHAPTER_PATH_RE = re.compile(r"^/html/\d+/\d+/\d+\.html$", re.IGNORECASE)
ILLEGAL_FILENAME_CHARS_RE = re.compile(r"[\\/:*?\"<>|]+")
SOURCE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$", re.IGNORECASE)
TITLE_NORMALIZE_RE = re.compile(r"[\s\-—_:：·,.，。!?！？'\"“”‘’()（）\[\]【】<>《》]+")
CHAPTER_NUM_PREFIX_RE = re.compile(
    r"^第\s*([0-9零〇一二三四五六七八九十百千万两]+)\s*章"
)

CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CHINESE_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}

MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

DESKTOP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

LOCKED_MARKERS = (
    "请登录后阅读",
    "订阅后可读",
    "订阅后可阅读",
    "本章未完",
    "请下载起点读书",
)

BLOCKED_EXTENSIONS = {
    ".exe",
    ".msi",
    ".apk",
    ".dmg",
    ".pkg",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".iso",
    ".img",
    ".deb",
    ".rpm",
}

ALLOWED_CONTENT_TYPE_KEYWORDS = ("text/html", "application/xhtml+xml", "text/plain")
MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024
BLOCKED_HOST_NAMES = {"localhost", "localhost.localdomain"}


@dataclass
class BookInfo:
    book_id: int
    book_name: str
    first_chapter_id: int


@dataclass
class ChapterInfo:
    book_id: int
    book_name: str
    chapter_id: int
    chapter_name: str
    chapter_order: Optional[int]
    next_chapter_id: Optional[int]
    vip_status: int
    is_buy: int
    source_url: str
    source_site: str
    words_count: int
    text: str

    def is_locked(self) -> bool:
        if self.vip_status != 1 or self.is_buy == 1:
            return False
        if not self.text.strip():
            return True
        if any(marker in self.text for marker in LOCKED_MARKERS):
            return True

        compact_len = len(re.sub(r"\s+", "", self.text))
        if self.words_count > 0:
            # Paid chapters on Qidian often return a short preview ending with ellipsis.
            if compact_len < max(120, int(self.words_count * 0.35)):
                return True
        if self.text.rstrip().endswith(("...", "……")) and compact_len < 400:
            return True
        return False


@dataclass
class FreeChapterResult:
    text: str
    source_url: str
    source_site: str


class FreeSourceProvider:
    name = "base"

    def fetch_chapter(
        self,
        *,
        book_name: str,
        chapter_order: int,
        chapter_name: str,
        timeout: int,
    ) -> Optional[FreeChapterResult]:
        raise NotImplementedError


def normalize_title(text: str) -> str:
    return TITLE_NORMALIZE_RE.sub("", text).lower().strip()


def score_title_similarity(target: str, candidate: str) -> float:
    n_target = normalize_title(target)
    n_candidate = normalize_title(candidate)
    if not n_target or not n_candidate:
        return 0.0
    ratio = SequenceMatcher(None, n_target, n_candidate).ratio()
    if n_target == n_candidate:
        ratio += 0.5
    elif n_target in n_candidate or n_candidate in n_target:
        ratio += 0.2
    return ratio


def parse_chinese_number(text: str) -> Optional[int]:
    if not text:
        return None
    if text.isdigit():
        return int(text)

    total = 0
    section = 0
    number = 0

    for char in text:
        if char in CHINESE_DIGITS:
            number = CHINESE_DIGITS[char]
            continue
        if char not in CHINESE_UNITS:
            return None

        unit = CHINESE_UNITS[char]
        if unit == 10000:
            section = (section + number) * unit
            total += section
            section = 0
            number = 0
        else:
            if number == 0:
                number = 1
            section += number * unit
            number = 0

    return total + section + number


def chapter_number_from_title(title: str) -> Optional[int]:
    match = CHAPTER_NUM_PREFIX_RE.match(title.strip())
    if not match:
        return None
    return parse_chinese_number(match.group(1))


def pick_chapter_path(
    entries: list[tuple[str, str]],
    *,
    chapter_name: str,
    chapter_order: int,
) -> Optional[str]:
    if not entries:
        return None

    best_path = ""
    best_score = 0.0
    if chapter_name:
        for path, title in entries:
            score = score_title_similarity(chapter_name, title)
            if score > best_score:
                best_score = score
                best_path = path
        if best_path and best_score >= 0.62:
            return best_path

    for path, title in entries:
        number = chapter_number_from_title(title)
        if number is not None and number == chapter_order:
            return path

    numbered_entries = [
        (path, title) for path, title in entries if chapter_number_from_title(title) is not None
    ]
    if chapter_order > 0 and chapter_order <= len(numbered_entries):
        return numbered_entries[chapter_order - 1][0]

    return None


class OneQXSProvider(FreeSourceProvider):
    name = "1qxs"
    site = "https://m.1qxs.com"
    search_site = "https://www.1qxs.com"

    def __init__(self) -> None:
        cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar)
        )
        self._book_path_cache: dict[str, str] = {}

    @staticmethod
    def _normalize_title(text: str) -> str:
        text = re.sub(r"[\s\-—_:：·,.，。!?！？'\"“”‘’()（）\[\]【】<>《》]+", "", text)
        return text.lower().strip()

    def _score_book_title(self, target: str, candidate: str) -> float:
        n_target = self._normalize_title(target)
        n_candidate = self._normalize_title(candidate)
        if not n_target or not n_candidate:
            return 0.0
        ratio = SequenceMatcher(None, n_target, n_candidate).ratio()
        if n_target == n_candidate:
            ratio += 0.5
        elif n_target in n_candidate or n_candidate in n_target:
            ratio += 0.2
        return ratio

    def _find_book_path(self, book_name: str, timeout: int) -> Optional[str]:
        if book_name in self._book_path_cache:
            return self._book_path_cache[book_name]

        encoded_name = urllib.parse.quote(book_name, encoding="utf-8", errors="ignore")
        search_url = f"{self.search_site}/search.html?kw={encoded_name}"
        html_text, _, _ = fetch_html(
            search_url,
            timeout=timeout,
            headers=DESKTOP_HEADERS,
            opener=self._opener,
        )

        candidates: list[tuple[float, str]] = []
        for match in re.finditer(
            r"<a\s+href=\"(/xs_\d+/\d+\.html)\"[^>]*>(.*?)</a>",
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            href = html.unescape(match.group(1))
            title_html = match.group(2)
            title = re.sub(r"<[^>]+>", "", html.unescape(title_html)).strip()
            score = self._score_book_title(book_name, title)
            if score > 0:
                candidates.append((score, href))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_href = candidates[0]
        if best_score < 0.55:
            return None

        book_path = best_href[:-5] if best_href.endswith(".html") else best_href
        self._book_path_cache[book_name] = book_path
        return book_path

    @staticmethod
    def _extract_content_fragment(page_html: str) -> Optional[str]:
        match = re.search(
            r"<div\s+class=\"content\"\s*>(.*?)</div>",
            page_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return None
        return match.group(1)

    @staticmethod
    def _clean_content_text(text: str) -> str:
        cleaned_lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if "一七小说" in line and "免费阅读" in line:
                continue
            if "阅读模式" in line and "无法显示本章节全部内容" in line:
                continue
            if "本章未完" in line and "继续阅读" in line:
                continue
            if "加载更多" in line:
                continue
            # Some anti-crawler lines are split by "|".
            if "|" in line and len(line) <= 48:
                line = line.replace("|", "")
            if line:
                cleaned_lines.append(line)

        normalized = "\n".join(cleaned_lines)
        return normalized.strip()

    @staticmethod
    def _normalize_oneqxs_path(href: str) -> str:
        href = href.strip()
        if not href:
            return ""
        parsed = urllib.parse.urlparse(href)
        if parsed.scheme and parsed.netloc:
            if "1qxs.com" not in parsed.netloc:
                return ""
            path = parsed.path
        else:
            path = href
        return path.split("?", 1)[0].rstrip("/")

    @staticmethod
    def _parse_right_link(page_html: str) -> str:
        matches = re.findall(
            r"<div\s+class=\"right\"\s*>\s*<a\s+href=\"([^\"]+)\"",
            page_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not matches:
            return ""
        # The page has another \"right\" block in header, navigation one is the last.
        return html.unescape(matches[-1])

    def fetch_chapter(
        self,
        *,
        book_name: str,
        chapter_order: int,
        chapter_name: str,
        timeout: int,
    ) -> Optional[FreeChapterResult]:
        if chapter_order <= 0:
            return None

        book_path = self._find_book_path(book_name, timeout=timeout)
        if not book_path or not ONEQXS_BOOK_PATH_RE.fullmatch(book_path):
            return None

        chapter_root = f"{book_path}/{chapter_order}"
        current_path = chapter_root
        max_pages = 20
        part_index = 1
        visited: set[str] = set()
        chunks: list[str] = []

        for _ in range(max_pages):
            normalized_path = self._normalize_oneqxs_path(current_path)
            if not normalized_path or normalized_path in visited:
                break
            visited.add(normalized_path)

            url = urllib.parse.urljoin(self.site, normalized_path)
            page_html, _, _ = fetch_html(
                url,
                timeout=timeout,
                headers=MOBILE_HEADERS,
                opener=self._opener,
            )

            fragment = self._extract_content_fragment(page_html)
            if fragment:
                page_text = self._clean_content_text(html_to_text(fragment))
                if page_text:
                    chunks.append(page_text)

            right_href = self._parse_right_link(page_html)
            right_path = self._normalize_oneqxs_path(right_href)
            if not right_path:
                break

            expected_next_part = f"{chapter_root}/{part_index + 1}"
            if right_path == expected_next_part:
                current_path = right_path
                part_index += 1
                time.sleep(0.05)
                continue

            # Right link changed to another chapter (or other page), stop current chapter merge.
            break

        if not chunks:
            return None

        # Remove repeated chunks caused by occasional mirror duplication.
        deduped: list[str] = []
        for chunk in chunks:
            if not deduped or deduped[-1] != chunk:
                deduped.append(chunk)

        return FreeChapterResult(
            text="\n".join(deduped).strip(),
            source_url=urllib.parse.urljoin(self.site, chapter_root),
            source_site=self.name,
        )


class FxnzwProvider(FreeSourceProvider):
    name = "fxnzw"
    site = "https://www.fxnzw.com"

    def __init__(self) -> None:
        cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar)
        )
        self._book_path_cache: dict[str, str] = {}

    @staticmethod
    def _clean_content_text(text: str) -> str:
        cleaned_lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("小说："):
                continue
            if any(
                marker in line
                for marker in (
                    "飞翔鸟中文",
                    "最新网址",
                    "请记住本书首发域名",
                    "手机版阅读网址",
                    "收藏本站",
                    "加入书签",
                    "投推荐票",
                    "投月票",
                    "上一章",
                    "下一章",
                    "返回目录",
                )
            ):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _find_book_path(self, book_name: str, timeout: int) -> Optional[str]:
        if book_name in self._book_path_cache:
            return self._book_path_cache[book_name]

        encoded_name = urllib.parse.quote(book_name, encoding="utf-8", errors="ignore")
        search_url = f"{self.site}/fxnlist/{encoded_name}.html"
        html_text, _, _ = fetch_html(
            search_url,
            timeout=timeout,
            headers=DESKTOP_HEADERS,
            opener=self._opener,
        )

        best_by_path: dict[str, float] = {}
        for match in re.finditer(
            r"<a\s+href=\"(/fxnbook/\d+\.html)\"[^>]*>(.*?)</a>",
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            path = html.unescape(match.group(1)).strip()
            if not FXNZW_BOOK_PATH_RE.fullmatch(path):
                continue
            title = re.sub(r"<[^>]+>", "", html.unescape(match.group(2))).strip()
            if not title:
                continue
            score = score_title_similarity(book_name, title)
            if score <= 0:
                continue
            previous = best_by_path.get(path)
            if previous is None or score > previous:
                best_by_path[path] = score

        if not best_by_path:
            return None

        best_path, best_score = max(best_by_path.items(), key=lambda item: item[1])
        if best_score < 0.55:
            return None

        self._book_path_cache[book_name] = best_path
        return best_path

    @staticmethod
    def _extract_catalog_entries(catalog_html: str) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        seen_paths: set[str] = set()
        for match in re.finditer(
            r"<a\s+href=\"(/fxnread/\d+_\d+\.html)\"[^>]*>(.*?)</a>",
            catalog_html,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            path = html.unescape(match.group(1)).strip()
            if not FXNZW_CHAPTER_PATH_RE.fullmatch(path):
                continue
            if path in seen_paths:
                continue
            title = re.sub(r"<[^>]+>", "", html.unescape(match.group(2))).strip()
            if not title:
                continue
            seen_paths.add(path)
            entries.append((path, title))
        return entries

    def _fetch_catalog_entries(self, book_path: str, timeout: int) -> list[tuple[str, str]]:
        book_match = FXNZW_BOOK_PATH_RE.fullmatch(book_path)
        if not book_match:
            return []
        book_id = book_match.group(1)
        catalog_url = f"{self.site}/fxnchapter/{book_id}.html"
        catalog_html, _, _ = fetch_html(
            catalog_url,
            timeout=timeout,
            headers=DESKTOP_HEADERS,
            opener=self._opener,
        )
        return self._extract_catalog_entries(catalog_html)

    def fetch_chapter(
        self,
        *,
        book_name: str,
        chapter_order: int,
        chapter_name: str,
        timeout: int,
    ) -> Optional[FreeChapterResult]:
        if chapter_order <= 0:
            return None

        book_path = self._find_book_path(book_name, timeout=timeout)
        if not book_path:
            return None

        entries = self._fetch_catalog_entries(book_path, timeout=timeout)
        chapter_path = pick_chapter_path(
            entries,
            chapter_name=chapter_name,
            chapter_order=chapter_order,
        )
        if not chapter_path:
            return None

        chapter_url = urllib.parse.urljoin(self.site, chapter_path)
        page_html, _, _ = fetch_html(
            chapter_url,
            timeout=timeout,
            headers=DESKTOP_HEADERS,
            opener=self._opener,
        )

        match = re.search(
            r"<div\s+id=\"Lab_Contents\"[^>]*>(.*?)</div>",
            page_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return None

        content_html = re.sub(
            r"<script[^>]*>.*?</script>",
            "",
            match.group(1),
            flags=re.IGNORECASE | re.DOTALL,
        )
        content_html = re.sub(
            r"<style[^>]*>.*?</style>",
            "",
            content_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = self._clean_content_text(html_to_text(content_html))
        if not text:
            return None

        return FreeChapterResult(
            text=text,
            source_url=chapter_url,
            source_site=self.name,
        )


class BQG2Provider(FreeSourceProvider):
    name = "bqg2"
    site = "https://www.bqg2.org"
    search_path = "/search.php"

    def __init__(self) -> None:
        cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar)
        )
        self._book_path_cache: dict[str, str] = {}

    @staticmethod
    def _search_headers() -> dict[str, str]:
        return {
            **DESKTOP_HEADERS,
            "Referer": "https://www.bqg2.org/",
            "Origin": "https://www.bqg2.org",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    @staticmethod
    def _clean_content_text(text: str) -> str:
        cleaned_lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if any(
                marker in line
                for marker in (
                    "请收藏本站",
                    "请记住本书首发域名",
                    "最新网址",
                    "手机版阅读网址",
                    "天才一秒记住",
                    "bqg2.org",
                    "笔趣阁",
                    "上一章",
                    "下一章",
                    "返回目录",
                    "推荐阅读",
                )
            ):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _search_html(self, book_name: str, timeout: int) -> str:
        search_url = urllib.parse.urljoin(self.site, self.search_path)
        fetch_html(
            f"{self.site}/",
            timeout=timeout,
            headers=DESKTOP_HEADERS,
            opener=self._opener,
        )

        headers = self._search_headers()
        utf8_data = urllib.parse.urlencode(
            {"s": book_name}, encoding="utf-8", errors="ignore"
        ).encode("ascii")
        gbk_data = urllib.parse.urlencode(
            {"s": book_name}, encoding="gbk", errors="ignore"
        ).encode("ascii")

        # Warm-up request improves hit rate for the following GBK query.
        try:
            fetch_html(
                search_url,
                timeout=timeout,
                headers=headers,
                opener=self._opener,
                data=utf8_data,
            )
        except Exception:  # noqa: BLE001
            pass

        last_error: Optional[Exception] = None
        for _ in range(2):
            try:
                html_text, _, _ = fetch_html(
                    search_url,
                    timeout=timeout,
                    headers=headers,
                    opener=self._opener,
                    data=gbk_data,
                )
                return html_text
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(0.05)

        if last_error is not None:
            raise last_error
        return ""

    def _find_book_path(self, book_name: str, timeout: int) -> Optional[str]:
        if book_name in self._book_path_cache:
            return self._book_path_cache[book_name]

        search_html = self._search_html(book_name, timeout=timeout)
        best_by_path: dict[str, float] = {}
        for match in re.finditer(
            r"<a\s+href=\"(/html/\d+/\d+/)\"[^>]*>(.*?)</a>",
            search_html,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            path = html.unescape(match.group(1)).strip()
            if not BQG2_BOOK_PATH_RE.fullmatch(path):
                continue
            title = re.sub(r"<[^>]+>", "", html.unescape(match.group(2))).strip()
            if not title:
                continue
            score = score_title_similarity(book_name, title)
            if score <= 0:
                continue
            previous = best_by_path.get(path)
            if previous is None or score > previous:
                best_by_path[path] = score

        if not best_by_path:
            return None

        best_path, best_score = max(best_by_path.items(), key=lambda item: item[1])
        if best_score < 0.55:
            return None

        self._book_path_cache[book_name] = best_path
        return best_path

    def _fetch_catalog_entries(self, book_path: str, timeout: int) -> list[tuple[str, str]]:
        if not BQG2_BOOK_PATH_RE.fullmatch(book_path):
            return []

        catalog_url = urllib.parse.urljoin(self.site, book_path)
        catalog_html, _, _ = fetch_html(
            catalog_url,
            timeout=timeout,
            headers=DESKTOP_HEADERS,
            opener=self._opener,
        )

        entries: list[tuple[str, str]] = []
        seen_paths: set[str] = set()
        for match in re.finditer(
            r"<a\s+href=\"(/html/\d+/\d+/\d+\.html)\"[^>]*>(.*?)</a>",
            catalog_html,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            path = html.unescape(match.group(1)).strip()
            if not BQG2_CHAPTER_PATH_RE.fullmatch(path):
                continue
            if path in seen_paths:
                continue
            title = re.sub(r"<[^>]+>", "", html.unescape(match.group(2))).strip()
            if not title:
                continue
            seen_paths.add(path)
            entries.append((path, title))
        return entries

    def fetch_chapter(
        self,
        *,
        book_name: str,
        chapter_order: int,
        chapter_name: str,
        timeout: int,
    ) -> Optional[FreeChapterResult]:
        if chapter_order <= 0:
            return None

        book_path = self._find_book_path(book_name, timeout=timeout)
        if not book_path:
            return None

        entries = self._fetch_catalog_entries(book_path, timeout=timeout)
        chapter_path = pick_chapter_path(
            entries,
            chapter_name=chapter_name,
            chapter_order=chapter_order,
        )
        if not chapter_path:
            direct_path = f"{book_path}{chapter_order}.html"
            if BQG2_CHAPTER_PATH_RE.fullmatch(direct_path):
                chapter_path = direct_path
        if not chapter_path:
            return None

        chapter_url = urllib.parse.urljoin(self.site, chapter_path)
        page_html, _, _ = fetch_html(
            chapter_url,
            timeout=timeout,
            headers=DESKTOP_HEADERS,
            opener=self._opener,
        )
        match = re.search(
            r"<div\s+id=\"content\"[^>]*>(.*?)</div>",
            page_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return None

        content_html = re.sub(
            r"<script[^>]*>.*?</script>",
            "",
            match.group(1),
            flags=re.IGNORECASE | re.DOTALL,
        )
        content_html = re.sub(
            r"<style[^>]*>.*?</style>",
            "",
            content_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = self._clean_content_text(html_to_text(content_html))
        if not text:
            return None

        return FreeChapterResult(
            text=text,
            source_url=chapter_url,
            source_site=self.name,
        )


def _detect_charset(raw: bytes, header_charset: Optional[str]) -> str:
    if header_charset:
        return header_charset
    head = raw[:4096].decode("ascii", errors="ignore")
    match = re.search(r"charset\s*=\s*[\"']?([a-zA-Z0-9_-]+)", head, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return "utf-8"


def _safe_regex(pattern: str, *, field: str) -> re.Pattern[str]:
    if not pattern or len(pattern) > 3000:
        raise RuntimeError(f"源配置 {field} 正则为空或过长。")
    try:
        return re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    except re.error as exc:
        raise RuntimeError(f"源配置 {field} 正则无效: {exc}") from exc


def _same_site_url(site: str, value: str) -> str:
    url = urllib.parse.urljoin(site.rstrip("/") + "/", value)
    parsed_site = urllib.parse.urlparse(site)
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme.lower() not in {"http", "https"}:
        raise RuntimeError(f"源配置 URL 协议不安全: {value}")
    if parsed_url.netloc.lower() != parsed_site.netloc.lower():
        raise RuntimeError(f"源配置 URL 越域: {value}")
    validate_safe_text_url(url)
    return url


def _path_with_query(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    value = parsed.path
    if parsed.query:
        value += "?" + parsed.query
    return value


def _group_or(match: re.Match[str], name: str, index: int) -> str:
    if name in match.re.groupindex:
        return html.unescape(match.group(name) or "").strip()
    try:
        return html.unescape(match.group(index) or "").strip()
    except IndexError:
        return ""


class ConfigurableFreeSourceProvider(FreeSourceProvider):
    """Safe regex/template provider loaded from config/free_sources.json."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.name = str(config["name"]).lower()
        self.site = str(config["site"]).rstrip("/")
        self._book_path_cache: dict[str, str] = {}
        cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar)
        )

    def _format(self, template: str, *, book_name: str = "", book_path: str = "", query_encoding: str = "utf-8") -> str:
        return template.format(
            query=urllib.parse.quote(book_name, encoding=query_encoding, errors="ignore"),
            book_name=book_name,
            book_path=book_path.strip("/"),
        )

    def _fetch_by_request(self, request_config: dict, *, book_name: str, timeout: int) -> tuple[str, str]:
        method = str(request_config.get("method") or "GET").upper()
        encoding = str(request_config.get("encoding") or "utf-8")
        url_template = str(request_config.get("url") or "")
        url = _same_site_url(self.site, self._format(url_template, book_name=book_name, query_encoding=encoding))
        headers = dict(DESKTOP_HEADERS)
        data = None
        if method == "POST":
            fields = dict(request_config.get("fields") or {})
            body = {
                str(key): self._format(str(value), book_name=book_name, query_encoding=encoding)
                for key, value in fields.items()
            }
            data = urllib.parse.urlencode(body, encoding=encoding, errors="ignore").encode("ascii", errors="ignore")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers["Referer"] = url
        elif method != "GET":
            raise RuntimeError(f"源配置不支持的请求方法: {method}")
        html_text, final_url, _ = fetch_html(url, timeout=timeout, headers=headers, opener=self._opener, data=data)
        return html_text, final_url

    def _find_book_path(self, book_name: str, timeout: int) -> Optional[str]:
        if book_name in self._book_path_cache:
            return self._book_path_cache[book_name]

        search_config = dict(self.config.get("search") or {})
        html_text, final_url = self._fetch_by_request(search_config, book_name=book_name, timeout=timeout)
        book_path_regex = str(self.config.get("book_path_regex") or "")
        if search_config.get("accept_final_url") and book_path_regex:
            final_path = urllib.parse.urlparse(final_url).path
            if _safe_regex(book_path_regex, field="book_path_regex").fullmatch(final_path):
                self._book_path_cache[book_name] = final_path
                return final_path

        result_regex = str(search_config.get("result_regex") or "")
        if not result_regex:
            return None
        best: tuple[float, str] = (0.0, "")
        for match in _safe_regex(result_regex, field="search.result_regex").finditer(html_text):
            path = _group_or(match, "path", 1)
            title = re.sub(r"<[^>]+>", "", _group_or(match, "title", 2)).strip()
            if not path:
                continue
            resolved_url = _same_site_url(self.site, path)
            resolved_path = _path_with_query(resolved_url)
            path_only = urllib.parse.urlparse(resolved_url).path
            if book_path_regex and not _safe_regex(book_path_regex, field="book_path_regex").fullmatch(path_only):
                continue
            score = score_title_similarity(book_name, title or book_name)
            if score > best[0]:
                best = (score, resolved_path)
        if best[0] < 0.55:
            return None
        self._book_path_cache[book_name] = best[1]
        return best[1]

    def _fetch_catalog_entries(self, book_path: str, timeout: int) -> list[tuple[str, str]]:
        catalog_config = dict(self.config.get("catalog") or {})
        url_template = str(catalog_config.get("url") or "")
        catalog_url = _same_site_url(self.site, self._format(url_template, book_path=book_path))
        catalog_html, _, _ = fetch_html(catalog_url, timeout=timeout, headers=DESKTOP_HEADERS, opener=self._opener)
        item_regex = _safe_regex(str(catalog_config.get("item_regex") or ""), field="catalog.item_regex")
        entries: list[tuple[str, str]] = []
        seen: set[str] = set()
        for match in item_regex.finditer(catalog_html):
            path = _group_or(match, "path", 1)
            title = re.sub(r"<[^>]+>", "", _group_or(match, "title", 2)).strip()
            if not path or not title:
                continue
            full_url = _same_site_url(catalog_url, path)
            full_path = _path_with_query(full_url)
            if not urllib.parse.urlparse(full_url).path.startswith(book_path.rstrip("/") + "/"):
                continue
            if full_path in seen:
                continue
            seen.add(full_path)
            entries.append((full_path, title))
        return entries

    def _extract_content(self, page_html: str) -> str:
        chapter_config = dict(self.config.get("chapter") or {})
        text_html = ""
        if chapter_config.get("content_regex"):
            match = _safe_regex(str(chapter_config.get("content_regex")), field="chapter.content_regex").search(page_html)
            if match:
                text_html = _group_or(match, "content", 1)
        elif chapter_config.get("start_regex") and chapter_config.get("end_regex"):
            start = _safe_regex(str(chapter_config.get("start_regex")), field="chapter.start_regex").search(page_html)
            if start:
                end = _safe_regex(str(chapter_config.get("end_regex")), field="chapter.end_regex").search(page_html, start.end())
                if end:
                    text_html = page_html[start.start():end.start()]
        if not text_html:
            return ""
        text_html = re.sub(r"<script[^>]*>.*?</script>", "", text_html, flags=re.IGNORECASE | re.DOTALL)
        text_html = re.sub(r"<style[^>]*>.*?</style>", "", text_html, flags=re.IGNORECASE | re.DOTALL)
        text = html_to_text(text_html)
        cleaned_lines: list[str] = []
        skip_markers = list(self.config.get("cleanup_contains") or [])
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if any(str(marker) in line for marker in skip_markers):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def fetch_chapter(
        self,
        *,
        book_name: str,
        chapter_order: int,
        chapter_name: str,
        timeout: int,
    ) -> Optional[FreeChapterResult]:
        if chapter_order <= 0:
            return None
        book_path = self._find_book_path(book_name, timeout=timeout)
        if not book_path:
            return None
        entries = self._fetch_catalog_entries(book_path, timeout=timeout)
        chapter_path = pick_chapter_path(entries, chapter_name=chapter_name, chapter_order=chapter_order)
        if not chapter_path:
            return None
        chapter_url = _same_site_url(self.site, chapter_path)
        page_html, _, _ = fetch_html(chapter_url, timeout=timeout, headers=DESKTOP_HEADERS, opener=self._opener)
        text = self._extract_content(page_html)
        if not text:
            return None
        return FreeChapterResult(text=text, source_url=chapter_url, source_site=self.name)


def validate_configurable_source(config: dict) -> dict:
    if not isinstance(config, dict):
        raise RuntimeError("源配置必须是对象。")
    name = str(config.get("name") or "").strip().lower()
    if not SOURCE_NAME_RE.fullmatch(name):
        raise RuntimeError("源 name 只能使用 2-32 位 ASCII 字母、数字、下划线或短横线。")
    if name in BUILTIN_SOURCE_NAMES:
        raise RuntimeError(f"源 name 与内置源冲突: {name}")
    site = str(config.get("site") or "").strip().rstrip("/")
    parsed_site = urllib.parse.urlparse(site)
    if parsed_site.scheme.lower() not in {"http", "https"} or not parsed_site.netloc:
        raise RuntimeError("源 site 必须是 HTTP/HTTPS 站点根 URL。")
    normalized = dict(config)
    normalized["name"] = name
    normalized["site"] = site
    for section in ("search", "catalog", "chapter"):
        if not isinstance(normalized.get(section), dict):
            raise RuntimeError(f"源配置缺少 {section} 对象。")
    if not normalized["search"].get("url"):
        raise RuntimeError("源配置缺少 search.url。")
    if not normalized["catalog"].get("url") or not normalized["catalog"].get("item_regex"):
        raise RuntimeError("源配置缺少 catalog.url 或 catalog.item_regex。")
    chapter = normalized["chapter"]
    if not chapter.get("content_regex") and not (chapter.get("start_regex") and chapter.get("end_regex")):
        raise RuntimeError("源配置 chapter 必须提供 content_regex 或 start/end_regex。")
    for regex_field in (
        ("book_path_regex", normalized.get("book_path_regex")),
        ("search.result_regex", normalized["search"].get("result_regex")),
        ("catalog.item_regex", normalized["catalog"].get("item_regex")),
        ("chapter.content_regex", chapter.get("content_regex")),
        ("chapter.start_regex", chapter.get("start_regex")),
        ("chapter.end_regex", chapter.get("end_regex")),
    ):
        if regex_field[1]:
            _safe_regex(str(regex_field[1]), field=regex_field[0])
    _same_site_url(site, str(normalized["search"].get("url")))
    _same_site_url(site, str(normalized["catalog"].get("url")))
    return normalized


def load_configurable_source_configs(*, include_disabled: bool = False) -> list[dict]:
    if not SOURCE_CONFIG_PATH.exists():
        return []
    try:
        data = json.loads(SOURCE_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 读取源配置失败: {exc}")
        return []
    sources = data.get("sources") if isinstance(data, dict) else []
    configs: list[dict] = []
    for item in sources or []:
        try:
            config = validate_configurable_source(item)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] 跳过无效源配置: {exc}")
            continue
        if include_disabled or config.get("enabled", True):
            configs.append(config)
    return configs


def configurable_source_names(*, include_disabled: bool = False) -> list[str]:
    return [config["name"] for config in load_configurable_source_configs(include_disabled=include_disabled)]


def default_fallback_source_names() -> list[str]:
    names = ["1qxs", "fxnzw"]
    for config in load_configurable_source_configs():
        name = config["name"]
        if config.get("default", True) and name not in names:
            names.append(name)
    if "bqg2" not in names:
        names.append("bqg2")
    return names


def sanitize_filename(name: str, fallback: str) -> str:
    safe = ILLEGAL_FILENAME_CHARS_RE.sub("_", name).strip()
    safe = re.sub(r"\s+", " ", safe)
    return safe or fallback


def to_int(value: object) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_chapter_url(url: str) -> tuple[int, int]:
    match = CHAPTER_URL_RE.search(url)
    if not match:
        raise ValueError(f"无法从链接解析章节 ID: {url}")
    return int(match.group(1)), int(match.group(2))


def parse_book_id(url: str) -> int:
    chapter_match = CHAPTER_URL_RE.search(url)
    if chapter_match:
        return int(chapter_match.group(1))
    book_match = BOOK_URL_RE.search(url)
    if not book_match:
        raise ValueError(f"无法从链接解析书籍 ID: {url}")
    return int(book_match.group(1))


def build_mobile_book_url(book_id: int) -> str:
    return f"https://m.qidian.com/book/{book_id}/"


def build_mobile_chapter_url(book_id: int, chapter_id: int) -> str:
    return f"https://m.qidian.com/chapter/{book_id}/{chapter_id}/"


def is_blocked_network_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_http_host(parsed: urllib.parse.ParseResult, url: str) -> None:
    host = parsed.hostname
    if not host:
        raise RuntimeError(f"无法解析链接主机: {url}")

    normalized_host = host.strip("[]").rstrip(".").lower()
    if normalized_host in BLOCKED_HOST_NAMES or normalized_host.endswith(".local"):
        raise RuntimeError(f"拦截了本机或局域网链接: {url}")

    try:
        direct_ip = ipaddress.ip_address(normalized_host)
    except ValueError:
        direct_ip = None
    if direct_ip is not None:
        if is_blocked_network_ip(direct_ip):
            raise RuntimeError(f"拦截了非公网 IP 链接: {url}")
        return

    try:
        resolved = socket.getaddrinfo(
            normalized_host,
            parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise RuntimeError(f"无法解析链接主机: {normalized_host}") from exc

    for item in resolved:
        resolved_ip = ipaddress.ip_address(item[4][0])
        if is_blocked_network_ip(resolved_ip):
            raise RuntimeError(f"拦截了指向本机或内网的链接: {url}")


def validate_safe_text_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise RuntimeError(f"仅允许 HTTP/HTTPS 链接: {url}")
    validate_public_http_host(parsed, url)

    lower_path = parsed.path.lower()
    for ext in BLOCKED_EXTENSIONS:
        if lower_path.endswith(ext):
            raise RuntimeError(f"拦截了非文本下载链接: {url}")


def fetch_html(
    url: str,
    *,
    timeout: int = 30,
    headers: Optional[dict[str, str]] = None,
    opener: Optional[urllib.request.OpenerDirector] = None,
    data: Optional[bytes] = None,
) -> tuple[str, str, str]:
    validate_safe_text_url(url)
    request = urllib.request.Request(url=url, headers=headers or DESKTOP_HEADERS, data=data)
    open_func = opener.open if opener is not None else urllib.request.urlopen

    try:
        with open_func(request, timeout=timeout) as response:
            status = response.getcode()
            raw = response.read(MAX_DOWNLOAD_BYTES + 1)
            if len(raw) > MAX_DOWNLOAD_BYTES:
                raise RuntimeError(f"响应体过大，已中止: {url}")

            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)

            content_type = (response.headers.get("Content-Type") or "").lower()
            if not any(keyword in content_type for keyword in ALLOWED_CONTENT_TYPE_KEYWORDS):
                raise RuntimeError(
                    f"仅允许抓取文本页面，检测到非文本类型: {content_type or 'unknown'} - {url}"
                )

            charset = _detect_charset(raw, response.headers.get_content_charset())
            text = raw.decode(charset, errors="replace")
            if status != 200:
                raise RuntimeError(f"请求失败: HTTP {status} - {url}")
            return text, response.geturl(), content_type
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP 错误: {exc.code} - {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络错误: {exc.reason} - {url}") from exc
    except (http.client.RemoteDisconnected, TimeoutError, OSError) as exc:
        raise RuntimeError(f"网络连接中断: {exc} - {url}") from exc


def extract_page_data(html_text: str) -> dict:
    script_blocks = re.findall(
        r"<script[^>]*>(.*?)</script>", html_text, flags=re.IGNORECASE | re.DOTALL
    )
    for block in reversed(script_blocks):
        candidate = block.strip()
        if candidate.startswith('{"pageContext"'):
            try:
                payload = json.loads(html.unescape(candidate))
                return payload["pageContext"]["pageProps"]["pageData"]
            except (json.JSONDecodeError, KeyError) as exc:
                raise RuntimeError("页面数据解析失败，可能页面结构已变更。") from exc
    raise RuntimeError("未找到章节数据脚本，可能被风控或页面结构发生变化。")


def html_to_text(content_html: str) -> str:
    if not content_html:
        return ""

    text = content_html
    text = re.sub(r"<\s*p\b[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/\s*p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.rstrip() for line in text.split("\n")]
    cleaned: list[str] = []
    prev_blank = True

    for line in lines:
        if not line.strip():
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
            continue
        cleaned.append(line)
        prev_blank = False

    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    return "\n".join(cleaned).strip()


def fetch_book_info(book_id: int, timeout: int) -> BookInfo:
    page_data = extract_page_data(
        fetch_html(build_mobile_book_url(book_id), timeout=timeout, headers=MOBILE_HEADERS)[0]
    )
    book_info = page_data.get("bookInfo") or {}
    chapter_content_info = page_data.get("chapterContentInfo") or {}

    book_name = str(book_info.get("bookName") or f"book-{book_id}")
    first_chapter_id = to_int(chapter_content_info.get("firstChapterId"))
    if not first_chapter_id:
        raise RuntimeError("未能从书籍页解析首章 ID。")

    return BookInfo(book_id=book_id, book_name=book_name, first_chapter_id=first_chapter_id)


def fetch_chapter_info(book_id: int, chapter_id: int, timeout: int) -> ChapterInfo:
    url = build_mobile_chapter_url(book_id, chapter_id)
    page_data = extract_page_data(fetch_html(url, timeout=timeout, headers=MOBILE_HEADERS)[0])
    chapter_data = page_data.get("chapterInfo")
    if not isinstance(chapter_data, dict):
        raise RuntimeError(f"章节数据缺失: {url}")

    chapter_name = str(chapter_data.get("chapterName") or f"chapter-{chapter_id}")
    chapter_order = to_int(chapter_data.get("seq"))
    if chapter_order is None:
        raw_order = to_int(chapter_data.get("chapterOrder"))
        if raw_order is not None and raw_order >= 0:
            chapter_order = raw_order // 1000 + 1

    next_chapter_id = to_int(chapter_data.get("next"))
    vip_status = to_int(chapter_data.get("vipStatus")) or 0
    is_buy = to_int(chapter_data.get("isBuy")) or 0
    words_count = to_int(chapter_data.get("wordsCount")) or 0
    content_html = str(chapter_data.get("content") or "")

    book_info = page_data.get("bookInfo") or {}
    book_name = str(book_info.get("bookName") or f"book-{book_id}")

    return ChapterInfo(
        book_id=book_id,
        book_name=book_name,
        chapter_id=chapter_id,
        chapter_name=chapter_name,
        chapter_order=chapter_order,
        next_chapter_id=next_chapter_id,
        vip_status=vip_status,
        is_buy=is_buy,
        source_url=url,
        source_site="qidian",
        words_count=words_count,
        text=html_to_text(content_html),
    )


def chapter_file_path(output_dir: Path, chapter: ChapterInfo) -> Path:
    name = sanitize_filename(chapter.chapter_name, f"chapter-{chapter.chapter_id}")
    if chapter.chapter_order is not None and chapter.chapter_order >= 0:
        filename = f"{chapter.chapter_order:04d}_{name}.txt"
    else:
        filename = f"{chapter.chapter_id}_{name}.txt"
    return output_dir / filename


def build_locked_placeholder(chapter: ChapterInfo) -> str:
    return (
        f"{chapter.chapter_name}\n"
        f"来源: {chapter.source_url}\n"
        f"来源站点: {chapter.source_site}\n\n"
        "该章节可能需要登录、订阅或购买后才能查看完整内容。\n"
    )


def build_chapter_text(chapter: ChapterInfo) -> str:
    return (
        f"{chapter.chapter_name}\n"
        f"来源: {chapter.source_url}\n"
        f"来源站点: {chapter.source_site}\n\n"
        f"{chapter.text}\n"
    )


def write_chapter(output_dir: Path, chapter: ChapterInfo, save_locked: bool) -> Optional[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = chapter_file_path(output_dir, chapter)

    if chapter.is_locked():
        if not save_locked:
            return None
        target.write_text(build_locked_placeholder(chapter), encoding="utf-8")
        return target

    target.write_text(build_chapter_text(chapter), encoding="utf-8")
    return target


def append_merged(merged_path: Path, chapter: ChapterInfo, index: int, save_locked: bool) -> bool:
    merged_path.parent.mkdir(parents=True, exist_ok=True)
    if chapter.is_locked() and not save_locked:
        return False

    prefix = "\n\n" if index > 0 else ""
    body = build_locked_placeholder(chapter) if chapter.is_locked() else build_chapter_text(chapter)
    with merged_path.open("a", encoding="utf-8") as file:
        file.write(prefix)
        file.write(body.rstrip())
        file.write("\n")
    return True


def build_fallback_providers(source_names: str) -> list[FreeSourceProvider]:
    names = [item.strip().lower() for item in source_names.split(",") if item.strip()]
    if not names:
        names = default_fallback_source_names()

    config_by_name = {
        config["name"]: config for config in load_configurable_source_configs()
    }
    providers: list[FreeSourceProvider] = []
    for name in names:
        if name == "1qxs":
            providers.append(OneQXSProvider())
        elif name == "fxnzw":
            providers.append(FxnzwProvider())
        elif name == "bqg2":
            providers.append(BQG2Provider())
        elif name in config_by_name:
            providers.append(ConfigurableFreeSourceProvider(config_by_name[name]))
        else:
            print(f"[WARN] 未识别的免费源: {name}，已跳过")
    return providers


def try_free_fallback(
    chapter: ChapterInfo,
    *,
    providers: list[FreeSourceProvider],
    timeout: int,
    min_chars: int,
) -> Optional[ChapterInfo]:
    if not chapter.is_locked() or chapter.chapter_order is None:
        return None

    for provider in providers:
        try:
            result = provider.fetch_chapter(
                book_name=chapter.book_name,
                chapter_order=chapter.chapter_order,
                chapter_name=chapter.chapter_name,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[FALLBACK][{provider.name}] 失败: {exc}")
            continue

        if not result or not result.text:
            continue

        if len(result.text) < min_chars:
            print(
                f"[FALLBACK][{provider.name}] 命中但内容过短({len(result.text)}字符)，已忽略"
            )
            continue

        print(
            f"[FALLBACK][{provider.name}] 命中章节: "
            f"{chapter.chapter_order:04d} {chapter.chapter_name}"
        )
        return replace(
            chapter,
            source_url=result.source_url,
            source_site=result.source_site,
            text=result.text,
            vip_status=0,
            is_buy=1,
            words_count=max(chapter.words_count, len(result.text)),
        )

    return None


def export_single_chapter(args: argparse.Namespace) -> int:
    book_id, chapter_id = parse_chapter_url(args.chapter_url)
    chapter = fetch_chapter_info(book_id, chapter_id, timeout=args.timeout)

    fallback_providers = (
        build_fallback_providers(args.fallback_sources) if args.fallback_free else []
    )

    if chapter.is_locked() and fallback_providers:
        replacement = try_free_fallback(
            chapter,
            providers=fallback_providers,
            timeout=args.timeout,
            min_chars=args.fallback_min_chars,
        )
        if replacement is not None:
            chapter = replacement

    output_dir = Path(args.output_dir).resolve()
    file_path = write_chapter(output_dir, chapter, save_locked=args.save_locked)

    if file_path is None:
        raise RuntimeError("该章节可能是付费章节，未导出。可加 --save-locked 输出占位文件。")

    print(f"[OK] 导出章节: {file_path}")

    if args.merge_file:
        merged_path = Path(args.merge_file).resolve()
        append_merged(merged_path, chapter, index=0, save_locked=args.save_locked)
        print(f"[OK] 合并文件更新: {merged_path}")

    return 0


def export_book(args: argparse.Namespace) -> int:
    book_id = parse_book_id(args.book_url)
    info = fetch_book_info(book_id, timeout=args.timeout)
    start_chapter_id = args.start_chapter_id or info.first_chapter_id

    output_dir = Path(args.output_dir).resolve()
    merged_path = (
        Path(args.merge_file).resolve()
        if args.merge_file
        else output_dir / f"{sanitize_filename(info.book_name, str(info.book_id))}_all.txt"
    )

    if args.merge and merged_path.exists():
        merged_path.unlink()

    fallback_providers = (
        build_fallback_providers(args.fallback_sources) if args.fallback_free else []
    )

    print(
        f"[INFO] 书籍: {info.book_name} (ID: {info.book_id}), "
        f"起始章节: {start_chapter_id}"
    )

    visited: set[int] = set()
    current_chapter_id = start_chapter_id
    fetched_count = 0
    exported_count = 0
    skipped_locked = 0
    fallback_count = 0
    merged_index = 0
    stop_reason = ""

    while current_chapter_id and current_chapter_id not in visited:
        visited.add(current_chapter_id)
        fetched_count += 1

        chapter = fetch_chapter_info(info.book_id, current_chapter_id, timeout=args.timeout)
        if chapter.is_locked() and fallback_providers:
            replacement = try_free_fallback(
                chapter,
                providers=fallback_providers,
                timeout=args.timeout,
                min_chars=args.fallback_min_chars,
            )
            if replacement is not None:
                chapter = replacement
                fallback_count += 1

        file_path = write_chapter(output_dir, chapter, save_locked=args.save_locked)
        if file_path is None:
            skipped_locked += 1
            print(f"[SKIP] 章节锁定: {chapter.chapter_id} {chapter.chapter_name}")
        else:
            exported_count += 1
            print(f"[OK] 章节已导出: {file_path.name}")

        if args.merge:
            merged_written = append_merged(
                merged_path, chapter, index=merged_index, save_locked=args.save_locked
            )
            if merged_written:
                merged_index += 1

        if args.end_chapter_id and chapter.chapter_id == args.end_chapter_id:
            print(f"[INFO] 已到达结束章节 ID: {args.end_chapter_id}")
            stop_reason = "end_chapter"
            break

        if args.max_chapters and fetched_count >= args.max_chapters:
            print(f"[INFO] 已达到 max-chapters={args.max_chapters}")
            stop_reason = "max_chapters"
            break

        if not chapter.next_chapter_id or chapter.next_chapter_id <= 0:
            print("[INFO] 已到最后一章。")
            stop_reason = "last_chapter"
            break

        current_chapter_id = chapter.next_chapter_id
        if args.delay > 0:
            time.sleep(args.delay)

    if not stop_reason and current_chapter_id in visited:
        print(f"[WARN] 检测到章节循环，已停止。当前章节 ID: {current_chapter_id}")

    print(f"[DONE] 抓取章节数: {fetched_count}")
    print(f"[DONE] 导出成功数: {exported_count}")
    print(f"[DONE] 锁定跳过数: {skipped_locked}")
    print(f"[DONE] 免费源回退数: {fallback_count}")
    print(f"[DONE] 输出目录: {output_dir}")
    if args.merge:
        print(f"[DONE] 合并文件: {merged_path}")

    return 0


def build_common_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="网络请求超时时间（秒），默认 30。",
    )
    common.add_argument(
        "--fallback-free",
        dest="fallback_free",
        action="store_true",
        default=True,
        help="遇到付费/锁定章节时自动尝试免费站点回退（默认开启）。",
    )
    common.add_argument(
        "--no-fallback-free",
        dest="fallback_free",
        action="store_false",
        help="关闭免费站点回退，仅抓取起点。",
    )
    common.add_argument(
        "--fallback-sources",
        default=",".join(default_fallback_source_names()),
        help="免费源列表，逗号分隔。默认使用内置源和 config/free_sources.json 中的默认源。",
    )
    common.add_argument(
        "--fallback-min-chars",
        type=int,
        default=120,
        help="回退正文最小字符数，低于该值视为无效内容。",
    )
    return common


def build_arg_parser() -> argparse.ArgumentParser:
    common = build_common_parser()
    parser = argparse.ArgumentParser(
        description=(
            "将起点小说章节导出为本地 TXT 文件。"
            "若章节付费/锁定，可自动回退到免费站点并仅抓取文本内容。"
        )
    )

    subparsers = parser.add_subparsers(dest="mode", required=True)

    chapter_parser = subparsers.add_parser(
        "chapter", help="导出单个章节", parents=[common]
    )
    chapter_parser.add_argument("--chapter-url", required=True, help="章节链接")
    chapter_parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"输出目录，默认 {DEFAULT_OUTPUT_DIR}",
    )
    chapter_parser.add_argument(
        "--merge-file",
        default="",
        help="可选：同时写入指定合并 TXT 文件路径。",
    )
    chapter_parser.add_argument(
        "--save-locked",
        action="store_true",
        help="章节锁定时生成占位 TXT（默认不生成）。",
    )

    book_parser = subparsers.add_parser(
        "book", help="从首章或指定章节开始导出", parents=[common]
    )
    book_parser.add_argument("--book-url", required=True, help="书籍链接（也支持章节链接）")
    book_parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"输出目录，默认 {DEFAULT_OUTPUT_DIR}",
    )
    book_parser.add_argument(
        "--start-chapter-id",
        type=int,
        default=0,
        help="从该章节 ID 开始，默认自动使用首章。",
    )
    book_parser.add_argument(
        "--end-chapter-id",
        type=int,
        default=0,
        help="到该章节 ID 停止（包含该章节）。",
    )
    book_parser.add_argument(
        "--max-chapters",
        type=int,
        default=0,
        help="最多抓取章节数，0 表示不限制。",
    )
    book_parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="章节请求间隔秒数，默认 0.25。",
    )
    book_parser.add_argument(
        "--merge",
        action="store_true",
        help="额外输出整本合并 TXT 文件。",
    )
    book_parser.add_argument(
        "--merge-file",
        default="",
        help="合并文件路径，不填时默认 output/<书名>_all.txt。",
    )
    book_parser.add_argument(
        "--save-locked",
        action="store_true",
        help="章节锁定时生成占位 TXT（默认跳过）。",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.mode == "chapter":
        return export_single_chapter(args)
    if args.mode == "book":
        return export_book(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
