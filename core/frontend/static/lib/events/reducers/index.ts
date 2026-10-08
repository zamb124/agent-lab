/**
 * Корневой reducer платформенного ядра.
 *
 * combineReducers(slices) — собирает состояние по доменам. Сервисные слайсы
 * (crm, flows, sync, ...) добавляются через `extendRootReducer(slices)` ДО
 * создания EventBus в bootstrap'е приложения.
 */

import type { PlatformEvent } from '../contract.js';
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
import { mailSlice } from './mail.js';
import { notificationsSlice } from './notifications.js';
import { uiSlice } from './ui.js';
import { bottomSheetsSlice } from './bottom_sheets.js';

export const coreSlices = Object.freeze({
    auth:          { reducer: authReducer, initial: initialAuthState },
    theme:         { reducer: themeReducer, initial: initialThemeState },
    i18n:          { reducer: i18nReducer, initial: initialI18nState },
    notify:        { reducer: notifyReducer, initial: initialNotifyState },
    modals:        { reducer: modalsReducer, initial: initialModalsState },
    bottomSheets:  bottomSheetsSlice,
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
    mail:          mailSlice,
    notifications: notificationsSlice,
});

/**
 * Собрать единый reducer и initialState из набора слайсов.
 *
 * @param {Object<string, {reducer: Function, initial: any}>} slices
 * @returns {{ reducer: (state: object, event: object) => object, initialState: object }}
 */
export interface SliceDef<S = unknown> {
    reducer: (state: S, event: PlatformEvent) => S;
    initial: S;
}

type SliceMap = Record<string, SliceDef>;
type StateOf<T extends SliceMap> = { [K in keyof T]: ReturnType<T[K]['reducer']> };

export function combineReducers<T extends SliceMap>(slices: T): {
    reducer: (state: StateOf<T>, event: PlatformEvent) => StateOf<T>;
    initialState: StateOf<T>;
} {
    const keys = Object.keys(slices) as Array<keyof T>;
    const initialState = {} as Record<string, unknown>;
    for (const key of keys) {
        initialState[key as string] = (slices[key] as SliceDef).initial;
    }

    function rootReducer(state: Record<string, unknown>, event: PlatformEvent): Record<string, unknown> {
        let changed = false;
        const next: Record<string, unknown> = {};
        for (const key of keys) {
            const prev = state[key as string];
            const slice = (slices[key] as SliceDef).reducer(prev, event);
            next[key as string] = slice;
            if (slice !== prev) changed = true;
        }
        return changed ? next : state;
    }

    return { reducer: rootReducer as (state: StateOf<T>, event: PlatformEvent) => StateOf<T>, initialState: initialState as StateOf<T> };
}

/**
 * Сборка root reducer из core slices плюс набор сервисных.
 */
export function buildPlatformReducer<T extends SliceMap>(extraSlices: T = {} as T): {
    reducer: (state: StateOf<typeof coreSlices & T>, event: PlatformEvent) => StateOf<typeof coreSlices & T>;
    initialState: StateOf<typeof coreSlices & T>;
} {
    const all = { ...coreSlices, ...extraSlices };
    return combineReducers(all) as ReturnType<typeof buildPlatformReducer<T>>;
}
