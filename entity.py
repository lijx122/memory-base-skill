from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
INDEX_DIR = BASE_DIR / "index"
ENTITIES_PATH = INDEX_DIR / "entities.json"
TERM_TYPES = ("tech", "project", "people")
BACKTICK_RE = re.compile(r"`([^`]+)`")
UPPER_ENTITY_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9._+-]*)(?:\s+[A-Z][A-Za-z0-9._+-]*)*")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,6}\b")
PATH_RE = re.compile(r"(?:[A-Za-z]:/|/)?(?:[\w.-]+/)+[\w.-]+")
CJK_NAME_RE = re.compile(r"\b(?:老[一-鿿]{1,2}|[一-鿿]{2,4})\b")


def _ensure_index_dir() -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)


def _load_entities() -> dict[str, dict[str, Any]]:
    if not ENTITIES_PATH.exists():
        return {}
    try:
        with ENTITIES_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_entities(data: dict[str, dict[str, Any]]) -> None:
    _ensure_index_dir()
    serializable = {
        entity: {"type": record["type"], "entries": sorted(set(record.get("entries", [])))}
        for entity, record in sorted(data.items())
    }
    with ENTITIES_PATH.open("w", encoding="utf-8") as fh:
        json.dump(serializable, fh, ensure_ascii=False, indent=2, sort_keys=True)


def search(query: str, store: str | None, top: int) -> list[tuple[str, float]]:
    if top <= 0:
        return []
    data = _load_entities()
    if not data:
        return []
    scores: dict[str, float] = {}
    for entity, entity_type in _extract_entities(query):
        record = data.get(entity)
        if not record:
            continue
        weight = _type_weight(entity_type, query_side=True)
        for file_path in record.get("entries", []):
            if store and _detect_store(file_path) != store:
                continue
            scores[file_path] = scores.get(file_path, 0.0) + weight
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top]


def index_file(file_path: str, text: str) -> None:
    path = str(Path(file_path).resolve())
    data = _load_entities()
    _remove_path_from_entities(data, path)
    for entity, entity_type in _extract_entities(text):
        record = data.setdefault(entity, {"type": entity_type, "entries": []})
        if not record.get("type"):
            record["type"] = entity_type
        elif record["type"] != entity_type and record["type"] != "tech":
            record["type"] = entity_type
        if path not in record["entries"]:
            record["entries"].append(path)
    _save_entities(data)


def remove_file(file_path: str) -> None:
    path = str(Path(file_path).resolve())
    data = _load_entities()
    if not data:
        return
    _remove_path_from_entities(data, path)
    _save_entities(data)


def rebuild(store: str | None) -> dict:
    data = _load_entities()
    if store:
        target_store = store
        for entity in list(data.keys()):
            kept = [path for path in data[entity].get("entries", []) if _detect_store(path) != target_store]
            if kept:
                data[entity]["entries"] = kept
            else:
                del data[entity]
    else:
        data = {}
    count = 0
    for file_path in _list_entries(store):
        path = str(Path(file_path).resolve())
        text = _entry_text(file_path)
        for entity, entity_type in _extract_entities(text):
            record = data.setdefault(entity, {"type": entity_type, "entries": []})
            if path not in record["entries"]:
                record["entries"].append(path)
        count += 1
    _save_entities(data)
    return {"count": count}


def related_entries(file_path: str) -> list[tuple[str, str, str]]:
    path = str(Path(file_path).resolve())
    text = _entry_text(path)
    data = _load_entities()
    seen: set[tuple[str, str, str]] = set()
    related: list[tuple[str, str, str]] = []
    for entity, entity_type in _extract_entities(text):
        record = data.get(entity)
        if not record:
            continue
        for candidate in record.get("entries", []):
            candidate_path = str(Path(candidate).resolve())
            if candidate_path == path:
                continue
            item = (entity_type, entity, candidate_path)
            if item in seen:
                continue
            seen.add(item)
            related.append(item)
    related.sort(key=lambda item: (item[0], item[1], item[2]))
    return related


