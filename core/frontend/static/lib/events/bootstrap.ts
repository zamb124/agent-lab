/**
 * Bootstrap платформенного EventBus.
 *
 * Создаёт EventBus с core-reducers и core-effects, регистрирует сервисные слайсы
 * и effects, кладёт bus в singleton и эмитит APP_BOOTSTRAP_STARTED/COMPLETED.
 *
 * Используется PlatformApp.connectedCallback ОДИН раз на приложение.
 */

import { EventBus } from './bus.js';
import { EventLog } from './log.js';
import { buildPlatformReducer } from './reducers/index.js';
import { CoreEvents } from './contract.js';
import { setPlatformBus, hasPlatformBus, getPlatformBus } from './bus-singleton.js';
import { maybeAttachDevtools } from './devtools.js';

import { createAuthEffect } from './effects/auth.effect.js';
import { createAuthCompanyNavigationEffect } from './effects/auth-company-navigation.effect.js';
import { createThemeEffect } from './effects/theme.effect.js';
import { createI18nEffect } from './effects/i18n.effect.js';
import { createNotifyEffect } from './effects/notify.effect.js';
import { createRouterEffect } from './effects/router.effect.js';
import { createNetworkEffect } from './effects/network.effect.js';
import { createPlatformWsEffect } from './effects/ws.effect.js';
import { createStorageEffect } from './effects/storage.effect.js';
import { createPwaEffect } from './effects/pwa.effect.js';
import { createIconEffect } from './effects/icon.effect.js';
import { createFileTypesEffect } from './effects/file-types.effect.js';
import { createFilesEffect } from './effects/files.effect.js';
import { createCompaniesEffect } from './effects/companies.effect.js';
import { createTeamEffect } from './effects/team.effect.js';
import { createCalendarEffect } from './effects/calendar.effect.js';
import { createMailEffect } from './effects/mail.effect.js';
import { createUiEffect } from './effects/ui.effect.js';

function _normalizePlatformApex(originStr: string | undefined): string {
    const s = (originStr || '').trim();
    if (s === '') {
        return '';
    }
    try {
        const href = s.endsWith('/') ? s : `${s}/`;
        return new URL(href).origin;
    } catch {
        return '';
    }
}

/**
 */
import type { EventEffect } from './bus.js';
import type { Reducer } from './bus.js';
import type { SliceDef } from './reducers/index.js';
import type { RouterRoute } from './reducers/router.js';

export interface BootstrapOptions {
    baseUrl?: string;
    routes?: RouterRoute[];
    slices?: Record<string, SliceDef>;
    effects?: EventEffect[];
    devMode?: boolean;
    platformApexOrigin?: string;
}

export function bootstrapPlatformBus(options?: BootstrapOptions): EventBus {
    if (hasPlatformBus()) {
        return getPlatformBus() as EventBus<Record<string, unknown>>;
    }
    const opts = options || {};
    const baseUrl = opts.baseUrl || '';
    const routes = Array.isArray(opts.routes) ? opts.routes : [];
    const slices = opts.slices || {};
    const extraEffects = Array.isArray(opts.effects) ? opts.effects : [];
    const devMode = Boolean(opts.devMode);
    const platformApex = _normalizePlatformApex(opts.platformApexOrigin || '');
    let suppressHostIntegrationsForPwa = false;
    if (
        platformApex !== ''
        && typeof globalThis.location !== 'undefined'
        && typeof globalThis.location.origin === 'string'
        && globalThis.location.origin.length > 0
    ) {
        suppressHostIntegrationsForPwa = globalThis.location.origin !== platformApex;
    }

    const { reducer, initialState } = buildPlatformReducer(slices);
    const log = new EventLog({ devMode });
    // State шины открыт: слайсы сервисов подключаются динамически —
    // честный тип состояния bus — Record<string, unknown>.
    const bus = new EventBus<Record<string, unknown>>({
        reducer: reducer as unknown as Reducer<Record<string, unknown>>,
        initialState: initialState as Record<string, unknown>,
        log,
    });

    setPlatformBus(bus);
    maybeAttachDevtools(bus, log);


    bus.registerEffect(createNetworkEffect());
    bus.registerEffect(createThemeEffect());
    bus.registerEffect(createI18nEffect({ baseUrl, platformApexOrigin: platformApex }));
    bus.registerEffect(createNotifyEffect());
    bus.registerEffect(createStorageEffect());
    bus.registerEffect(
        createPwaEffect({
            baseUrl,
            suppressHostIntegrations: suppressHostIntegrationsForPwa,
        }),
    );
    bus.registerEffect(createIconEffect({ platformApexOrigin: platformApex }));
    bus.registerEffect(createFileTypesEffect({ platformApexOrigin: platformApex }));
    bus.registerEffect(createFilesEffect());
    bus.registerEffect(createCompaniesEffect({ baseUrl }));
    bus.registerEffect(createTeamEffect({ baseUrl }));
    bus.registerEffect(createCalendarEffect({ baseUrl }));
    bus.registerEffect(createMailEffect({ baseUrl }));
    bus.registerEffect(createUiEffect());
    bus.registerEffect(createAuthEffect({ baseUrl }));
    bus.registerEffect(createAuthCompanyNavigationEffect());
    if (routes.length > 0) {
        bus.registerEffect(createRouterEffect({ baseUrl, routes }));
    }
    bus.registerEffect(createPlatformWsEffect());

    for (const eff of extraEffects) {
        bus.registerEffect(eff);
    }

    bus.dispatch(CoreEvents.APP_BOOTSTRAP_STARTED, { baseUrl }, { source: 'system' });

    return bus;
}

export function completeBootstrap(): void {
    const bus = getPlatformBus();
    bus.dispatch(CoreEvents.APP_BOOTSTRAP_COMPLETED, null, { source: 'system' });
}
