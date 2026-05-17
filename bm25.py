from __future__ import annotations

kwlist = [
    "False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue",
    "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import",
    "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
]
softkwlist = ["_", "case", "match", "type"]


def iskeyword(value: str) -> bool:
    return value in kwlist


def issoftkeyword(value: str) -> bool:
    return value in softkwlist


def _base_dir():
    from pathlib import Path

    return Path(__file__).resolve().parent


def _index_dir():
    return _base_dir() / "index"


def _bm25_path():
    return _index_dir() / "bm25.json"


def _jieba_cache_dir():
    return _index_dir() / "jieba_cache"


K1 = 1.5
B = 0.75


def _ensure_index_dir() -> None:
    _index_dir().mkdir(parents=True, exist_ok=True)
    _jieba_cache_dir().mkdir(parents=True, exist_ok=True)


def _get_jieba():
    import os

    _ensure_index_dir()
    os.environ.setdefault("JIEBA_CACHE_DIR", str(_jieba_cache_dir()))
    try:
        import jieba
    except ModuleNotFoundError:
        return None

    return jieba


def _fallback_tokenize(text: str) -> list[str]:
    import re

    return re.findall(r"[A-Za-z0-9_.+-]+|[一-鿿]+", text)


def _tokenize(text: str) -> list[str]:
    import re

    text = (text or "").strip()
    if not text:
        return []
    jieba = _get_jieba()
    if jieba is None:
        tokens = _fallback_tokenize(text)
    else:
        tokens = [token.strip() for token in jieba.lcut(text) if token.strip()]
    return [token for token in tokens if not re.fullmatch(r"\W+", token)]


def _load_index() -> dict[str, object]:
    import json

    bm25_path = _bm25_path()
    if not bm25_path.exists():
        return {"doc_count": 0, "avg_doc_len": 0.0, "documents": {}, "inverted_index": {}}
    try:
        with bm25_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"doc_count": 0, "avg_doc_len": 0.0, "documents": {}, "inverted_index": {}}
    data.setdefault("doc_count", 0)
    data.setdefault("avg_doc_len", 0.0)
    data.setdefault("documents", {})
    data.setdefault("inverted_index", {})
    return data


def _save_index(data: dict[str, object]) -> None:
    import json

    _ensure_index_dir()
    with _bm25_path().open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)


def _rebuild_from_documents(documents: dict[str, dict[str, object]]) -> dict[str, object]:
    from collections import Counter

    inverted: dict[str, list[dict[str, object]]] = {}
    total_len = 0
    for file_path, doc in documents.items():
        tokens = list(doc.get("tokens", []))
        doc_len = int(doc.get("doc_len", len(tokens)))
        total_len += doc_len
        counts = Counter(tokens)
        for term, tf in counts.items():
            inverted.setdefault(term, []).append({"file": file_path, "tf": tf, "doc_len": doc_len})
    doc_count = len(documents)
    avg_doc_len = (total_len / doc_count) if doc_count else 0.0
    return {
        "doc_count": doc_count,
        "avg_doc_len": avg_doc_len,
        "documents": documents,
        "inverted_index": inverted,
    }


def search(query: str, store: str | None, top: int) -> list[tuple[str, float]]:
    import math

    if top <= 0:
        return []
    data = _load_index()
    inverted = data.get("inverted_index", {})
    documents = data.get("documents", {})
    doc_count = int(data.get("doc_count", 0))
    avg_doc_len = float(data.get("avg_doc_len", 0.0))
    if not isinstance(inverted, dict) or not isinstance(documents, dict) or doc_count <= 0:
        return []
    scores: dict[str, float] = {}
    for term in _tokenize(query):
        postings = inverted.get(term, [])
        if not isinstance(postings, list) or not postings:
            continue
        df = len(postings)
        idf = math.log(1.0 + (doc_count - df + 0.5) / (df + 0.5))
        for posting in postings:
            if not isinstance(posting, dict):
                continue
            file_path = str(posting.get("file", ""))
            document = documents.get(file_path, {}) if isinstance(documents, dict) else {}
            if store and isinstance(document, dict) and document.get("store") != store:
                continue
            tf = float(posting.get("tf", 0))
            doc_len = float(posting.get("doc_len", 0))
            denom = tf + K1 * (1.0 - B + B * (doc_len / avg_doc_len if avg_doc_len else 0.0))
            if denom <= 0:
                continue
            score = idf * (tf * (K1 + 1.0) / denom)
            scores[file_path] = scores.get(file_path, 0.0) + score
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top]


