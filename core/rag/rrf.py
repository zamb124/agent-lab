"""
Reciprocal Rank Fusion (RRF) для объединения ранжированных списков идентификаторов.

Используется в гибридном поиске pgvector (семантика + лексика).
"""


def reciprocal_rank_fusion(
    ranked_id_lists: list[list[str]],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    """
    Объединяет несколько списков id, упорядоченных по убыванию релевантности внутри канала.

    Для каждого списка rank начинается с 1 для лучшего элемента.
    Возвращает пары (id, rrf_score) по убыванию score.
    """
    if k <= 0:
        raise ValueError("k для RRF должен быть > 0")
    scores: dict[str, float] = {}
    for ranked in ranked_id_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))
