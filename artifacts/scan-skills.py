#!/usr/bin/env python3
"""掃描本機 skill 目錄，產出技能庫儀表板用的 data/skills.json。

用法:
    python3 artifacts/scan-skills.py                    # 印出 JSON
    python3 artifacts/scan-skills.py -o skills.json     # 寫入檔案

分類與中文名是人工維護的，掃描時會從既有的清單沿用（以 name 對應）。
掃描到的新 skill 會標上 needsCuration，等待補中文名與分類。
"""
from __future__ import annotations
import argparse, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

MNT      = Path("/mnt/skills")
SYNCED   = Path.home() / ".claude" / "skills" / "synced"
MANIFEST = SYNCED / "manifest.json"

# manifest 的 source 值 → 儀表板的來源分類
SRC_OF_SOURCE = {"custom": "mine", "anthropic-example": "example", "anthropic": "builtin"}
ROOTS = [(MNT / "examples", "example"), (MNT / "public", "builtin")]

FILES_SHOWN = 6          # 詳細面板列出的檔名數量，其餘以「另外 N 個」帶過
DEFAULT_CAT = "ops"


def frontmatter(skill_md: Path) -> dict:
    """讀 SKILL.md 最前面的 YAML frontmatter，只取 name 與 description。"""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    out, key = {}, None
    for line in m.group(1).split("\n"):
        kv = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            out[key] = val
        elif key and line.startswith((" ", "\t")):        # 折行的續行
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def human_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{n / 1024:.1f} KB"


def walk(root: Path) -> tuple[list[str], int, float]:
    """回傳 (相對路徑清單, 總位元組, 最新 mtime)。"""
    names, total, newest = [], 0, 0.0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git"}]
        for f in filenames:
            p = Path(dirpath) / f
            try:
                st = p.stat()
            except OSError:
                continue
            names.append(str(p.relative_to(root)))
            total += st.st_size
            newest = max(newest, st.st_mtime)
    names.sort(key=lambda s: (s.count("/"), s.lower()))
    return names, total, newest


def load_manifest() -> dict[str, dict]:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {s["name"]: s for s in data.get("skills", []) if s.get("name")}


def first_sentence(text: str, limit: int = 90) -> str:
    s = re.split(r"(?<=[。.!?])\s", text.strip(), maxsplit=1)[0]
    return s if len(s) <= limit else s[: limit - 1] + "…"


def scan() -> list[dict]:
    manifest = load_manifest()
    found: dict[str, dict] = {}

    dirs: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for root, src in ROOTS:
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if d.is_dir() and (d / "SKILL.md").is_file():
                    dirs.append((d, src))
                    seen.add(d.name)
    # 同步目錄整個掃過，不倚賴 manifest 有沒有登記：
    # 直接放進目錄的 skill 也要看得見。與 /mnt 同名的視為同一個，不重複列。
    synced_names: set[str] = set()
    if SYNCED.is_dir():
        for d in sorted(SYNCED.iterdir()):
            if not (d.is_dir() and (d / "SKILL.md").is_file()):
                continue
            synced_names.add(d.name)
            if d.name in seen:
                continue
            entry = manifest.get(d.name)
            dirs.append((d, SRC_OF_SOURCE.get(entry.get("source")) if entry else "mine"))

    for d, src in dirs:
        name = d.name
        fm = frontmatter(d / "SKILL.md")
        files, total, newest = walk(d)
        entry = manifest.get(name)
        if entry and entry.get("updatedAt"):
            updated = entry["updatedAt"][:10]
        else:
            updated = datetime.fromtimestamp(newest or 0, timezone.utc).strftime("%Y-%m-%d")
        found[name] = {
            "name": fm.get("name") or name,
            "cat": DEFAULT_CAT,
            "src": src,
            "enabled": name in manifest or name in synced_names,
            "size": human_size(total),
            "updated": updated,
            "nfiles": len(files),
            "files": files[:FILES_SHOWN],
            "path": str(d) + "/",
            "raw": fm.get("description", ""),
        }
    return [found[k] for k in sorted(found)]


def merge(scanned: list[dict], previous: list[dict]) -> list[dict]:
    """沿用既有的人工欄位（中文名、分類、一句話用途）。"""
    prev = {s["name"]: s for s in previous}
    out = []
    for s in scanned:
        old = prev.get(s["name"])
        if old:
            s["zh"] = old.get("zh", s["name"])
            s["cat"] = old.get("cat", DEFAULT_CAT)
            s["desc"] = old.get("desc") or first_sentence(s["raw"])
        else:
            s["zh"] = s["name"]
            s["desc"] = first_sentence(s["raw"])
            s["needsCuration"] = True
        out.append(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", help="輸出檔案，預設印到 stdout")
    ap.add_argument("--previous", default=str(Path(__file__).with_name("skill-index.html")),
                    help="沿用人工欄位的來源：舊的 skills.json 或含資料的儀表板 HTML")
    args = ap.parse_args()

    previous: list[dict] = []
    cats: list[dict] = []
    src = Path(args.previous)
    if src.is_file():
        text = src.read_text(encoding="utf-8")
        blob = re.search(r'<script id="skill-data" type="application/json">(.*?)</script>', text, re.S)
        payload = json.loads(blob.group(1)) if blob else json.loads(text)
        previous = payload.get("skills", [])
        cats = payload.get("cats", [])

    skills = merge(scan(), previous)
    doc = {
        "scannedAt": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
        "cats": cats,
        "skills": skills,
    }
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        new = [s["name"] for s in skills if s.get("needsCuration")]
        gone = sorted(set(s["name"] for s in previous) - set(s["name"] for s in skills))
        print(f"{len(skills)} 個 skill → {args.out}", file=sys.stderr)
        if new:  print("新增（待補中文名與分類）: " + ", ".join(new), file=sys.stderr)
        if gone: print("已消失: " + ", ".join(gone), file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
