/**
 * CRM Graph UI — slice состояния только для UI экрана графа.
 *
 * Хранит:
 *   - panels: { search, timeline, legend, meta } — видимость overlay-панелей
 *     (persist через crm-persist.effect.js, ключ `crm.graph_ui.panels`).
 *   - timelineSeeded: boolean — флаг «дефолт-диапазон таймлайна посеян для
 *     текущей сессии» (раньше жил в sessionStorage).
 *
 * Мутации — только через actions слайс-контроллера (`useSlice('crm/graph_ui')`).
 */

import { createSlice } from '@platform/lib/events/index.js';

const DEFAULT_PANELS = Object.freeze({
    search: true,
    timeline: true,
    legend: true,
    meta: true,
});

export const graphUiSlice = createSlice({
    name: 'crm/graph_ui',
    extraInitial: {
        panels: DEFAULT_PANELS,
        timelineSeeded: false,
    },
    extraEvents: {
        PANELS_HYDRATED: 'panels_hydrated',
        PANELS_UPDATED: 'panels_updated',
        TIMELINE_SEEDED: 'timeline_seeded',
    },
    actions: {
        setPanels: 'panels_updated',
        hydratePanels: 'panels_hydrated',
        markTimelineSeeded: 'timeline_seeded',
    },
    extraReducer: (state, event) => {
        switch (event.type) {
            case 'crm/graph_ui/panels_hydrated': {
                const p = event.payload;
                if (!p || !p.panels || typeof p.panels !== 'object') return state;
                const next = { ...state.panels };
                for (const key of Object.keys(DEFAULT_PANELS)) {
                    if (typeof p.panels[key] === 'boolean') {
                        next[key] = p.panels[key];
                    }
                }
                return { ...state, panels: Object.freeze(next) };
            }
            case 'crm/graph_ui/panels_updated': {
                const p = event.payload;
                if (!p || !p.panels || typeof p.panels !== 'object') return state;
                const next = { ...state.panels };
                for (const key of Object.keys(DEFAULT_PANELS)) {
                    if (typeof p.panels[key] === 'boolean') {
                        next[key] = p.panels[key];
                    }
                }
                return { ...state, panels: Object.freeze(next) };
            }
            case 'crm/graph_ui/timeline_seeded':
                return { ...state, timelineSeeded: true };
            default:
                return state;
        }
    },
});
