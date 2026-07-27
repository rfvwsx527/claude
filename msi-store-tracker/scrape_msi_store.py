#!/usr/bin/env python3
"""MSI Store (tw-store.msi.com) 活動與折扣商品蒐集器。

蒐集兩類資料：
1. 折扣商品 — 透過 Shopify 公開 API /products.json 取得全站商品，
   凡 compare_at_price > price 即視為折扣中，計算折數。
2. 活動頁 — 抓取已知活動/促銷頁面，擷取頁面標題與內文中的日期區間。

輸出：
- reports/YYYY-MM-DD.md   當日報告（Markdown 表格）
- data/products-YYYY-MM-DD.csv  折扣商品明細
- data/latest.json        最新一次抓取的原始整理資料（供 diff 比對）

用法：python scrape_msi_store.py [--out-dir DIR]
"""

import argparse
import csv
import datetime
import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = "https://tw-store.msi.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# 已知的活動/促銷頁面（新活動頁可自行加入）
PROMO_PAGES = [
    "/pages/campaign",
    "/pages/promotions",
    "/pages/2026summer",
    "/pages/nb-promotions",
    "/pages/education",
    "/pages/msi-holiday-coupons",
    "/pages/collection-bundle",
    "/pages/reward-program",
    "/collections/members-points-reward",
    "/collections/special-offer-laptops",
    "/collections/newproducts",
    "/collections/preorder",
]

DATE_RANGE_RE = re.compile(
    r"(20\d{2}[./年]\s?\d{1,2}[./月]\s?\d{1,2}日?)\s*[-~～至]+\s*"
    r"((?:20\d{2}[./年]\s?)?\d{1,2}[./月]\s?\d{1,2}日?)"
)


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


class TextExtractor(HTMLParser):
    """擷取 <title> 與可見文字，忽略 script/style。"""

    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self._skip = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            text = data.strip()
            if text:
                self.chunks.append(text)


def scrape_products():
    """抓取全站商品，回傳 (all_products, discounted)。"""
    products = []
    page = 1
    while True:
        url = f"{BASE}/products.json?limit=250&page={page}"
        try:
            data = json.loads(fetch(url))
        except Exception as e:
            print(f"[warn] products.json page {page} failed: {e}", file=sys.stderr)
            break
        batch = data.get("products", [])
        if not batch:
            break
        products.extend(batch)
        page += 1
        time.sleep(1)

    discounted = []
    for p in products:
        for v in p.get("variants", []):
            price = float(v.get("price") or 0)
            compare = float(v.get("compare_at_price") or 0)
            if compare > price > 0:
                discounted.append({
                    "title": p["title"],
                    "variant": v.get("title", ""),
                    "type": p.get("product_type", ""),
                    "price": price,
                    "compare_at_price": compare,
                    "discount_pct": round((1 - price / compare) * 100, 1),
                    "available": v.get("available", ""),
                    "url": f"{BASE}/products/{p['handle']}",
                })
    discounted.sort(key=lambda d: -d["discount_pct"])
    return products, discounted


def scrape_promo_pages():
    """抓取活動頁標題與日期區間。"""
    results = []
    for path in PROMO_PAGES:
        url = BASE + path
        row = {"url": url, "title": "", "date_ranges": [], "status": "ok"}
        try:
            html = fetch(url).decode("utf-8", errors="replace")
            parser = TextExtractor()
            parser.feed(html)
            row["title"] = re.sub(r"\s+", " ", parser.title).strip()
            text = " ".join(parser.chunks)
            row["date_ranges"] = [
                f"{a} ~ {b}" for a, b in dict.fromkeys(DATE_RANGE_RE.findall(text))
            ][:5]
        except Exception as e:
            row["status"] = f"error: {e}"
        results.append(row)
        time.sleep(1)
    return results


def write_report(out_dir: Path, today: str, promos, discounted, total_products):
    report = out_dir / "reports" / f"{today}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# MSI Store 活動與折扣商品報告 {today}",
        "",
        f"- 來源：{BASE}",
        f"- 全站商品數：{total_products}，折扣中品項（變體）：{len(discounted)}",
        "",
        "## 活動頁面",
        "",
        "| 活動頁 | 偵測到的日期區間 | 連結 | 狀態 |",
        "|--------|----------------|------|------|",
    ]
    for r in promos:
        dates = "; ".join(r["date_ranges"]) or "—"
        lines.append(f"| {r['title'] or r['url']} | {dates} | {r['url']} | {r['status']} |")

    lines += [
        "",
        "## 折扣商品（依折扣幅度排序）",
        "",
        "| 商品 | 規格 | 類別 | 原價 | 特價 | 折扣 | 有貨 | 連結 |",
        "|------|------|------|------|------|------|------|------|",
    ]
    for d in discounted:
        lines.append(
            f"| {d['title']} | {d['variant']} | {d['type']} "
            f"| {d['compare_at_price']:,.0f} | {d['price']:,.0f} "
            f"| -{d['discount_pct']}% | {d['available']} | {d['url']} |"
        )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def write_csv(out_dir: Path, today: str, discounted):
    path = out_dir / "data" / f"products-{today}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["title", "variant", "type", "compare_at_price", "price",
              "discount_pct", "available", "url"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(discounted)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(Path(__file__).parent))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    today = datetime.datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")

    promos = scrape_promo_pages()
    products, discounted = scrape_products()

    report = write_report(out_dir, today, promos, discounted, len(products))
    write_csv(out_dir, today, discounted)

    latest = out_dir / "data" / "latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(
        {"date": today, "promos": promos, "discounted": discounted},
        ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"report: {report}")
    print(f"promo pages: {len(promos)}, discounted variants: {len(discounted)}")


if __name__ == "__main__":
    main()
