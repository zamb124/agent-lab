/**
 * Self-contained бандл `<platform-map>` для внешних страниц (витрина shop).
 * Собирается в `core/frontend/embed-dist/map/autoload.js` и отдаётся по
 * `/static/core/lib/map/autoload.js`. MapLibre и PMTiles грузятся lazy
 * самим компонентом — бандл только регистрирует тэг.
 *
 * `<platform-map>` построен на PlatformElement: перевод `this.t()` читает
 * `state.i18n` через `getPlatformBus()`, а интерполяция — `__PLATFORM_BRAND__`.
 * На странице без PlatformApp этих рантаймов нет, поэтому бандл ставит
 * минимальный standalone-контур: реальный EventBus без сетевых эффектов
 * (auth/ws/i18n-fetch не нужны для статичной карты), geo-неймспейс из
 * канонических переводов core/i18n и нейтральный brand-фолбэк — страница
 * платформы всегда отдаёт настоящий `window.__PLATFORM_BRAND__`, он имеет
 * приоритет.
 */
import { EventBus } from '../events/bus.js';
import { EventLog } from '../events/log.js';
import { buildPlatformReducer } from '../events/reducers/index.js';
import { hasPlatformBus, setPlatformBus } from '../events/bus-singleton.js';
import { getPlatformBrandBootstrap, setPlatformBrandBootstrap } from '../utils/platform-brand.js';
import geoRu from '../../../../i18n/translations/ru/geo.json';
import geoEn from '../../../../i18n/translations/en/geo.json';

if (!hasPlatformBus()) {
    const { reducer, initialState } = buildPlatformReducer();
    const i18n = {
        ...initialState.i18n,
        translations: {
            ru: { ...initialState.i18n.translations.ru, geo: geoRu },
            en: { ...initialState.i18n.translations.en, geo: geoEn },
        },
    };
    setPlatformBus(
        new EventBus({
            reducer,
            initialState: { ...initialState, i18n },
            log: new EventLog({ capacity: 200 }),
        }),
    );
}

if (!getPlatformBrandBootstrap()) {
    const { hostname, port, protocol, origin } = window.location;
    setPlatformBrandBootstrap({
        isProduction: false,
        baseDomain: hostname,
        portSuffix: port ? `:${port}` : '',
        protocol: protocol.replace(':', ''),
        platformName: 'Platform',
        supportEmail: '',
        logoPath: '',
        apexOrigin: `${origin}/`,
        supportedDomains: [hostname],
        modelsProductName: 'Models',
        voiceProductName: 'Voice',
        llmsDisplayLabel: 'LLMs',
        flowsProductLabel: 'Flows',
    });
}

import '../components/platform-map.js';
