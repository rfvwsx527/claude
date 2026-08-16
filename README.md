# Obsidian MCP 配置

本仓库包含 Claude Code 的 Obsidian MCP 服务器配置（`.mcp.json`），通过 [mcp-obsidian](https://github.com/MarkusPfundstein/mcp-obsidian) 连接 Obsidian 的 Local REST API 插件。

## 前置条件

1. 在 Obsidian 中安装并启用 **Local REST API** 社区插件
2. 在插件设置中复制 API Key（默认端口为 `27124`，HTTPS）
3. 本机已安装 [uv](https://docs.astral.sh/uv/)（提供 `uvx` 命令）

## 使用方式

### 方式一：项目配置（本仓库已内置）

在本仓库目录下启动 Claude Code 时，`.mcp.json` 会自动加载 obsidian 服务器。API Key 不会提交到仓库，通过环境变量注入：

```bash
export OBSIDIAN_API_KEY=你的key
# 可选，默认值如下
export OBSIDIAN_HOST=127.0.0.1
export OBSIDIAN_PORT=27124

claude
```

### 方式二：全局/本地添加（命令行）

```bash
claude mcp add obsidian \
  -e OBSIDIAN_API_KEY=你的key \
  -e OBSIDIAN_HOST=127.0.0.1 \
  -e OBSIDIAN_PORT=27124 \
  -- uvx mcp-obsidian
```

加 `-s user` 可对所有项目生效；加 `-s project` 则写入项目的 `.mcp.json`。

## 验证

启动 Claude Code 后运行 `/mcp`，确认 `obsidian` 服务器状态为 connected。

## 注意事项

- **不要把真实的 API Key 提交到仓库**，请始终通过环境变量或 `claude mcp add -e` 传入。
- 该服务器连接的是 `127.0.0.1`（你本机的 Obsidian），因此只在本地运行 Claude Code 时可用；在云端/远程会话中无法访问你本机的 Obsidian。

---

# CMoney 股市爆料同學會發文爬蟲

`cmoney_forum_scraper.py`:抓取指定使用者(例如
https://www.cmoney.tw/forum/user/2408703 )從以前到現在的所有發文與發文時間,輸出 CSV。

## 安裝

```bash
pip install -r requirements.txt
playwright install chromium
```

## 使用

```bash
# 用網址或數字 ID 都可以,預設輸出 cmoney_user_<ID>_posts.csv
python cmoney_forum_scraper.py https://www.cmoney.tw/forum/user/2408703
python cmoney_forum_scraper.py 2408703 -o posts.csv

# 除錯:顯示瀏覽器視窗(頁面若要求登入,可在視窗中手動登入)
python cmoney_forum_scraper.py 2408703 --headful

# 不連網,驗證解析邏輯
python cmoney_forum_scraper.py --selftest
```

## 原理與說明

- 論壇的發文列表由前端以 XHR/fetch 取得 JSON(內含精確時間戳),不在靜態 HTML 中。
  腳本用 Playwright 開啟真實瀏覽器、自動向下捲動觸發載入,同時攔截所有 JSON 回應,
  以通用啟發式規則(同時具有時間、內容、文章 ID 欄位的物件)辨識發文,去重後依時間排序。
- 這種作法不依賴特定 API 網址或 DOM 結構,站方改版通常仍可運作。
- 會自動過濾留言與他人文章(依作者 ID 判斷),時間一律轉為台北時區。
- CSV 以 `utf-8-sig` 編碼,Excel 直接開啟不會亂碼。
- 欄位:`文章ID, 發文時間, 內容, 文章網址, 讚數, 留言數`。
- 請遵守網站服務條款,勿高頻率大量抓取;腳本每次捲動間隔約 1.2 秒。
