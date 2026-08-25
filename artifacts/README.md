# 技能庫儀表板

`skill-index.html` 是發佈成 Artifact 的技能庫索引頁，`scan-skills.py` 產生它讀的清單。

## 為什麼需要兩步

發佈後的 Artifact 跑在 claude.ai 的沙箱 iframe 裡，**沒有檔案系統權限**，CSP 也只放行
Google Fonts。頁面因此無法自己去掃 `/mnt/skills`。分工是：

- `scan-skills.py` 在讀得到 skill 目錄的環境掃描，輸出 JSON。
- 頁面**每次開啟**都會讀自己的資料檔 `data/skills.json`，讀不到才退回內建快照。

所以清單一旦更新，之後每次打開都是最新的，不必重新發佈整頁。

## 新增 skill 後怎麼更新

```sh
python3 artifacts/scan-skills.py            # 印出 JSON
python3 artifacts/scan-skills.py -o out.json
```

把輸出整段貼進頁面右上角的「更新清單」，按套用。頁面會：

1. 驗證 JSON，壞掉就只顯示錯誤、不動現有清單；
2. 列出新增／移除／異動的筆數與名稱；
3. 寫入 `data/skills.json`（透過 artifact capability 的檔案式發佈）。

## 人工維護的欄位

掃描能拿到 `name`、`src`、`enabled`、`size`、`nfiles`、`updated`、`path` 與
frontmatter 的 `description`。中文名 `zh`、分類 `cat`、一句話用途 `desc` 是人工的，
掃描時會依 `name` 從舊清單沿用。

新掃到的 skill 會標上 `needsCuration`，卡片上顯示「待補」，分類先落在 `ops`。補完
`zh` / `cat` / `desc` 並移除該旗標即可。

## 資料來源

- `/mnt/skills/examples/` → `example`
- `/mnt/skills/public/` → `builtin`
- `~/.claude/skills/synced/` + `manifest.json` → `mine`（`source: custom`），
  `manifest.json` 同時決定 `enabled` 與 `updatedAt`

## 每日自動更新

Routine `技能庫儀表板每日重掃（台北 09:00）`（trig_012GBVX2otuNRaodfcbzib4c，
cron `0 1 * * *`＝台北時間每天 09:00）會開一個
新 session，流程是：切到本分支 → 用 Artifact `action: read` 把**目前線上那一版**存成本機
檔 → `python3 artifacts/update-dashboard.py --baseline <那個檔>` → 退出碼 0 才重新發佈。

三個設計上的坑，都是實際觸發後才發現的：

1. **repo 的預設分支沒有 artifacts/**。新 session 預設 clone 預設分支，找不到腳本就會
   自己去 `find /` 找，然後卡在權限詢問上——排程執行時沒有人能批准，等於永久停住。
   所以指令裡明確要求先 checkout 本分支，並禁止掃描磁碟。
2. **排程 session 不見得能 git push**。所以 git 完全移出流程。
3. **因此比對基準不能用 repo 裡的檔案**。推不上去的話基準永遠停在舊版，同一個變動會
   每次執行都被重新發佈一次。改用線上頁面當基準——那是排程唯一能可靠寫入的狀態。

驗證紀錄（四次手動觸發）：

| 執行 | 情境 | 結果 |
|---|---|---|
| 1 | 舊指令，無變動 | 結束但無從確認是否真的掃過 |
| 2 | 舊指令，有差異 | **卡死**在 `find /` 的權限詢問 |
| 3 | 新指令，有差異 | 偵測到「異動 1：docx」，發佈到既有網址（未另建）✓ |
| 4 | 新指令，無變動 | 退出碼 2，**未發佈**（session 紀錄無 artifacts 欄位）✓ |

若本分支被刪除或改名，排程會回報「找不到 artifacts/update-dashboard.py」並停止，
不會誤發佈。