def index_file(file_path: str, text: str) -> None:
    from pathlib import Path

    path = str(Path(file_path).resolve())
    tokens = _tokenize(text)
    documents = _load_index().get("documents", {})
    if not isinstance(documents, dict):
        documents = {}
    documents[path] = {
        "tokens": tokens,
        "doc_len": len(tokens),
        "store": _detect_store(path),
    }
    _save_index(_rebuild_from_documents(documents))


def remove_file(file_path: str) -> None:
    from pathlib import Path

    path = str(Path(file_path).resolve())
    data = _load_index()
    documents = data.get("documents", {})
    if isinstance(documents, dict) and path in documents:
        del documents[path]
        _save_index(_rebuild_from_documents(documents))


def rebuild(store: str | None) -> dict:
    from pathlib import Path

    data = _load_index()
    documents = data.get("documents", {})
    if not isinstance(documents, dict):
        documents = {}
    if store:
        documents = {
            path: doc
            for path, doc in documents.items()
            if not isinstance(doc, dict) or doc.get("store") != store
        }
    else:
        documents = {}
    count = 0
    for file_path in _list_entries(store):
        text = _entry_text(file_path)
        path = str(Path(file_path).resolve())
        tokens = _tokenize(text)
        documents[path] = {
            "tokens": tokens,
            "doc_len": len(tokens),
            "store": _detect_store(path),
        }
        count += 1
    _save_index(_rebuild_from_documents(documents))
    return {"count": count}


def _entry_text(file_path: str) -> str:
    from pathlib import Path

    common = _load_common_module()
    if common is not None:
        entry = common.read_entry(file_path)
        return "\n".join(
            part for part in [entry.get("title", ""), entry.get("summary", ""), entry.get("content", "")] if part
        )
    text = Path(file_path).read_text(encoding="utf-8")
    title, summary, content = _fallback_parse(text, file_path)
    return "\n".join(part for part in [title, summary, content] if part)


def _load_common_module():
    try:
        import common  # type: ignore
    except ModuleNotFoundError:
        return None
    return common


def _list_entries(store: str | None) -> list[str]:
    from pathlib import Path

    common = _load_common_module()
    if common is not None:
        return common.list_entries(store)
    roots: list[Path] = []
    base_dir = _base_dir()
    if store in (None, "all"):
        roots = [base_dir / "entries", base_dir / "bug" / "entries", base_dir / "knowledge" / "entries"]
    elif store == "bug":
        roots = [base_dir / "bug" / "entries"]
    elif store == "knowledge":
        roots = [base_dir / "knowledge" / "entries"]
    else:
        roots = [base_dir / store / "entries"]
    paths: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for file_path in sorted(root.glob("*.md")):
            paths.append(str(file_path.resolve()))
    return paths


def _detect_store(file_path: str) -> str:
    normalized = file_path.replace("\\", "/")
    if "/bug/entries/" in normalized:
        return "bug"
    if "/knowledge/entries/" in normalized:
        return "knowledge"
    return "entries"


def _fallback_parse(text: str, file_path: str) -> tuple[str, str, str]:
    from pathlib import Path

    title = Path(file_path).stem
    summary = ""
    content = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            content = parts[2].lstrip("\r\n")
            for line in frontmatter.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                if key == "title" and value:
                    title = value
                elif key == "summary" and value:
                    summary = value
    if not summary:
        summary = next((line.strip() for line in content.splitlines() if line.strip()), "无描述")
    return title, summary, content
