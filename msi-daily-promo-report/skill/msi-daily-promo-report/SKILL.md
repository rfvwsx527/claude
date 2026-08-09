---
name: msi-daily-promo-report
description: 產出 MSI Store（tw-store.msi.com）每日活動優惠 Excel 報告並建立 Gmail 草稿。當使用者要求「MSI 每日報告」「微星活動報告」「抓 MSI 優惠」，或排程任務指示執行 MSI 活動監控時使用此 skill。抓取限時優惠、福利品、加購方案、組合優惠等專區的商品名稱、原價、活動價、折扣率與庫存，整理成 xlsx 後以附件建立 Gmail 草稿（草稿由使用者的 Apps Script 定時寄出，本 skill 絕不直接寄信）。
---

# MSI Store 每日活動優惠報告

每日抓取 MSI 官方商城活動資料 → 產出 Excel → 建立 Gmail 草稿。
草稿的實際寄送由使用者 Google 帳號裡的 Apps Script 觸發器負責，
**本 skill 只建草稿，絕不呼叫任何寄送功能**。

## 固定參數

- 收件人：`rfvwsx527@gmail.com`（安裝時已設定，之後不再詢問）
- 主旨格式：`【MSI每日活動報告】YYYY-MM-DD`（Apps Script 依此前綴搜尋草稿，**不可更改前綴**）
- 時區：Asia/Taipei（產報告日期一律用台北時間）

## 執行流程

### 步驟 1：抓取商品資料（web_fetch）

逐一以 web_fetch 抓取下列 Shopify JSON 端點。這些是公開端點，
回傳結構化 JSON，**優先於抓 HTML 頁面**：

| 專區 | URL | 折扣方式代碼 |
|---|---|---|
| 限時優惠 | https://tw-store.msi.com/collections/limited-time-offer/products.json | A｜直接標價折扣（不得合併折扣碼） |
| 福利品 | https://tw-store.msi.com/collections/welfare/products.json | A｜直接標價（福利品不疊加任何優惠、非嚴重瑕疵不退） |
| 加購8折-電競周邊 | https://tw-store.msi.com/collections/gaminggearprogram/products.json | B｜同筆訂單購買筆電/桌機/螢幕/主板/顯卡後加購，結帳自動8折 |
| 加購7折-服飾配件 | https://tw-store.msi.com/collections/definemystyleprogram2/products.json | B｜購買任何商品後同筆訂單加購，結帳自動7折 |
| 加購9折-筆電配件 | https://tw-store.msi.com/collections/laptop-handheld-accy/products.json | B｜同筆訂單加購自動9折 |
| 加購9折-延長保固 | https://tw-store.msi.com/collections/msi-care-plus/products.json | B｜購買主機同筆加購延保9折 |
| 筆電戰鬥組合 | https://tw-store.msi.com/collections/gaming-laptop-battle-bundle/products.json | A＋隨貨贈品（後背包+耳機+滑鼠，無需登錄） |
| 筆電雙螢幕組合 | https://tw-store.msi.com/collections/laptop-dual-monitor-bundle/products.json | H｜組合定價 |
| 筆電高效組合 | https://tw-store.msi.com/collections/laptop-productivity-bundle/products.json | H｜組合定價 |
| DIY套裝組合 | https://tw-store.msi.com/collections/diy-pack/products.json | H｜組合定價 |
| 商務套裝組合 | https://tw-store.msi.com/collections/business-pack/products.json | H｜組合定價 |
| 白色套裝組合 | https://tw-store.msi.com/collections/white-pack/products.json | H｜組合定價 |
| 40週年LUCKY收藏 | https://tw-store.msi.com/collections/msi-40th-lucky-collection/products.json | A｜直接標價（部分限定預購） |
| 教育75折賣場 | https://tw-store.msi.com/collections/2024edu75/products.json | I｜需教育資格審核 |

