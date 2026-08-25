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
