from __future__ import annotations

import math
import pickle
from pathlib import Path
from typing import Any

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
INDEX_DIR = BASE_DIR / "index"
VECTORS_PATH = INDEX_DIR / "vectors.pkl"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
_model = None


def _ensure_index_dir() -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)


def _load_index() -> dict[str, dict[str, Any]]:
    if not VECTORS_PATH.exists():
        return {}
    try:
        with VECTORS_PATH.open("rb") as fh:
            data = pickle.load(fh)
    except (OSError, pickle.PickleError, EOFError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_index(data: dict[str, dict[str, Any]]) -> None:
    _ensure_index_dir()
    with VECTORS_PATH.open("wb") as fh:
        pickle.dump(data, fh)


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _encode(text: str) -> list[float]:
    vector = _get_model().encode(text or "", normalize_embeddings=True)
    return np.asarray(vector, dtype=np.float32).tolist()


def _cosine(query_vec: list[float], doc_vec: list[float]) -> float:
    if not query_vec or not doc_vec or len(query_vec) != len(doc_vec):
        return 0.0
    return float(np.dot(np.asarray(query_vec, dtype=np.float32), np.asarray(doc_vec, dtype=np.float32)))


def search(query: str, store: str | None, top: int) -> list[tuple[str, float]]:
    if top <= 0:
        return []
    index = _load_index()
    if not index:
        return []
    query_vec = _encode(query)
    scored: list[tuple[str, float]] = []
    for file_path, record in index.items():
        if store and record.get("store") != store:
            continue
        score = _cosine(query_vec, record.get("embedding", []))
        if math.isnan(score):
            continue
        scored.append((file_path, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top]


def index_file(file_path: str, text: str) -> None:
    index = _load_index()
    path = str(Path(file_path).resolve())
    index[path] = {
        "embedding": _encode(text),
        "store": _detect_store(path),
    }
    _save_index(index)


def remove_file(file_path: str) -> None:
    index = _load_index()
    path = str(Path(file_path).resolve())
    if path in index:
        del index[path]
        _save_index(index)


def rebuild(store: str | None) -> dict:
    index = _load_index()
    target_store = store
    if target_store:
        index = {
            path: record
            for path, record in index.items()
            if record.get("store") != target_store
        }
    else:
        index = {}
    count = 0
    for file_path in _list_entries(store):
        text = _entry_text(file_path, semantic_only=True)
        index[str(Path(file_path).resolve())] = {
            "embedding": _encode(text),
            "store": _detect_store(file_path),
        }
        count += 1
    _save_index(index)
    return {"count": count}


def _entry_text(file_path: str, semantic_only: bool = False) -> str:
    common = _load_common_module()
    if common is not None:
        entry = common.read_entry(file_path)
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        if semantic_only:
            return f"{title}。{summary}".strip("。 ")
        content = entry.get("content", "")
        return "\n".join(part for part in [title, summary, content] if part)
    text = Path(file_path).read_text(encoding="utf-8")
    title, summary, content = _fallback_parse(text, file_path)
    if semantic_only:
        return f"{title}。{summary}".strip("。 ")
    return "\n".join(part for part in [title, summary, content] if part)


def _load_common_module():
    try:
        import common  # type: ignore
    except ModuleNotFoundError:
        return None
    return common


def _list_entries(store: str | None) -> list[str]:
    common = _load_common_module()
    if common is not None:
        return common.list_entries(store)
    roots: list[Path] = []
    if store in (None, "all"):
        roots = [BASE_DIR / "entries", BASE_DIR / "bug" / "entries", BASE_DIR / "knowledge" / "entries"]
    elif store == "bug":
        roots = [BASE_DIR / "bug" / "entries"]
    elif store == "knowledge":
        roots = [BASE_DIR / "knowledge" / "entries"]
    else:
        roots = [BASE_DIR / store / "entries"]
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
        first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
        summary = first_line or "无描述"
    return title, summary, content
