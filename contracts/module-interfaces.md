# Module Interfaces Contract

## Scope
This contract defines the implementation boundary for the refactor from single-file `vec.py` to:
- `vec.py`
- `semantic.py`
- `bm25.py`
- `entity.py`
- `fusion.py`
- `common.py`

Rules frozen by this contract:
- Keep existing CLI command names: `search`, `read`, `index`, `index-dir`, `check`, `list`, `remove`, `dedup`
- Add only: `init`, `entities`, `relate`
- Preserve two-step retrieval: `search` returns compact metadata; `read` returns full file content
- Do not modify `SKILL.md`
- Do not modify or delete existing files under `bug/entries/` and `knowledge/entries/` during migration

## Shared types

```python
from typing import Literal, TypedDict

StoreName = Literal["bug", "knowledge"]
SignalResult = list[tuple[str, float]]

class EntryMeta(TypedDict, total=False):
    title: str
    summary: str
    env: str
    stability: str
    store: StoreName

class EntryDocument(EntryMeta, total=False):
    content: str

class RebuildStats(TypedDict, total=False):
    count: int
    removed: int
    terms: int
    entities: int
```

## Signal module contract
Implemented independently by `semantic.py`, `bm25.py`, and `entity.py`.

```python
def search(query: str, store: str | None, top: int) -> SignalResult:
    """Return [(file_path, score)] sorted by descending score.

    Inputs:
    - query: raw user query
    - store: None | "bug" | "knowledge"
    - top: positive integer limit

    Output constraints:
    - file_path must be repo-local entry paths
    - score must be numeric and sortable descending
    - missing index should return [] rather than crash
    """


def index_file(file_path: str, text: str) -> None:
    """Index one entry.

    text source:
    - semantic: title + summary
    - keyword/entity: title + summary + content
    """


def remove_file(file_path: str) -> None:
    """Remove one entry from this signal index. No error if absent."""


def rebuild(store: str | None) -> RebuildStats:
    """Rebuild this signal index from storage.list_entries(store)."""
```

Signal-specific constraints:
- `semantic.py`: only module allowed to import `sentence_transformers`; import lazily
- `bm25.py`: only module allowed to import `jieba`; import lazily and use `index/jieba_cache/`
- `entity.py`: standard library only; maintain `index/entities.json` plus term-file append behavior

## Fusion contract

```python
def merge(results: list[SignalResult], weights: list[float], top: int) -> SignalResult:
    """Normalize each signal to [0, 1], apply weights, merge by file_path,
    keep highest final score per path, sort descending, and return top N."""
```

Constraints:
- exactly three input result sets in signal order: semantic, keyword, entity
- default weights in `vec.py`: `[0.5, 0.3, 0.2]`
- `fusion.py` performs no file IO, no imports from heavy dependencies

## Common contract

```python
def init(base_dir: str) -> None:
    """Create index/, bug/entries/, knowledge/entries/ and initial term files.
    If entries already exist, preserve them and only prepare/rebuild indexes."""


def read_entry(file_path: str) -> EntryDocument:
    """Return title, summary, content, env, stability, store."""


def read_meta(file_path: str) -> EntryMeta:
    """Return frontmatter-only metadata for compact search output."""


def write_entry(file_path: str, content: str) -> None:
    """Write one markdown entry file."""


def list_entries(store: str | None) -> list[str]:
    """Return all markdown entry file paths for one store or both."""


def clean_stale(indexed_paths: list[str], store: str | None) -> list[str]:
    """Return paths removed from indexes because files no longer exist."""


def load_terms(term_type: str) -> list[str]:
    """Load terms from index/terms_tech.txt, terms_project.txt, or terms_people.txt."""


def append_term(term_type: str, term: str, auto: bool = False) -> None:
    """Append a term; add '# auto' suffix when auto=True."""
```

Constraints:
- `common.py` owns path conventions and frontmatter parsing
- `common.py` must treat missing optional fields as empty, not fatal
- `common.py` must preserve existing entry file contents unless explicitly asked to write
- `common.py` exists intentionally as a shared utility module so signal modules can reuse entry traversal, frontmatter parsing, store rules, and term management without depending on `vec.py`

## vec.py orchestration contract

`vec.py` is the only CLI entrypoint.

Responsibilities:
- parse arguments
- route to storage/signal/fusion functions
- preserve compact output format for `search`
- preserve full-content output for `read`
- keep Windows UTF-8 stdout/stderr compatibility

Non-responsibilities:
- no embedding logic
- no BM25 logic
- no entity extraction rules
- no raw filesystem traversal beyond calling `common.py`

## Error-handling contract
- Missing optional index files: rebuildable condition, not fatal for read/list
- Unsupported store value: CLI validation error
- Missing entry file on `read/index/remove`: user-facing message with non-zero exit
- Signal failure must not silently corrupt other indexes

## Validation targets
At minimum the implementation must support these checks after refactor:
- `python -m py_compile vec.py`
- `python vec.py --help`
- `python vec.py list`
- `python vec.py search "测试关键词" --top 3`
- touched subcommands from the refactor spec: `init`, `entities`, `relate`, `index-dir`, `check`
