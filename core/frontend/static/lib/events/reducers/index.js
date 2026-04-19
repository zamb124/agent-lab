/**
 * Корневой reducer платформенного ядра.
 *
 * combineReducers(slices) — собирает состояние по доменам. Сервисные слайсы
 * (crm, flows, sync, ...) добавляются через `extendRootReducer(slices)` ДО
 * создания EventBus в bootstrap'е приложения.
 */

import { authReducer, initialAuthState } from './auth.js';
import { themeReducer, initialThemeState } from './theme.js';
import { i18nReducer, initialI18nState } from './i18n.js';
import { notifyReducer, initialNotifyState } from './notify.js';
import { modalsReducer, initialModalsState } from './modals.js';
import { networkReducer, initialNetworkState } from './network.js';
import { routerReducer, initialRouterState } from './router.js';
import { pwaReducer, initialPwaState } from './pwa.js';
import { iconSlice } from './icon.js';
import { fileTypesSlice } from './file-types.js';
import { filesSlice } from './files.js';
import { companiesSlice } from './companies.js';
import { teamSlice } from './team.js';
import { calendarSlice } from './calendar.js';
import { notificationsSlice } from './notifications.js';
import { uiSlice } from './ui.js';

export const coreSlices = Object.freeze({
    auth:          { reducer: authReducer, initial: initialAuthState },
    theme:         { reducer: themeReducer, initial: initialThemeState },
    i18n:          { reducer: i18nReducer, initial: initialI18nState },
    notify:        { reducer: notifyReducer, initial: initialNotifyState },
    modals:        { reducer: modalsReducer, initial: initialModalsState },
    network:       { reducer: networkReducer, initial: initialNetworkState },
    router:        { reducer: routerReducer, initial: initialRouterState },
    pwa:           { reducer: pwaReducer, initial: initialPwaState },
    ui:            uiSlice,
    icon:          iconSlice,
    fileTypes:     fileTypesSlice,
    files:         filesSlice,
    companies:     companiesSlice,
    team:          teamSlice,
    calendar:      calendarSlice,
    notifications: notificationsSlice,
});

/**
 * Собрать единый reducer и initialState из набора слайсов.
 *
 * @param {Object<string, {reducer: Function, initial: any}>} slices
 * @returns {{ reducer: (state: object, event: object) => object, initialState: object }}
 */
export function combineReducers(slices) {
    const keys = Object.keys(slices);
    const initialState = {};
    for (const key of keys) {
        initialState[key] = slices[key].initial;
    }

    function rootReducer(state, event) {
        let changed = false;
        const next = {};
        for (const key of keys) {
            const prev = state[key];
            const slice = slices[key].reducer(prev, event);
            next[key] = slice;
            if (slice !== prev) changed = true;
        }
        return changed ? next : state;
    }

    return { reducer: rootReducer, initialState };
}

/**
 * Сборка root reducer из core slices плюс набор сервисных.
 */
export function buildPlatformReducer(extraSlices = {}) {
    const all = { ...coreSlices, ...extraSlices };
    return combineReducers(all);
}
