/**
 * Корневой reducer платформенного ядра.
 *
 * combineReducers(slices) — собирает состояние по доменам. Сервисные слайсы
 * (crm, flows, sync, ...) добавляются через `extendRootReducer(slices)` ДО
 * создания EventBus в bootstrap'е приложения.
 */

import type { PlatformEvent } from '../contract.js';
import type { PlatformBusState } from '../bus-state.js';
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
// reducer — метод: фабрики с разными S собираются в одну коллекцию (бивариантность параметров метода).
export interface SliceDef<S = unknown> {
    reducer(state: S, event: PlatformEvent): S;
    initial: S;
}

type SliceMap = Record<string, SliceDef>;
type StateOf<T extends SliceMap> = { [K in keyof T]: ReturnType<T[K]['reducer']> };
type SliceKey<T extends SliceMap> = Extract<keyof T, string>;

function ownedSliceKeys<T extends SliceMap>(slices: T): SliceKey<T>[] {
    return Object.keys(slices).filter((key): key is SliceKey<T> => Object.prototype.hasOwnProperty.call(slices, key));
}

function isCombinedState<T extends SliceMap>(value: Record<string, unknown>, slices: T): value is StateOf<T> {
    return ownedSliceKeys(slices).every((key) => Object.prototype.hasOwnProperty.call(value, key));
}

function requireSlice<T extends SliceMap>(slices: T, key: SliceKey<T>): SliceDef {
    const slice = slices[key];
    if (slice === undefined) {
        throw new Error(`combineReducers: slice "${key}" missing`);
    }
    return slice;
}

export function combineReducers<T extends SliceMap>(slices: T): {
    reducer: (state: StateOf<T>, event: PlatformEvent) => StateOf<T>;
    initialState: StateOf<T>;
} {
    const keys = ownedSliceKeys(slices);
    const initialState: Record<string, unknown> = {};
    for (const key of keys) {
        initialState[key] = requireSlice(slices, key).initial;
    }
    if (!isCombinedState(initialState, slices)) {
        throw new Error('combineReducers: initial state is missing a slice');
    }

    function rootReducer(state: StateOf<T>, event: PlatformEvent): StateOf<T> {
        let changed = false;
        const next: Record<string, unknown> = {};
        for (const key of keys) {
            const prev = state[key];
            const reduced = requireSlice(slices, key).reducer(prev, event);
            next[key] = reduced;
            if (reduced !== prev) changed = true;
        }
        if (!changed) return state;
        if (!isCombinedState(next, slices)) {
            throw new Error('combineReducers: next state is missing a slice');
        }
        return next;
    }

    return { reducer: rootReducer, initialState };
}

function sliceAt(slices: SliceMap, key: string): SliceDef {
    const slice = slices[key];
    if (slice === undefined) {
        throw new Error(`buildPlatformReducer: slice "${key}" missing`);
    }
    return slice;
}

/**
 * Сборка root reducer из core slices плюс набор сервисных.
 * Сервисные слайсы подключаются списком фабрик во время старта, поэтому
 * их ключи остаются в индексной части `PlatformBusState`.
 */
export function buildPlatformReducer(extraSlices: SliceMap = {}): {
    reducer: (state: PlatformBusState, event: PlatformEvent) => PlatformBusState;
    initialState: PlatformBusState;
} {
    for (const key of Object.keys(extraSlices)) {
        if (Object.hasOwn(coreSlices, key)) {
            throw new Error(`buildPlatformReducer: extra slice "${key}" replaces a core slice`);
        }
    }
    const slices: SliceMap = { ...coreSlices, ...extraSlices };
    const initialState: PlatformBusState = {
        auth: coreSlices.auth.initial,
        theme: coreSlices.theme.initial,
        i18n: coreSlices.i18n.initial,
        notify: coreSlices.notify.initial,
        modals: coreSlices.modals.initial,
        bottomSheets: coreSlices.bottomSheets.initial,
        network: coreSlices.network.initial,
        router: coreSlices.router.initial,
        pwa: coreSlices.pwa.initial,
        ui: coreSlices.ui.initial,
        icon: coreSlices.icon.initial,
        fileTypes: coreSlices.fileTypes.initial,
        files: coreSlices.files.initial,
        companies: coreSlices.companies.initial,
        team: coreSlices.team.initial,
        calendar: coreSlices.calendar.initial,
        mail: coreSlices.mail.initial,
        notifications: coreSlices.notifications.initial,
    };
    for (const key of Object.keys(extraSlices)) {
        initialState[key] = sliceAt(extraSlices, key).initial;
    }
    const keys = Object.keys(slices);

    function reducer(state: PlatformBusState, event: PlatformEvent): PlatformBusState {
        let changed = false;
        const next: PlatformBusState = { ...state };
        for (const key of keys) {
            const prev = state[key];
            const reduced = sliceAt(slices, key).reducer(prev, event);
            if (reduced !== prev) {
                next[key] = reduced;
                changed = true;
            }
        }
        return changed ? next : state;
    }

    return { reducer, initialState };
}