每個 JSON 取 `products[]` 中的：`title`、`product_type`、`handle`、
`variants[0].price`（現售價）、`variants[0].compare_at_price`（原價，
可能為 null 或等於現售價 = 無折扣）、`variants[].available`（任一為
true = 有庫存）。商品連結為 `https://tw-store.msi.com/products/{handle}`。

注意事項：
- 抓取工具可能剝除 URL 查詢參數；products.json 預設每頁 30 筆，
  本清單各專區皆 ≤ 25 件，30 筆上限足夠。若某專區恰好回傳 30 筆，
  在報告該分頁備註「可能有第 2 頁未涵蓋」。
- 某端點抓取失敗時：跳過該專區、在摘要頁標註「抓取失敗」，
  **繼續完成其餘專區**，不要中止整個任務。

### 步驟 2：抓取活動層級資訊（登錄送類）

web_fetch 抓 https://tw-store.msi.com/pages/promotions ，
擷取每個活動的：活動名稱（h3 標題）、活動期間（標題後段落中的日期）、
贈品內容。這些是「購買後登錄送贈品」類活動（折扣方式 C），
商品層級只有「指定機種」字樣，如實記錄即可，不要虛構型號清單。
依台北時間今天日期判斷每檔活動為「進行中」或「已結束」。
此頁抓取失敗時略過本節，繼續後續步驟。

### 步驟 3：產出 Excel

把步驟 1 的資料整理成一個 JSON 檔存到 `/home/claude/msi_data.json`，
結構：

```json
{
  "crawl_time": "2026-08-09 08:00 (台北時間)",
  "collections": [
    {"name": "限時優惠", "mech": "A｜...", "note": "",
     "items": [{"title": "...", "type": "...", "price": 2988,
                "compare_at": 3188, "available": true,
                "url": "https://..."}]}
  ],
  "promotions": [
    {"title": "...", "period": "...", "gift": "...", "status": "進行中"}
  ]
}
```

然後執行本 skill 附帶的產表腳本：

```bash
python {skill_dir}/scripts/build_excel.py /home/claude/msi_data.json /home/claude/MSI活動優惠_YYYY-MM-DD.xlsx
```

（`{skill_dir}` 為本 SKILL.md 所在目錄；日期用台北時間今天。）
腳本會產出含摘要頁＋各專區分頁的 xlsx，含折扣率公式與格式。

### 步驟 4：建立 Gmail 草稿

1. 把 xlsx 轉 base64：
   ```bash
   base64 -w0 /home/claude/MSI活動優惠_YYYY-MM-DD.xlsx > /home/claude/xlsx.b64
   ```
2. 呼叫 `Gmail:create_draft`：
   - `to`: [收件人]
   - `subject`: `【MSI每日活動報告】YYYY-MM-DD`
   - `htmlBody`: 簡短 HTML 摘要 — 各專區商品數與最深折扣的表格、
     全站折扣 Top 5（含商品連結、原價→現價、省幾 %）、
     進行中的登錄送活動清單。結尾註明「完整明細見附件」。
   - `attachments`: `[{"filename": "MSI活動優惠_YYYY-MM-DD.xlsx",
     "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
     "content": "<base64字串>"}]`
3. base64 內容過大無法放入工具呼叫時的降級做法：改建**無附件**草稿，
   htmlBody 內放完整的各專區商品 HTML 表格，主旨改為
   `【MSI每日活動報告】YYYY-MM-DD（明細於內文）`。

### 步驟 5：回報

任務結束時輸出一段摘要：抓取成功/失敗的專區數、商品總數、
草稿 ID、是否含附件。**不要寄送草稿、不要詢問是否寄送**——
寄送由 Apps Script 處理。

## 禁止事項

- 不呼叫任何寄送郵件的功能；只用 create_draft
- 同一天已存在相同主旨的草稿時（可用 Gmail:list_drafts 查
  `subject:【MSI每日活動報告】` 確認），先建新草稿即可，
  不要刪除舊草稿（Apps Script 端會處理重複）
- 抓不到的資料標「未取得」，不要用推測值填補價格或日期
