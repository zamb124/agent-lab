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
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { CrmGraphUiSlice } from '../crm.types.js';

const DEFAULT_PANELS = Object.freeze({
    search: true,
    timeline: true,
    legend: true,
    meta: true,
});

function applyPanels(state: CrmGraphUiSlice, payload: unknown): CrmGraphUiSlice {
    if (!isPlainRecord(payload) || !isPlainRecord(payload.panels)) return state;
    const panels = payload.panels;
    const next: Record<string, boolean> = { ...state.panels };
    for (const key of Object.keys(DEFAULT_PANELS)) {
        const value = panels[key];
        if (typeof value === 'boolean') {
            next[key] = value;
        }
    }
    return { ...state, panels: Object.freeze(next) };
}

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
    extraReducer: (state: CrmGraphUiSlice, event) => {
        switch (event.type) {
            case 'crm/graph_ui/panels_hydrated':
                return applyPanels(state, event.payload);
            case 'crm/graph_ui/panels_updated':
                return applyPanels(state, event.payload);
            case 'crm/graph_ui/timeline_seeded':
                return { ...state, timelineSeeded: true };
            default:
                return state;
        }
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/graph_ui': typeof graphUiSlice;
    }
}
