from __future__ import annotations

from typing import Iterable


def merge(results: list[list[tuple[str, float]]], weights: list[float], top: int) -> list[tuple[str, float]]:
    if top <= 0:
        return []
    if len(results) != 3:
        raise ValueError("merge expects exactly three result sets: semantic, bm25, entity")
    if len(weights) != 3:
        raise ValueError("merge expects exactly three weights")

    combined: dict[str, float] = {}
    for result_set, weight in zip(results, weights, strict=True):
        normalized = _normalize(result_set)
        for file_path, score in normalized:
            combined[file_path] = combined.get(file_path, 0.0) + score * weight

    ranked = sorted(combined.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top]


def _normalize(result_set: Iterable[tuple[str, float]]) -> list[tuple[str, float]]:
    items = list(result_set)
    if not items:
        return []
    scores = [score for _, score in items]
    max_score = max(scores)
    min_score = min(scores)
    if max_score == min_score:
        if max_score <= 0:
            return [(file_path, 0.0) for file_path, _ in items]
        return [(file_path, 1.0) for file_path, _ in items]
    span = max_score - min_score
    return [(file_path, (score - min_score) / span) for file_path, score in items]
