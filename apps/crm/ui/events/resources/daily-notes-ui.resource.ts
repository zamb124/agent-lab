/**
 * CRM Daily Notes UI — slice состояния только для UI экрана «ежедневник».
 *
 * Хранит выбранный диапазон дат `range: { from, to }` (ISO YYYY-MM-DD).
 *
 * Стартовый диапазон пересчитывает daily-notes-page по последним 50 заметкам.
 */

import { createSlice } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { CrmDailyNotesUiSlice } from '../crm.types.js';

function _formatIsoDate(d: Date) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function _defaultRange() {
    const to = new Date();
    const from = new Date();
    to.setDate(to.getDate() + 1);
    return Object.freeze({ from: _formatIsoDate(from), to: _formatIsoDate(to) });
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export const dailyNotesUiSlice = createSlice({
    name: 'crm/daily_notes_ui',
    extraInitial: {
        range: _defaultRange(),
    },
    extraEvents: {
        RANGE_UPDATED: 'range_updated',
    },
    actions: {
        setRange: 'range_updated',
    },
    extraReducer: (state: CrmDailyNotesUiSlice, event) => {
        switch (event.type) {
            case 'crm/daily_notes_ui/range_updated': {
                const p = event.payload;
                if (!isPlainRecord(p)) return state;
                const from = p.from;
                const to = p.to;
                if (typeof from !== 'string' || typeof to !== 'string') return state;
                if (!ISO_DATE_RE.test(from) || !ISO_DATE_RE.test(to)) return state;
                const next = Object.freeze({ from, to });
                return { ...state, range: next };
            }
            default:
                return state;
        }
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/daily_notes_ui': typeof dailyNotesUiSlice;
    }
}
