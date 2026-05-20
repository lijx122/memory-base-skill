"""memory-base CLI entrypoint."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Iterable

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_WEIGHTS = [0.5, 0.3, 0.2]


def _load_common():
    import common

    return common


def _load_semantic():
    import semantic

    return semantic


def _load_bm25():
    import bm25

    return bm25


def _load_entity():
    import entity

    return entity


def _load_fusion():
    import fusion

    return fusion


def _entry_text(entry: dict, *, semantic_only: bool = False) -> str:
    title = entry.get("title", "")
    summary = entry.get("summary", "")
    if semantic_only:
        return f"{title}。{summary}".strip("。 ")
    content = entry.get("content", "")
    return "\n".join(part for part in [title, summary, content] if part)


def _store_label(file_path: str, meta: dict | None = None) -> str:
    if meta and meta.get("store"):
        return str(meta["store"])
    normalized = file_path.replace("\\", "/")
    if "/bug/entries/" in normalized:
        return "bug"
    if "/knowledge/entries/" in normalized:
        return "knowledge"
    return "entries"


def _signal_modules():
    return [_load_semantic(), _load_bm25(), _load_entity()]


def _search_candidates(query: str, store: str | None, top: int) -> list[tuple[str, float]]:
    results = [module.search(query, store, top) for module in _signal_modules()]
    return _load_fusion().merge(results, DEFAULT_WEIGHTS, top)


def _all_indexed_paths() -> list[str]:
    paths: set[str] = set()
    try:
        semantic_index = _load_semantic()._load_index()  # type: ignore[attr-defined]
        paths.update(semantic_index.keys())
    except Exception:
        pass
    try:
        bm25_index = _load_bm25()._load_index()  # type: ignore[attr-defined]
        documents = bm25_index.get("documents", {}) if isinstance(bm25_index, dict) else {}
        if isinstance(documents, dict):
            paths.update(str(path) for path in documents.keys())
    except Exception:
        pass
    try:
        entities = _load_entity()._load_entities()  # type: ignore[attr-defined]
        if isinstance(entities, dict):
            for record in entities.values():
                if isinstance(record, dict):
                    paths.update(str(path) for path in record.get("entries", []))
    except Exception:
        pass
    return sorted(paths)


def _render_related_section(related: list[tuple[str, str, str]]) -> str:
    if not related:
        return ""
    lines = ["## 相关条目"]
    for entity_type, entity, path in related:
        lines.append(f"- [{entity_type}:{entity}] {path}")
    return "\n".join(lines)


def _refresh_related_links(file_path: str) -> None:
    path = Path(file_path)
    raw = path.read_text(encoding="utf-8")
    marker = "\n## 相关条目\n"
    if marker in raw:
        raw = raw.split(marker, 1)[0].rstrip() + "\n"
    related = _load_entity().related_entries(file_path)
    section = _render_related_section(related)
    if not section:
        path.write_text(raw, encoding="utf-8")
        return
    updated = raw.rstrip() + "\n\n" + section + "\n"
    path.write_text(updated, encoding="utf-8")


def _reindex_one(file_path: str) -> None:
    common = _load_common()
    entry = common.read_entry(file_path)
    semantic = _load_semantic()
    bm25_mod = _load_bm25()
    entity_mod = _load_entity()
    semantic.index_file(file_path, _entry_text(entry, semantic_only=True))
    bm25_mod.index_file(file_path, _entry_text(entry))
    entity_mod.index_file(file_path, _entry_text(entry))


def _rebuild_all(store: str | None) -> dict[str, int]:
    common = _load_common()
    stale_paths = common.clean_stale(_all_indexed_paths(), store)
    for stale_path in stale_paths:
        for module in _signal_modules():
            module.remove_file(stale_path)
    semantic_stats = _load_semantic().rebuild(store)
    bm25_stats = _load_bm25().rebuild(store)
    entity_stats = _load_entity().rebuild(store)
    for file_path in common.list_entries(store):
        _refresh_related_links(file_path)
        _reindex_one(file_path)
    return {
        "semantic": int(semantic_stats.get("count", 0)),
        "bm25": int(bm25_stats.get("count", 0)),
        "entity": int(entity_stats.get("count", 0)),
        "removed": len(stale_paths),
    }


def _duplicate_candidates(top: int) -> list[tuple[str, float]]:
    return _search_candidates("", None, top)


def cmd_init(_args) -> None:
    common = _load_common()
    common.init(str(BASE_DIR))
    print("[OK] 初始化完成")
    print(f"- index: {BASE_DIR / 'index'}")
    print(f"- bug entries: {BASE_DIR / 'bug' / 'entries'}")
    print(f"- knowledge entries: {BASE_DIR / 'knowledge' / 'entries'}")
    missing = []
    try:
        import sentence_transformers  # noqa: F401
    except ModuleNotFoundError:
        missing.append("sentence-transformers")
    try:
        import jieba  # noqa: F401
    except ModuleNotFoundError:
        missing.append("jieba")
    if missing:
        print(f"[INFO] 缺少依赖：{', '.join(missing)}")
        print("[INFO] 可执行：pip install sentence-transformers jieba --break-system-packages")


def cmd_index(args) -> None:
    file_path = str(Path(args.file_path).resolve())
    path = Path(file_path)
    if not path.exists():
        print(f"[ERROR] 文件不存在：{file_path}", file=sys.stderr)
        sys.exit(1)
    _reindex_one(file_path)
    _refresh_related_links(file_path)
    _reindex_one(file_path)
    print(f"[OK] 索引：{file_path}")


def cmd_index_dir(args) -> None:
    stats = _rebuild_all(args.store)
    print(
        f"[OK] 重建完成：semantic={stats['semantic']} bm25={stats['bm25']} "
        f"entity={stats['entity']} removed={stats['removed']}"
    )


def cmd_search(args) -> None:
    common = _load_common()
    results = _search_candidates(args.query, args.store, args.top)
    if not results:
        print("[INFO] 索引库为空，请先执行 init 或 index-dir")
        return
    filtered_results = [(file_path, score) for file_path, score in results if score >= args.min_score]
    if not filtered_results:
        best_score = results[0][1]
        print(f"未找到相关条目（最高分 {best_score:.2f}，低于阈值 {args.min_score:.2f}）")
        return
    for file_path, score in filtered_results:
        meta = common.read_meta(file_path)
        store = _store_label(file_path, meta)
        title = meta.get("title") or Path(file_path).stem
        summary = meta.get("summary") or "无描述"
        print(f"[{score:.4f}] [{store}] {title} | {summary} | {file_path}")


def cmd_read(args) -> None:
    file_path = Path(args.file_path).resolve()
    if not file_path.exists():
        print(f"[ERROR] 文件不存在：{file_path}", file=sys.stderr)
        sys.exit(1)
    print(file_path.read_text(encoding="utf-8"))


def cmd_remove(args) -> None:
    file_path = str(Path(args.file_path).resolve())
    indexed_paths = set(_all_indexed_paths())
    if file_path not in indexed_paths:
        print(f"[INFO] 未找到索引记录：{file_path}", file=sys.stderr)
        return
    for module in _signal_modules():
        module.remove_file(file_path)
    print(f"[OK] 已删除索引：{file_path}")


def cmd_list(args) -> None:
    common = _load_common()
    entries = common.list_entries(args.store)
    if not entries:
        print("[INFO] 索引库为空")
        return
    for file_path in entries:
        meta = common.read_meta(file_path)
        title = meta.get("title") or Path(file_path).stem
        summary = meta.get("summary") or "无描述"
        print(f"{title} | {summary} | {file_path}")


def cmd_check(args) -> None:
    results = _search_candidates(args.text, args.store, 1)
    if not results:
        print("OK")
        return
    file_path, score = results[0]
    common = _load_common()
    meta = common.read_meta(file_path)
    title = meta.get("title") or Path(file_path).stem
    summary = meta.get("summary") or "无描述"
    if score > args.threshold:
        print(f"DUPLICATE [{score:.4f}] {title} | {summary} | {file_path}")
    elif score >= 0.7:
        print(f"RELATED [{score:.4f}] {title} | {summary} | {file_path}")
    else:
        print("OK")


def _pairwise_similarity(paths: list[str], threshold: float) -> list[tuple[float, str, str, str, str]]:
    semantic = _load_semantic()
    index = semantic._load_index()  # type: ignore[attr-defined]
    pairs = []
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            left = paths[i]
            right = paths[j]
            left_record = index.get(left)
            right_record = index.get(right)
            if not left_record or not right_record:
                continue
            score = semantic._cosine(left_record.get("embedding", []), right_record.get("embedding", []))  # type: ignore[attr-defined]
            if score <= threshold:
                continue
            pairs.append((score, left, right, left, right))
    pairs.sort(key=lambda item: item[0], reverse=True)
    return pairs


def cmd_dedup(args) -> None:
    common = _load_common()
    entries = common.list_entries(args.store)
    if not entries:
        print("[INFO] 索引库为空")
        return
    if len(entries) < args.min:
        print(f"[INFO] 当前条目数 {len(entries)}，未达到最小扫描数量 {args.min}")
        return
    pairs = _pairwise_similarity(entries, args.threshold)
    if not pairs:
        print(f"[INFO] 在阈值 {args.threshold} 下未发现相似对")
        return
    print(f"[DEDUP] 发现 {len(pairs)} 个相似对（阈值 {args.threshold}）：")
    for score, left_path, right_path, _, _ in pairs:
        left_meta = common.read_meta(left_path)
        right_meta = common.read_meta(right_path)
        left_title = left_meta.get("title") or Path(left_path).stem
        right_title = right_meta.get("title") or Path(right_path).stem
        print(f"  [{score:.4f}] {left_title} vs {right_title}")
        print(f"    A: {left_path}")
        print(f"    B: {right_path}")
    print(f"\n共 {len(pairs)} 对，请人工判断是否需要合并")


def cmd_entities(args) -> None:
    entity_mod = _load_entity()
    if args.name:
        entity_type, entries = entity_mod.entity_entries(args.name)
        if not entries:
            print(f"[INFO] 未找到实体：{args.name}")
            return
        print(f"[{entity_type}] {args.name} ({len(entries)}条关联)")
        for path in entries:
            print(f"  - {path}")
        return
    rows = entity_mod.list_entities()
    if not rows:
        print("[INFO] 实体索引为空")
        return
    for entity_type, name, count in rows:
        print(f"[{entity_type}] {name} ({count}条关联)")


def cmd_relate(args) -> None:
    file_path = str(Path(args.file_path).resolve())
    if not Path(file_path).exists():
        print(f"[ERROR] 文件不存在：{file_path}", file=sys.stderr)
        sys.exit(1)
    related = _load_entity().related_entries(file_path)
    if not related:
        print("[INFO] 未找到关联条目")
        return
    print("关联条目（通过共享实体）：")
    for entity_type, entity, path in related:
        print(f"  [{entity_type}:{entity}] {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="memory-base 三信号融合检索工具")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init", help="初始化目录结构和索引文件")

    p_index = sub.add_parser("index", help="索引单个文件")
    p_index.add_argument("file_path", help="md 文件路径")

    p_index_dir = sub.add_parser("index-dir", help="全量重建索引")
    p_index_dir.add_argument("--store", choices=["bug", "knowledge"], default=None, help="仅重建指定子库")

    p_search = sub.add_parser("search", help="融合检索")
    p_search.add_argument("query", help="检索词")
    p_search.add_argument("--store", choices=["bug", "knowledge"], default=None, help="仅搜索指定子库")
    p_search.add_argument("--top", type=int, default=3, help="返回条数")
    p_search.add_argument("--min-score", type=float, default=0.75, help="最低综合分阈值")

    p_check = sub.add_parser("check", help="写入前去重检查")
    p_check.add_argument("text", help="待检查的 title + summary 文本")
    p_check.add_argument("--store", choices=["bug", "knowledge"], default=None, help="仅检查指定子库")
    p_check.add_argument("--threshold", type=float, default=0.9, help="相似度阈值")

    p_dedup = sub.add_parser("dedup", help="全量相似对扫描")
    p_dedup.add_argument("--store", choices=["bug", "knowledge"], default=None, help="仅扫描指定子库")
    p_dedup.add_argument("--threshold", type=float, default=0.75, help="相似度阈值")
    p_dedup.add_argument("--min", type=int, default=20, help="条目数达到此值时才执行")

    p_read = sub.add_parser("read", help="读取文件内容")
    p_read.add_argument("file_path", help="文件路径")

    p_remove = sub.add_parser("remove", help="删除索引")
    p_remove.add_argument("file_path", help="文件路径")

    p_list = sub.add_parser("list", help="列出所有索引条目")
    p_list.add_argument("--store", choices=["bug", "knowledge", "entries"], default=None, help="仅列出指定子库")

    p_entities = sub.add_parser("entities", help="查看实体索引")
    p_entities.add_argument("name", nargs="?", help="实体名称")

    p_relate = sub.add_parser("relate", help="通过实体查找关联条目")
    p_relate.add_argument("file_path", help="条目路径")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "init":
        cmd_init(args)
    elif args.cmd == "index":
        cmd_index(args)
    elif args.cmd == "index-dir":
        cmd_index_dir(args)
    elif args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "dedup":
        cmd_dedup(args)
    elif args.cmd == "read":
        cmd_read(args)
    elif args.cmd == "remove":
        cmd_remove(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "entities":
        cmd_entities(args)
    elif args.cmd == "relate":
        cmd_relate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
