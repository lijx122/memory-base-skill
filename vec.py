"""
vec.py - 向量化索引与检索工具
支持子命令：index, index-dir, search, read, remove, list
"""
import argparse
import io
import os
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "store.db"
ENTRIES_DIR = SCRIPT_DIR / "entries"

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS vec_store ("
        "  id TEXT PRIMARY KEY,"
        "  title TEXT NOT NULL,"
        "  summary TEXT NOT NULL,"
        "  embedding BLOB NOT NULL,"
        "  file_path TEXT NOT NULL,"
        "  created_at INTEGER,"
        "  updated_at INTEGER"
        ")"
    )
    conn.commit()
    return conn


def parse_frontmatter(content: str) -> tuple[dict, str]:
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", content, re.DOTALL)
    if not match:
        return {}, content
    fm = match.group(1)
    body = content[match.end():]
    data = {}
    for line in fm.splitlines():
        if ": " in line:
            key, val = line.split(": ", 1)
            data[key.strip()] = val.strip()
    return data, body


def extract_title_summary(file_path: Path) -> tuple[str, str]:
    content = file_path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(content)
    title = fm.get("title", file_path.stem)
    summary = fm.get("summary", "")
    if not summary:
        body = fm.get("", "")
        summary = body or "无描述"
    return title, summary


def index_file(file_path: Path, conn: sqlite3.Connection):
    if not file_path.exists():
        print(f"[WARN] 文件不存在：{file_path}", file=sys.stderr)
        return
    title, summary = extract_title_summary(file_path)
    text = f"{title}。{summary}"
    embedding = get_model().encode(text, normalize_embeddings=True).astype(np.float32)
    now = int(os.path.getmtime(file_path))
    embedding_bytes = embedding.tobytes()
    conn.execute(
        "INSERT OR REPLACE INTO vec_store (id, title, summary, embedding, file_path, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM vec_store WHERE id = ?), ?), ?)",
        (str(file_path), title, summary, embedding_bytes, str(file_path), str(file_path), now, now),
    )
    conn.commit()
    print(f"[OK] 索引：{title}")


def cmd_index(args):
    conn = init_db()
    file_path = Path(args.file_path).resolve()
    index_file(file_path, conn)


def cmd_index_dir(_):
    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
    md_files = list(ENTRIES_DIR.glob("*.md"))
    if not md_files:
        print(f"[INFO] entries 目录为空，无需索引")
        return
    conn = init_db()
    for f in md_files:
        index_file(f, conn)
    print(f"\n[OK] 索引完成，共 {len(md_files)} 个文件")


def cmd_check(args):
    conn = init_db()
    cursor = conn.execute("SELECT id, title, summary, embedding, file_path FROM vec_store")
    rows = cursor.fetchall()
    if not rows:
        print("OK")
        return
    query_emb = get_model().encode(args.text, normalize_embeddings=True).astype(np.float32)
    best_score = -1.0
    best = None
    for row in rows:
        file_id, title, summary, emb_bytes, file_path = row
        emb = np.frombuffer(emb_bytes, dtype=np.float32)
        score = float(np.dot(query_emb, emb))
        if score > best_score:
            best_score = score
            best = (title, summary, file_path)
    if best_score > args.threshold:
        title, summary, file_path = best
        print(f"DUPLICATE [{best_score:.4f}] {title} | {summary} | {file_path}")
    else:
        print("OK")


def cmd_dedup(args):
    conn = init_db()
    cursor = conn.execute("SELECT id, title, summary, embedding, file_path FROM vec_store")
    rows = cursor.fetchall()
    if not rows:
        print("[INFO] 索引库为空")
        return
    count = len(rows)
    pairs = []
    for i in range(count):
        for j in range(i + 1, count):
            emb_i_np = np.frombuffer(rows[i][3], dtype=np.float32)
            emb_j_np = np.frombuffer(rows[j][3], dtype=np.float32)
            score = float(np.dot(emb_i_np, emb_j_np))
            if score > args.threshold:
                pairs.append((score, rows[i][1], rows[j][1], rows[i][4], rows[j][4]))
    pairs.sort(key=lambda x: x[0], reverse=True)
    if not pairs:
        print(f"[INFO] 在阈值 {args.threshold} 下未发现相似对")
        return
    print(f"[DEDUP] 发现 {len(pairs)} 个相似对（阈值 {args.threshold}）：")
    for score, title_i, title_j, path_i, path_j in pairs:
        print(f"  [{score:.4f}] {title_i} vs {title_j}")
        print(f"    A: {path_i}")
        print(f"    B: {path_j}")
    print(f"\n共 {len(pairs)} 对，请人工判断是否需要合并")


