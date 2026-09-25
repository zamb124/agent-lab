/**
 * Доля релевантности из поля score сущности (контекст семантического поиска), 0–100 %.
 * Не путать с weight рёбер графа и с confidence ребра (уверенность в корректности связи).
 */

export function searchScorePercent(entity) {
    if (!entity || typeof entity.score !== 'number' || !Number.isFinite(entity.score)) {
        return null;
    }
    const raw = entity.score;
    const pct = raw <= 1 ? raw * 100 : raw;
    return Math.min(100, Math.max(0, pct));
}

/** Поле confidence связи из карточки/API, 0–100 % для полоски в соседях. */
export function relationshipConfidencePercent(rel) {
    if (!rel || typeof rel !== 'object' || typeof rel.confidence !== 'number' || !Number.isFinite(rel.confidence)) {
        return null;
    }
    const raw = rel.confidence;
    const pct = raw <= 1 ? raw * 100 : raw;
    return Math.min(100, Math.max(0, pct));
}
