#!/usr/bin/env python3
"""重掃 skill 目錄，只在內容真的變了才改寫儀表板頁面。

給排程用：
    python3 artifacts/update-dashboard.py --baseline <已發佈頁面的下載檔>
    退出碼 0 = 有變動，已改寫 skill-index.html，需要重新發佈
    退出碼 2 = 沒有變動，什麼都別做
    退出碼 1 = 出錯
變動摘要會印到 stdout，可直接放進發佈的 label。

--baseline 要指向「目前線上那一版」的 HTML。排程執行的 session 不見得能 git push
（推送可能需要人工批准，而排程時沒有人在），所以不能拿 repo 裡的檔案當基準：推不上去
的話基準永遠不會前進，同一個變動會每小時被重新發佈一次。線上頁面是排程唯一能可靠寫入
的狀態，因此以它為準。省略時退回用 repo 裡的檔案，適合手動執行。
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

HERE  = Path(__file__).resolve().parent
PAGE  = HERE / "skill-index.html"
BLOB  = re.compile(r'(<script id="skill-data" type="application/json">)(.*?)(</script>)', re.S)
# 比對時忽略的欄位：scannedAt 每次都不同，needsCuration 由人工消化
IGNORE = {"needsCuration"}


def key(skills: list[dict]) -> dict:
    return {s["name"]: {k: v for k, v in sorted(s.items()) if k not in IGNORE} for s in skills}


def seed_of(path: Path) -> dict:
    m = BLOB.search(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path} 裡找不到 skill-data 區塊")
    return json.loads(m.group(2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", help="拿來比對的已發佈頁面 HTML；省略則用 repo 內的檔案")
    args = ap.parse_args()

    if not PAGE.is_file():
        print(f"找不到 {PAGE}", file=sys.stderr)
        return 1
    html = PAGE.read_text(encoding="utf-8")
    m = BLOB.search(html)
    if not m:
        print("頁面裡找不到 skill-data 區塊", file=sys.stderr)
        return 1
    try:
        current = seed_of(Path(args.baseline)) if args.baseline else json.loads(m.group(2))
    except (OSError, ValueError) as e:
        print(f"讀不到比對基準：{e}", file=sys.stderr)
        return 1

    scan = subprocess.run([sys.executable, str(HERE / "scan-skills.py")],
                          capture_output=True, text=True)
    if scan.returncode != 0:
        print(scan.stderr.strip() or "掃描失敗", file=sys.stderr)
        return 1
    fresh = json.loads(scan.stdout)

    if fresh.get("partial"):
        print("掃描不完整，不改寫也不發佈：" + fresh["partial"], file=sys.stderr)
        return 1

    a, b = key(current["skills"]), key(fresh["skills"])
    if a == b:
        print("沒有變動")
        return 2

    added   = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    changed = sorted(n for n in set(a) & set(b) if a[n] != b[n])
    parts = []
    if added:   parts.append(f"新增 {len(added)}：{'、'.join(added)}")
    if removed: parts.append(f"移除 {len(removed)}：{'、'.join(removed)}")
    if changed: parts.append(f"異動 {len(changed)}：{'、'.join(changed[:6])}"
                             + (f" 等 {len(changed)} 筆" if len(changed) > 6 else ""))

    doc = {"scannedAt": fresh["scannedAt"], "cats": current["cats"], "skills": fresh["skills"]}
    PAGE.write_text(
        html[:m.start(2)] + "\n" + json.dumps(doc, ensure_ascii=False, indent=1) + "\n" + html[m.end(2):],
        encoding="utf-8")

    print(" · ".join(parts))
    pending = [s["name"] for s in fresh["skills"] if s.get("needsCuration")]
    if pending:
        print("待補中文名與分類：" + "、".join(pending))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
