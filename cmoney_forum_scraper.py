#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CMoney 股市爆料同學會 — 使用者歷史發文爬蟲

指定一位使用者(例如 https://www.cmoney.tw/forum/user/2408703),
抓取他從以前到現在的所有發文與發文時間,輸出成 CSV。

原理:
    CMoney 論壇是前後端分離的網頁應用,發文列表由瀏覽器透過 XHR/fetch
    以 JSON 取得(內含精確的發文時間戳),而非寫死在 HTML 裡。
    本腳本用 Playwright 開啟真實瀏覽器載入使用者頁面,一邊自動向下捲動
    觸發「載入更多」,一邊攔截所有 JSON 回應,從中以通用啟發式規則
    (同時具有 時間欄位 + 內容欄位 + 文章ID 的物件)辨識出發文資料,
    去重後依時間排序輸出 CSV。
    這種「攔截 API 回應」的作法不依賴特定的 API 網址或 DOM 結構,
    即使 CMoney 改版換了端點名稱,通常仍能正常運作。

安裝:
    pip install playwright
    playwright install chromium

使用:
    python cmoney_forum_scraper.py https://www.cmoney.tw/forum/user/2408703
    python cmoney_forum_scraper.py 2408703 -o posts.csv
    python cmoney_forum_scraper.py 2408703 --headful          # 顯示瀏覽器視窗(除錯用)
    python cmoney_forum_scraper.py --selftest                  # 不連網,自測解析邏輯

輸出 CSV 欄位:
    文章ID, 發文時間(台北時區), 內容, 文章網址, 讚數, 留言數
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time as time_mod
from datetime import datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")

# ---------------------------------------------------------------------------
# JSON 啟發式解析:從任意 JSON 回應中找出「發文」物件
# ---------------------------------------------------------------------------

TIME_KEYS = (
    "createtime", "createdtime", "creattime", "createat", "createdat",
    "posttime", "publishtime", "publishat", "articlecreatetime",
)
CONTENT_KEYS = ("content", "text", "title", "articlecontent")
ID_KEYS = ("articleid", "id", "postid")
AUTHOR_KEYS = ("creatorid", "memberid", "authorid", "userid")
LIKE_KEYS = ("likecount", "interestedcount", "reactioncount", "likes")
COMMENT_KEYS = ("commentcount", "replycount", "comments")


def _get_ci(d: dict, keys: Iterable[str]) -> Any:
    """不分大小寫地依候選 key 順序取值。"""
    lower = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k in lower and lower[k] is not None:
            return lower[k]
    return None


def parse_timestamp(value: Any) -> datetime | None:
    """把 epoch 秒/毫秒 或 ISO 字串轉成台北時區的 datetime。"""
    if value is None:
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        num = float(value)
        if num > 1e12:      # 毫秒
            num /= 1000.0
        if num < 1e8:       # 太小,不是合理的 epoch
            return None
        try:
            return datetime.fromtimestamp(num, tz=timezone.utc).astimezone(TAIPEI)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip().replace("Z", "+00:00")
        for fmt in (None, "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
            try:
                dt = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TAIPEI)  # 站方時間預設視為台北時間
            return dt.astimezone(TAIPEI)
    return None


def looks_like_post(d: dict) -> bool:
    """判斷一個 dict 是否像一篇「發文」:要有時間、內容、文章ID。"""
    lower = {str(k).lower() for k in d.keys()}
    has_time = any(k in lower for k in TIME_KEYS)
    has_content = any(k in lower for k in CONTENT_KEYS)
    has_id = any(k in lower for k in ID_KEYS)
    # 排除「留言」物件:有 commentId 但沒有 articleId 的通常是留言
    is_bare_comment = "commentid" in lower and "articleid" not in lower
    return has_time and has_content and has_id and not is_bare_comment


def extract_posts(node: Any, target_user_id: str | None, found: list[dict]) -> None:
    """遞迴走訪 JSON,收集所有像發文的物件。"""
    if isinstance(node, dict):
        if looks_like_post(node):
            author = _get_ci(node, AUTHOR_KEYS)
            # 若能判斷作者且不是目標使用者,略過(例如轉貼內嵌的他人文章)
            if target_user_id is None or author is None or str(author) == str(target_user_id):
                found.append(node)
        for v in node.values():
            extract_posts(v, target_user_id, found)
    elif isinstance(node, list):
        for item in node:
            extract_posts(item, target_user_id, found)


def normalize_post(raw: dict) -> dict | None:
    """把原始 JSON 物件整理成輸出用的統一欄位。"""
    post_id = _get_ci(raw, ID_KEYS)
    dt = parse_timestamp(_get_ci(raw, TIME_KEYS))
    content = _get_ci(raw, CONTENT_KEYS)
    if post_id is None or dt is None:
        return None
    if isinstance(content, str):
        content = re.sub(r"\s+", " ", content).strip()
    likes = _get_ci(raw, LIKE_KEYS)
    comments = _get_ci(raw, COMMENT_KEYS)
    return {
        "文章ID": str(post_id),
        "發文時間": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "_dt": dt,
        "內容": content or "",
        "文章網址": f"https://www.cmoney.tw/forum/article/{post_id}",
        "讚數": likes if isinstance(likes, (int, float)) else "",
        "留言數": comments if isinstance(comments, (int, float)) else "",
    }


# ---------------------------------------------------------------------------
# 主爬蟲:Playwright 開頁 + 自動捲動 + 攔截 JSON
# ---------------------------------------------------------------------------

def _find_chromium(explicit: str | None) -> str | None:
    """回傳 Chromium 執行檔路徑;None 表示交給 Playwright 自己找。"""
    import os
    candidates = [explicit, os.environ.get("CHROMIUM_EXECUTABLE"),
                  "/opt/pw-browsers/chromium"]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def scrape(user_id: str, max_scrolls: int, headful: bool,
           idle_rounds: int = 10, chromium_path: str | None = None) -> list[dict]:
    from playwright.sync_api import sync_playwright

    url = f"https://www.cmoney.tw/forum/user/{user_id}"
    collected: dict[str, dict] = {}

    def on_response(response):
        try:
            ctype = response.headers.get("content-type", "")
            if "json" not in ctype and not response.url.endswith(".json"):
                return
            body = response.json()
        except Exception:
            return
        raw_posts: list[dict] = []
        extract_posts(body, user_id, raw_posts)
        for raw in raw_posts:
            post = normalize_post(raw)
            if post:
                collected[post["文章ID"]] = post

    with sync_playwright() as p:
        exe = _find_chromium(chromium_path)
        try:
            browser = p.chromium.launch(headless=not headful, executable_path=exe)
        except Exception:
            # 找不到指定的瀏覽器就退回 Playwright 預設(需先 playwright install chromium)
            browser = p.chromium.launch(headless=not headful)
        page = browser.new_page(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"),
            viewport={"width": 1280, "height": 900},
        )
        page.on("response", on_response)
        print(f"開啟 {url} ...", flush=True)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            browser.close()
            print(f"錯誤:無法連線到 {url}\n  {e}", file=sys.stderr)
            print("請確認你的網路可以連上 www.cmoney.tw(公司防火牆/代理可能會擋)。",
                  file=sys.stderr)
            return []
        page.wait_for_timeout(3_000)

        # 自動捲動直到連續 idle_rounds 次都沒有新文章,或達到 max_scrolls
        stale = 0
        last_count = -1
        for i in range(max_scrolls):
            page.mouse.wheel(0, 4_000)
            page.keyboard.press("End")
            page.wait_for_timeout(1_200)
            # 若頁面有「載入更多 / 查看更多」按鈕就點它
            for label in ("載入更多", "查看更多", "更多"):
                try:
                    btn = page.get_by_role("button", name=label)
                    if btn.count() and btn.first.is_visible():
                        btn.first.click(timeout=1_000)
                except Exception:
                    pass
            count = len(collected)
            if count == last_count:
                stale += 1
                if stale >= idle_rounds:
                    break
            else:
                stale = 0
                last_count = count
                print(f"  已收集 {count} 篇...", flush=True)
        browser.close()

    posts = sorted(collected.values(), key=lambda x: x["_dt"])
    for post in posts:
        post.pop("_dt", None)
    return posts


def write_csv(posts: list[dict], path: str) -> None:
    fields = ["文章ID", "發文時間", "內容", "文章網址", "讚數", "留言數"]
    # utf-8-sig:讓 Excel 直接開啟不會亂碼
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(posts)


# ---------------------------------------------------------------------------
# 自我測試(不需網路):驗證 JSON 解析啟發式
# ---------------------------------------------------------------------------

def selftest() -> int:
    sample = {
        "data": {
            "articles": [
                {"articleId": 111, "creatorId": 2408703, "content": "看多台積電\n目標價上看",
                 "createTime": 1700000000, "likeCount": 12, "commentCount": 3},
                {"articleId": 222, "creatorId": 2408703, "content": "今天大盤觀察",
                 "createTime": "2024-05-01T09:30:00+08:00", "likeCount": 0, "commentCount": 0},
                # 別人的文章 → 應被過濾
                {"articleId": 333, "creatorId": 999, "content": "路人文", "createTime": 1700000001},
                # 留言 → 應被過濾
                {"commentId": 444, "content": "推", "createTime": 1700000002, "id": 444},
            ]
        }
    }
    found: list[dict] = []
    extract_posts(sample, "2408703", found)
    posts = [p for p in (normalize_post(r) for r in found) if p]
    ids = sorted(p["文章ID"] for p in posts)
    assert ids == ["111", "222"], f"expected ['111','222'], got {ids}"
    t1 = next(p for p in posts if p["文章ID"] == "111")["發文時間"]
    assert t1 == "2023-11-15 06:13:20", t1  # epoch 1700000000 → 台北時間
    print("selftest OK:", posts)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CMoney 股市爆料同學會使用者發文爬蟲")
    ap.add_argument("user", nargs="?", default="2408703",
                    help="使用者頁網址或數字 ID(預設 2408703)")
    ap.add_argument("-o", "--output", default=None, help="輸出 CSV 路徑")
    ap.add_argument("--max-scrolls", type=int, default=3000,
                    help="最大捲動次數(預設 3000,足以載完多年發文)")
    ap.add_argument("--headful", action="store_true", help="顯示瀏覽器視窗")
    ap.add_argument("--chromium-path", default=None,
                    help="自訂 Chromium 執行檔路徑(預設自動偵測)")
    ap.add_argument("--selftest", action="store_true", help="執行離線自我測試")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    m = re.search(r"(\d+)", args.user)
    if not m:
        print("錯誤:無法從輸入解析出使用者 ID", file=sys.stderr)
        return 1
    user_id = m.group(1)
    out = args.output or f"cmoney_user_{user_id}_posts.csv"

    t0 = time_mod.time()
    posts = scrape(user_id, max_scrolls=args.max_scrolls, headful=args.headful,
                   chromium_path=args.chromium_path)
    if not posts:
        print("沒有攔截到任何發文資料。可能原因:", file=sys.stderr)
        print("  1. 網路無法連到 cmoney.tw(防火牆/代理)", file=sys.stderr)
        print("  2. 頁面要求登入才能看歷史文章 → 用 --headful 打開視窗手動登入後再等待", file=sys.stderr)
        print("  3. 使用者 ID 不存在或沒有發文", file=sys.stderr)
        return 2

    write_csv(posts, out)
    print(f"完成:共 {len(posts)} 篇發文,時間範圍 {posts[0]['發文時間']} ~ {posts[-1]['發文時間']}")
    print(f"已輸出 {out}(耗時 {time_mod.time() - t0:.0f} 秒)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
