# MSI Store 活動追蹤器

定時蒐集 [MSI Store 微星品牌旗艦館](https://tw-store.msi.com/) 的活動、活動商品、折扣與時間資料。

## 內容

- `scrape_msi_store.py` — 爬蟲主程式
  - 透過 Shopify 公開 API `/products.json` 抓全站商品，以 `compare_at_price > price` 判斷折扣中商品並計算折數
  - 抓取已知活動頁（清單在 `PROMO_PAGES`，有新活動頁直接加進去），擷取標題與內文日期區間
- `reports/YYYY-MM-DD.md` — 每日報告（Markdown 表格）
- `data/products-YYYY-MM-DD.csv` — 折扣商品明細（可用 Excel 開啟）
- `data/latest.json` — 最新原始資料，可供前後比對新增/下架活動
- `.github/workflows/msi-store-scrape.yml` — GitHub Actions 排程，每天台北時間 09:00 自動執行並 commit 報告

## 手動執行

```bash
python msi-store-tracker/scrape_msi_store.py
```

也可在 GitHub Actions 頁面用 **Run workflow** 手動觸發。

## 注意事項

- 網站若啟用機器人防護（Cloudflare 等）可能擋掉部分請求；腳本已帶瀏覽器 User-Agent 並限速（每頁間隔 1 秒），若仍被擋可考慮改用 Playwright。
- 首份報告 `reports/2026-07-27.md` 因執行環境無法直連該網站，是由搜尋引擎索引資料整理而成。
