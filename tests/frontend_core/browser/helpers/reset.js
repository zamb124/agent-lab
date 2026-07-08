/**
 * Глобальный teardown bus + factory-registry между тестами.
 *
 * Использование:
 *   import { resetPlatformState, bootstrapTestBus } from './helpers/reset.js';
 *   beforeEach(() => resetPlatformState());
 *   beforeEach(() => bootstrapTestBus());
 */

import {
    resetPlatformBusForTests,
    bootstrapPlatformBus,
    clearFactoryRegistry,
} from '@platform/lib/events/index.js';
import { _resetResourceRegistryForTests } from '@platform/lib/events/factories/_internal.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { setPlatformBrandBootstrap } from '@platform/lib/utils/platform-brand.js';

/** Канонический brand для browser/unit тестов без SSR bootstrap. */
const TEST_PLATFORM_BRAND = {
    isProduction: false,
    baseDomain: 'localhost',
    portSuffix: ':8002',
    protocol: 'http',
    platformName: 'Humanitec',
    supportEmail: 'support@humanitec.ru',
    logoPath: '/static/core/assets/service_logos/frontend_logo.svg',
    apexOrigin: 'http://localhost:8002/',
    supportedDomains: ['humanitec.ru', 'linnex.io', 'localhost', 'lvh.me'],
    agentProductName: 'HumanitecAgent',
    modelsProductName: 'Humanitec Models',
    voiceProductName: 'Humanitec Voice',
    llmsDisplayLabel: 'Humanitec LLMs',
    flowsProductLabel: 'Humanitec Flows',
};

export function bootstrapTestPlatformBrand() {
    setPlatformBrandBootstrap(TEST_PLATFORM_BRAND);
}

export function resetPlatformState() {
    resetPlatformBusForTests();
    clearFactoryRegistry();
    _resetResourceRegistryForTests();
    // Дефолтный namespace 'platform' — чтобы компоненты UI Kit, которые
    // вызывают this.t('platform_field.empty_value') без явного NS, не падали
    // в "cannot resolve i18n namespace".
    setDefaultI18nNamespace('platform');
    bootstrapTestPlatformBrand();
}

/**
 * Поднять минимальный bus для тестов без сетевых эффектов.
 * routes = [] чтобы createRouterEffect не зарегистрировался.
 */
export function bootstrapTestBus(opts = {}) {
    return bootstrapPlatformBus({
        baseUrl: opts.baseUrl || '',
        routes: opts.routes || [],
        slices: opts.slices || {},
        effects: opts.effects || [],
    });
}