def list_entities() -> list[tuple[str, str, int]]:
    data = _load_entities()
    rows = []
    for entity, record in sorted(data.items()):
        rows.append((str(record.get("type", "tech")), entity, len(record.get("entries", []))))
    return rows


def entity_entries(name: str) -> tuple[str | None, list[str]]:
    data = _load_entities()
    record = data.get(name)
    if not record:
        return None, []
    return str(record.get("type", "tech")), sorted(str(path) for path in record.get("entries", []))


def _remove_path_from_entities(data: dict[str, dict[str, Any]], file_path: str) -> None:
    for entity in list(data.keys()):
        entries = [path for path in data[entity].get("entries", []) if path != file_path]
        if entries:
            data[entity]["entries"] = entries
        else:
            del data[entity]


def _extract_entities(text: str) -> list[tuple[str, str]]:
    ordered: dict[str, str] = {}
    terms = {term_type: _load_terms(term_type) for term_type in TERM_TYPES}
    for term_type, values in terms.items():
        for value in values:
            if value and value.lower() in text.lower():
                ordered.setdefault(value, term_type)
    for match in BACKTICK_RE.findall(text):
        entity = _clean_entity(match)
        if entity:
            ordered.setdefault(entity, "tech")
            _auto_append("tech", entity, terms)
    for match in PATH_RE.findall(text):
        entity = _clean_entity(match)
        if entity:
            ordered.setdefault(entity, "tech")
            _auto_append("tech", entity, terms)
    for match in UPPER_ENTITY_RE.findall(text):
        entity = _clean_entity(match)
        if entity and _is_meaningful_entity(entity):
            ordered.setdefault(entity, "tech")
            _auto_append("tech", entity, terms)
    for match in ACRONYM_RE.findall(text):
        entity = _clean_entity(match)
        if entity:
            ordered.setdefault(entity, "tech")
            _auto_append("tech", entity, terms)
    for match in CJK_NAME_RE.findall(text):
        entity = _clean_entity(match)
        if entity and entity not in ordered and len(entity) <= 4:
            ordered[entity] = "people"
            _auto_append("people", entity, terms)
    return list(ordered.items())


def _type_weight(entity_type: str, query_side: bool = False) -> float:
    weights = {"tech": 1.0, "project": 0.9, "people": 0.8}
    base = weights.get(entity_type, 0.7)
    return base if query_side else 1.0


def _clean_entity(value: str) -> str:
    return value.strip().strip("`[](){}'\".,;:!?")


def _is_meaningful_entity(value: str) -> bool:
    if len(value) <= 1:
        return False
    if value.lower() in {"the", "and", "for", "with", "from"}:
        return False
    return True


def _load_terms(term_type: str) -> list[str]:
    common = _load_common_module()
    if common is not None:
        return common.load_terms(term_type)
    path = INDEX_DIR / f"terms_{term_type}.txt"
    if not path.exists():
        return []
    values: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.split("#", 1)[0].strip()
        if item:
            values.append(item)
    return values


def _append_term(term_type: str, term: str, auto: bool = False) -> None:
    common = _load_common_module()
    if common is not None:
        common.append_term(term_type, term, auto=auto)
        return
    _ensure_index_dir()
    path = INDEX_DIR / f"terms_{term_type}.txt"
    existing = set(_load_terms(term_type))
    if term in existing:
        return
    suffix = " # auto" if auto else ""
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{term}{suffix}\n")


def _auto_append(term_type: str, term: str, terms: dict[str, list[str]]) -> None:
    if term_type not in terms:
        return
    if term in terms[term_type]:
        return
    _append_term(term_type, term, auto=True)
    terms[term_type].append(term)


def _entry_text(file_path: str) -> str:
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
        summary = next((line.strip() for line in content.splitlines() if line.strip()), "无描述")
    return title, summary, content
