"""Storage layer for memory-base refactor.

This module owns filesystem layout, markdown/frontmatter parsing, entry IO,
legacy entry enumeration, and term list management.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

MODULE_DIR = Path(__file__).resolve().parent
_BASE_DIR = MODULE_DIR

INDEX_DIR_NAME = "index"
BUG_STORE = "bug"
KNOWLEDGE_STORE = "knowledge"
LEGACY_STORE = "entries"
VALID_STORES = {BUG_STORE, KNOWLEDGE_STORE}
VALID_TERM_TYPES = {"tech", "project", "people"}

INDEX_FILES = {
    "vectors.pkl": b"",
    "bm25.json": b"{}\n",
    "entities.json": b"{}\n",
}

TERM_FILE_TEMPLATE = "terms_{term_type}.txt"
PRESEEDED_TECH_TERMS = [
    "AI",
    "Agent",
    "Anthropic",
    "API",
    "AppContainer",
    "Bash",
    "BM25",
    "Claude",
    "Claude Code",
    "CLI",
    "CSS",
    "Docker",
    "Embeddings",
    "FastAPI",
    "Git",
    "GitHub",
    "HTML",
    "JavaScript",
    "Junction",
    "JSON",
    "Linux",
    "Markdown",
    "Node.js",
    "npm",
    "NumPy",
    "Pathlib",
    "pickle",
    "PowerShell",
    "Python",
    "Regex",
    "Ripgrep",
    "SentenceTransformer",
    "Sentence Transformers",
    "SQLite",
    "Store App",
    "TypeScript",
    "UTF-8",
    "UWP",
    "vec.py",
    "WAL",
    "Windows",
    "YAML",
]


def init(base_dir: str) -> None:
    """Initialize directory structure, empty index files, and term lists."""
    global _BASE_DIR
    _BASE_DIR = Path(base_dir).resolve()

    _index_dir().mkdir(parents=True, exist_ok=True)
    _entries_dir(BUG_STORE).mkdir(parents=True, exist_ok=True)
    _entries_dir(KNOWLEDGE_STORE).mkdir(parents=True, exist_ok=True)

    for file_name, default_bytes in INDEX_FILES.items():
        path = _index_dir() / file_name
        if not path.exists():
            path.write_bytes(default_bytes)

    _ensure_terms_file("tech", PRESEEDED_TECH_TERMS)
    _ensure_terms_file("project", [])
    _ensure_terms_file("people", [])


def read_entry(file_path: str) -> dict:
    """Read one markdown entry and return metadata plus body content."""
    path = Path(file_path).resolve()
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    return {
        "title": meta.get("title") or path.stem,
        "summary": meta.get("summary", ""),
        "content": body,
        "env": meta.get("env", ""),
        "stability": meta.get("stability", ""),
        "store": _infer_store(path),
    }


def read_meta(file_path: str) -> dict:
    """Read only frontmatter-relevant fields from one markdown entry."""
    path = Path(file_path).resolve()
    raw = path.read_text(encoding="utf-8")
    meta, _ = _parse_frontmatter(raw)
    return {
        "title": meta.get("title") or path.stem,
        "summary": meta.get("summary", ""),
        "env": meta.get("env", ""),
        "stability": meta.get("stability", ""),
        "store": _infer_store(path),
    }


def write_entry(file_path: str, content: str) -> None:
    """Write entry content, creating parent directories when needed."""
    path = Path(file_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def list_entries(store: str | None) -> list[str]:
    """List entry markdown paths for one store or for all stores plus legacy entries."""
    stores = _normalize_store_selection(store)
    paths: list[Path] = []

    for store_name in stores:
        if store_name == LEGACY_STORE:
            legacy_dir = _legacy_entries_dir()
            if legacy_dir.exists():
                paths.extend(_iter_markdown_files(legacy_dir))
            continue

        entries_dir = _entries_dir(store_name)
        if entries_dir.exists():
            paths.extend(_iter_markdown_files(entries_dir))

    return [str(path.resolve()) for path in sorted(paths)]


def clean_stale(indexed_paths: list[str], store: str | None) -> list[str]:
    """Return indexed paths that no longer exist in the selected store scope."""
    allowed_roots = _allowed_roots_for_store(store)
    stale: list[str] = []

    for indexed_path in indexed_paths:
        path = Path(indexed_path).resolve()
        if allowed_roots and not _is_within_any(path, allowed_roots):
            continue
        if not path.exists():
            stale.append(str(path))

    return stale


def load_terms(term_type: str) -> list[str]:
    """Load one term list, stripping blank lines and inline auto markers."""
    normalized = _normalize_term_type(term_type)
    path = _term_file(normalized)
    if not path.exists():
        return []

    terms: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        terms.append(_strip_auto_marker(stripped))
    return terms


def append_term(term_type: str, term: str, auto: bool = False) -> None:
    """Append one term if it does not already exist in the term list."""
    normalized = _normalize_term_type(term_type)
    cleaned_term = term.strip()
    if not cleaned_term:
        return

    existing = {item.casefold() for item in load_terms(normalized)}
    if cleaned_term.casefold() in existing:
        return

    path = _term_file(normalized)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        _ensure_terms_file(normalized, PRESEEDED_TECH_TERMS if normalized == "tech" else [])

    line = f"{cleaned_term} # auto" if auto else cleaned_term
    prefix = "" if _file_is_empty(path) else "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{prefix}{line}")


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    text = raw.lstrip("﻿")
    if not text.startswith("---"):
        return {}, raw

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw

    frontmatter_lines: list[str] = []
    body_start_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start_index = index + 1
            break
        frontmatter_lines.append(line)

    if body_start_index is None:
        return {}, raw

    meta: dict[str, str] = {}
    current_key: str | None = None
    current_value_lines: list[str] = []

    for line in frontmatter_lines:
        if ":" in line and not line[:1].isspace():
            if current_key is not None:
                meta[current_key] = "\n".join(current_value_lines).strip()
            key, value = line.split(":", 1)
            current_key = key.strip()
            current_value_lines = [value.strip()]
        elif current_key is not None:
            current_value_lines.append(line.strip())

    if current_key is not None:
        meta[current_key] = "\n".join(current_value_lines).strip()

    body = "\n".join(lines[body_start_index:])
    if raw.endswith("\n"):
        body = f"{body}\n" if body else ""
    return meta, body


def _ensure_terms_file(term_type: str, initial_terms: list[str]) -> None:
    path = _term_file(term_type)
    if path.exists():
        return

    lines = [
        f"# {term_type} terms for memory-base entity extraction",
        "# One term per line.",
        "# Lines ending with '# auto' were added automatically.",
    ]
    if initial_terms:
        lines.append("")
        lines.extend(initial_terms)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _normalize_store_selection(store: str | None) -> list[str]:
    if store is None:
        return [BUG_STORE, KNOWLEDGE_STORE, LEGACY_STORE]
    normalized = store.strip().lower()
    if normalized == LEGACY_STORE:
        return [LEGACY_STORE]
    if normalized not in VALID_STORES:
        raise ValueError(f"Unsupported store: {store}")
    return [normalized]


def _allowed_roots_for_store(store: str | None) -> list[Path]:
    roots: list[Path] = []
    for store_name in _normalize_store_selection(store):
        if store_name == LEGACY_STORE:
            roots.append(_legacy_entries_dir().resolve())
        else:
            roots.append(_entries_dir(store_name).resolve())
    return roots


def _entries_dir(store: str) -> Path:
    normalized = store.strip().lower()
    if normalized not in VALID_STORES:
        raise ValueError(f"Unsupported store: {store}")
    return _base_dir() / normalized / "entries"


def _legacy_entries_dir() -> Path:
    return _base_dir() / LEGACY_STORE


def _index_dir() -> Path:
    return _base_dir() / INDEX_DIR_NAME


def _term_file(term_type: str) -> Path:
    return _index_dir() / TERM_FILE_TEMPLATE.format(term_type=term_type)


def _normalize_term_type(term_type: str) -> str:
    normalized = term_type.strip().lower()
    if normalized not in VALID_TERM_TYPES:
        raise ValueError(f"Unsupported term_type: {term_type}")
    return normalized


def _base_dir() -> Path:
    return _BASE_DIR.resolve()


def _iter_markdown_files(directory: Path) -> Iterable[Path]:
    return (path for path in directory.glob("*.md") if path.is_file())


def _is_within_any(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _strip_auto_marker(term_line: str) -> str:
    if term_line.endswith("# auto"):
        return term_line[: -len("# auto")].rstrip()
    return term_line


def _file_is_empty(path: Path) -> bool:
    return not path.exists() or path.stat().st_size == 0


def _infer_store(path: Path) -> str:
    lowered = [part.lower() for part in path.parts]
    if BUG_STORE in lowered:
        return BUG_STORE
    if KNOWLEDGE_STORE in lowered:
        return KNOWLEDGE_STORE
    return LEGACY_STORE


def _dump_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
