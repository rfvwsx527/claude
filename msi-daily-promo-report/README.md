# MSI Store 每日活動優惠報告

Claude skill 負責抓資料＋產 Excel＋建 Gmail 草稿，Apps Script 只負責把草稿寄出。

## 整體架構

```
每天 08:00　Claude 排程任務 → 執行 msi-daily-promo-report skill
　　　　　　　├ web_fetch 抓 14 個活動專區的 products.json
　　　　　　　├ build_excel.py 產出 xlsx（摘要頁＋各專區分頁，含折扣率公式）
　　　　　　　└ Gmail:create_draft 建草稿（主旨【MSI每日活動報告】YYYY-MM-DD＋xlsx附件）

每天 09:00　Apps Script 觸發器 → 搜尋主旨前綴的草稿 → 寄出
```

兩端唯一的約定是**主旨前綴**——skill 只建草稿絕不寄信（SKILL.md 明文禁止），
Apps Script 只寄符合前綴的草稿。中間一小時是人工檢查草稿的緩衝時間。

## 目錄結構

| 路徑 | 說明 |
|---|---|
| `skill/msi-daily-promo-report/` | Claude skill（上傳時把此資料夾壓成 zip） |
| `apps-script/MSI草稿寄送端.gs` | Google Apps Script 寄送端 |

## 安裝步驟

### Skill 端

1. 先改 `skill/msi-daily-promo-report/SKILL.md` 裡的 `RECIPIENT@example.com` 為實際收件信箱
2. 把 `msi-daily-promo-report/` 資料夾壓成 zip，Claude 設定 → Capabilities → Skills → 上傳
3. 建排程任務，prompt 寫：「執行 msi-daily-promo-report skill 產出今日 MSI 活動報告並建立 Gmail 草稿」，排每天 08:00
4. 先手動跑一次驗證——確認草稿有出現在 Gmail、附件打得開，再開排程

### Apps Script 端

1. [script.google.com](https://script.google.com) → 新專案 → 貼上 `MSI草稿寄送端.gs` → 執行一次 `setup()` 授權
2. 預設 09:00 寄送（`SEND_HOUR` 可調，建議晚於 Claude 排程至少 30 分鐘）
3. `NOTIFY_ON_MISS` 填你的信箱的話，Claude 端漏跑時會發警告信提醒，建議填

## 設計上的防呆

- **附件過大降級**：base64 後的 xlsx 若塞不進工具呼叫，skill 改建無附件草稿、
  完整表格放信件內文，主旨加註「明細於內文」——寄送端照樣認得前綴。
- **同日重複草稿**：Claude 重跑產生多份時，Apps Script 只寄最新一份、其餘丟垃圾桶。
- **單一專區抓失敗不中斷**：摘要頁標「抓取失敗」，其餘照常出。
- **分頁上限**：products.json 預設一頁 30 筆，目前各專區皆 ≤25 件；
  某專區哪天剛好回 30 筆時，報告會自動備註可能有第 2 頁。

## 執行環境注意

skill 用 `web_fetch` 抓資料（不是 bash curl），所以不受排程沙箱的網域白名單影響；
但 `web_fetch` 可能剝除 URL 查詢參數，因此設計固定在「單頁 30 筆內」。
若日後某專區商品數超過 30 件，需改成沙箱網路直抓
（在排程環境的網路設定放行 `tw-store.msi.com`）。