def cmd_search(args):
    conn = init_db()
    cursor = conn.execute("SELECT id, title, summary, embedding, file_path FROM vec_store")
    rows = cursor.fetchall()
    if not rows:
        print("[INFO] 索引库为空，请先执行 index 或 index-dir")
        return
    query_emb = get_model().encode(args.query, normalize_embeddings=True).astype(np.float32)
    results = []
    for row in rows:
        file_id, title, summary, emb_bytes, file_path = row
        emb = np.frombuffer(emb_bytes, dtype=np.float32)
        score = float(np.dot(query_emb, emb))
        results.append((score, title, summary, file_path))
    results.sort(key=lambda x: x[0], reverse=True)
    top = results[: args.top]
    for score, title, summary, file_path in top:
        print(f"[{score:.4f}] {title} | {summary} | {file_path}")


def cmd_read(args):
    file_path = Path(args.file_path).resolve()
    if not file_path.exists():
        print(f"[ERROR] 文件不存在：{file_path}", file=sys.stderr)
        sys.exit(1)
    print(file_path.read_text(encoding="utf-8"))


def cmd_remove(args):
    conn = init_db()
    file_id = str(Path(args.file_path).resolve())
    cur = conn.execute("SELECT id FROM vec_store WHERE id = ?", (file_id,))
    if cur.fetchone() is None:
        print(f"[INFO] 未找到索引记录：{file_path}", file=sys.stderr)
        return
    conn.execute("DELETE FROM vec_store WHERE id = ?", (file_id,))
    conn.commit()
    print(f"[OK] 已删除索引：{file_id}")


def cmd_list(_):
    conn = init_db()
    cursor = conn.execute("SELECT title, summary, file_path FROM vec_store ORDER BY file_path")
    rows = cursor.fetchall()
    if not rows:
        print("[INFO] 索引库为空")
        return
    for title, summary, file_path in rows:
        print(f"{title} | {summary} | {file_path}")


def main():
    parser = argparse.ArgumentParser(description="向量索引与检索工具")
    sub = parser.add_subparsers(dest="cmd")

    p_index = sub.add_parser("index", help="索引单个文件")
    p_index.add_argument("file_path", help="md 文件路径")

    sub.add_parser("index-dir", help="批量索引 entries 目录")

    p_search = sub.add_parser("search", help="检索")
    p_search.add_argument("query", help="检索词")
    p_search.add_argument("--top", type=int, default=3, help="返回条数")

    p_check = sub.add_parser("check", help="写入前去重检查")
    p_check.add_argument("text", help="待检查的 title + summary 文本")
    p_check.add_argument("--threshold", type=float, default=0.9, help="相似度阈值")

    p_dedup = sub.add_parser("dedup", help="全量相似对扫描")
    p_dedup.add_argument("--threshold", type=float, default=0.75, help="相似度阈值")
    p_dedup.add_argument("--min", type=int, default=20, help="条目数达到此值时才执行")

    p_read = sub.add_parser("read", help="读取文件内容")
    p_read.add_argument("file_path", help="文件路径")

    p_remove = sub.add_parser("remove", help="删除索引")
    p_remove.add_argument("file_path", help="文件路径")

    sub.add_parser("list", help="列出所有索引条目")

    args = parser.parse_args()

    if args.cmd == "index":
        cmd_index(args)
    elif args.cmd == "index-dir":
        cmd_index_dir(args)
    elif args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "dedup":
        cmd_dedup(args)
    elif args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "read":
        cmd_read(args)
    elif args.cmd == "remove":
        cmd_remove(args)
    elif args.cmd == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
