/**
 * CRM Daily Notes UI — UI-only slice состояния экрана «ежедневник».
 *
 * Хранит выбранный диапазон дат `range: { from, to }` (ISO YYYY-MM-DD).
 * Persist выполняет `crm-persist.effect.js` (ключ `crm.daily_notes.range`).
 *
 * Дефолтный диапазон — последние 7 дней включая сегодня. Дефолт каноничен и
 * живёт только здесь — никаких fallback в pages.
 */

import { createSlice } from '@platform/lib/events/index.js';

const DEFAULT_RANGE_DAYS = 7;

function _formatIsoDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function _defaultRange() {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - (DEFAULT_RANGE_DAYS - 1));
    return Object.freeze({ from: _formatIsoDate(from), to: _formatIsoDate(to) });
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export const dailyNotesUiSlice = createSlice({
    name: 'crm/daily_notes_ui',
    extraInitial: {
        range: _defaultRange(),
    },
    extraEvents: {
        RANGE_HYDRATED: 'range_hydrated',
        RANGE_UPDATED: 'range_updated',
    },
    actions: {
        setRange: 'range_updated',
        hydrateRange: 'range_hydrated',
    },
    extraReducer: (state, event) => {
        switch (event.type) {
            case 'crm/daily_notes_ui/range_hydrated':
            case 'crm/daily_notes_ui/range_updated': {
                const p = event.payload;
                if (!p || typeof p.from !== 'string' || typeof p.to !== 'string') return state;
                if (!ISO_DATE_RE.test(p.from) || !ISO_DATE_RE.test(p.to)) return state;
                const next = Object.freeze({ from: p.from, to: p.to });
                return { ...state, range: next };
            }
            default:
                return state;
        }
    },
});
