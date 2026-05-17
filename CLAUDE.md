# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

This repository contains a local `memory-base` skill for Claude Code. Today’s implementation is a single-file Python CLI in [`vec.py`](vec.py) that indexes and searches markdown knowledge entries with sentence-transformer embeddings stored in SQLite. The repo also includes the current skill contract in [`SKILL.md`](SKILL.md) and a target refactor/design document in [`memory-base-refactor-spec.md`](memory-base-refactor-spec.md).

## Core commands

### Run the CLI
- `python vec.py --help`
- `python vec.py search "<query>" --top 5`
- `python vec.py read <file_path>`
- `python vec.py index <file_path>`
- `python vec.py index-dir`
- `python vec.py check "<title + summary>" --threshold 0.9`
- `python vec.py dedup --threshold 0.75`
- `python vec.py list`
- `python vec.py remove <file_path>`

### Development checks
There is no dedicated test suite, linter, formatter, or build system in this repository right now.

Use these lightweight checks while developing:
- `python -m py_compile vec.py`
- `python vec.py --help`
- `python vec.py list`
- `python vec.py search "测试关键词" --top 3`

When changing CLI behavior, validate the specific subcommand you touched directly, since that is the closest thing to a single-test workflow in this repo. Example:
- `python vec.py search "SQLite WAL" --top 3`
- `python vec.py check "title + summary" --threshold 0.9`

## High-level architecture

### Current implementation
The current tool is centered in [`vec.py`](vec.py).

- CLI layer: `argparse` subcommands dispatch to `cmd_*` functions.
- Storage layer: SQLite database at `store.db` stores one row per indexed markdown file, including title, summary, embedding bytes, and source path.
- Embedding layer: `SentenceTransformer` with model `BAAI/bge-small-zh-v1.5` is loaded lazily via `get_model()`.
- Content model: only markdown files are indexed; metadata is read from YAML-like frontmatter.
- Source of truth for entries: the live implementation currently indexes markdown files under the top-level `entries/` directory, not `bug/entries/` or `knowledge/entries/`.

Important current data flow:
1. `index` / `index-dir` reads markdown files.
2. `extract_title_summary()` parses frontmatter and derives the text used for embeddings.
3. The embedding for `title + summary` is stored in SQLite.
4. `search` embeds the query and does an in-memory cosine similarity scan over all stored rows.
5. `read` prints the full markdown file after search identifies a relevant path.

### Key implementation details
- Frontmatter parsing is handwritten in [`vec.py`](vec.py); it is intentionally simple and assumes `key: value` lines.
- `index-dir` currently scans only `entries/*.md` in the repository-local `entries/` directory.
- The database is initialized on demand with WAL mode enabled.
- `cmd_search`, `cmd_check`, and `cmd_dedup` all load every stored embedding from SQLite and compute scores in Python rather than delegating vector search to an external system.
- `bug/` and `knowledge/` exist in the repo, but the current CLI does not query them directly; they matter more as part of the skill contract and planned architecture than the live indexing path.

## Documentation that defines behavior

### [`SKILL.md`](SKILL.md)
Treat this as the behavioral contract for how the skill is supposed to be used by Claude Code:
- when to search before acting
- how bug vs knowledge entries are categorized
- how new entries should be written, deduplicated, and indexed
- the expected two-step workflow of `search` first, `read` second

If code behavior and `SKILL.md` differ, call out the mismatch explicitly instead of silently assuming they are aligned.

### [`memory-base-refactor-spec.md`](memory-base-refactor-spec.md)
This is a forward-looking architecture spec, not the current implementation. It describes the intended split from one file into modules such as `semantic.py`, `keyword.py`, `entity.py`, `fusion.py`, and `storage.py`, plus a move toward three-signal retrieval.

Use it as design intent when implementing refactors, but verify behavior against the actual code in [`vec.py`](vec.py) before making claims about what already exists.

## Repository structure that matters
- [`vec.py`](vec.py): current production CLI and all live indexing/search logic.
- [`SKILL.md`](SKILL.md): operational rules for the skill.
- [`memory-base-refactor-spec.md`](memory-base-refactor-spec.md): target architecture and migration direction.
- [`entries/`](entries): directory actually indexed by `index-dir` in the current code.
- [`bug/entries/`](bug/entries) and [`knowledge/`](knowledge): content/layout related to the skill design, but not yet wired into the live CLI search path.
- [`.claude/settings.local.json`](.claude/settings.local.json): local permission tweaks for this workspace.

## Working assumptions for future edits
- Prefer preserving the current two-step retrieval workflow: search returns compact metadata, then `read` loads the full file.
- Be careful when changing path conventions: the code, skill doc, and refactor spec currently describe different directory layouts.
- If you refactor `vec.py`, keep command names and basic CLI ergonomics stable unless the skill contract is being updated too.
- If you add tests later, document the exact command here and update this file instead of adding generic guidance.
