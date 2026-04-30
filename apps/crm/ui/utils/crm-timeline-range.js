/**
 * Минимальный выбранный интервал на шкале «Период» графа/mind map — 30 суток (в миллисекундах).
 */

export const CRM_TIMELINE_MIN_RANGE_MS = 30 * 24 * 60 * 60 * 1000;

/**
 * Доля шкалы 0–100, соответствующая минимуму CRM_TIMELINE_MIN_RANGE_MS.
 *
 * @param {number} minTs
 * @param {number} maxTs
 * @returns {number}
 */
export function timelineMinGapPercent(minTs, maxTs) {
    if (typeof minTs !== 'number' || typeof maxTs !== 'number' || !Number.isFinite(minTs) || !Number.isFinite(maxTs)) {
        throw new Error('timelineMinGapPercent: timestamps must be finite numbers');
    }
    const span = maxTs - minTs;
    if (span <= 0) {
        return 100;
    }
    if (span <= CRM_TIMELINE_MIN_RANGE_MS) {
        return 100;
    }
    return Math.min(100, (CRM_TIMELINE_MIN_RANGE_MS / span) * 100);
}

/**
 * Сжимает или сдвигает концы диапазона так, чтобы длительность была не короче минимума.
 *
 * @param {number} startPercent
 * @param {number} endPercent
 * @param {number} minTs
 * @param {number} maxTs
 * @returns {{ startPercent: number, endPercent: number }}
 */
export function clampTimelinePercents(startPercent, endPercent, minTs, maxTs) {
    let sp = Number(startPercent);
    let ep = Number(endPercent);
    if (!Number.isFinite(sp) || !Number.isFinite(ep)) {
        throw new Error('clampTimelinePercents: percents must be finite numbers');
    }
    sp = Math.max(0, Math.min(100, sp));
    ep = Math.max(0, Math.min(100, ep));
    if (ep < sp) {
        const tmp = sp;
        sp = ep;
        ep = tmp;
    }
    const gap = timelineMinGapPercent(minTs, maxTs);
    if (ep - sp >= gap) {
        return { startPercent: sp, endPercent: ep };
    }
    ep = Math.min(100, sp + gap);
    if (ep - sp >= gap) {
        return { startPercent: sp, endPercent: ep };
    }
    sp = Math.max(0, ep - gap);
    return { startPercent: sp, endPercent: ep };
}
