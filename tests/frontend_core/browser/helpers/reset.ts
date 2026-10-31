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
    registerFactory,
    collectFactories,
} from '@platform/lib/events/index.js';
import type { EventEffect } from '@platform/lib/events/bus.js';
import type { RouterRoute } from '@platform/lib/events/reducers/router.js';
import type { SliceDef } from '@platform/lib/events/reducers/index.js';
import type { CollectableFactory } from '@platform/lib/events/factories/register.js';
import { _resetResourceRegistryForTests } from '@platform/lib/events/factories/_internal.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { setPlatformBrandBootstrap } from '@platform/lib/utils/platform-brand.js';
import {
    clearPlatformFilesRouteSegment,
    setPlatformFilesRouteSegment,
} from '@platform/lib/utils/platform-files-url.js';

/** Канонический brand для browser/unit тестов без SSR bootstrap. */
const TEST_PLATFORM_BRAND = {
    isProduction: false,
    baseDomain: 'localhost',
    portSuffix: ':8002',
    protocol: 'http',
    platformName: 'Linnex',
    supportEmail: 'support@linnex.io',
    logoPath: '/static/core/assets/service_logos/frontend_logo.svg',
    apexOrigin: 'http://localhost:8002/',
    supportedDomains: ['linnex.io', 'linnex.io', 'localhost', 'lvh.me'],
    modelsProductName: 'Linnex Models',
    voiceProductName: 'Linnex Voice',
    llmsDisplayLabel: 'Linnex LLMs',
    flowsProductLabel: 'Linnex Flows',
};

export function bootstrapTestPlatformBrand(): void {
    setPlatformBrandBootstrap(TEST_PLATFORM_BRAND);
}

export function resetPlatformState(): void {
    resetPlatformBusForTests();
    clearFactoryRegistry();
    _resetResourceRegistryForTests();
    // Дефолтный namespace 'platform' — чтобы компоненты UI Kit, которые
    // вызывают this.t('platform_field.empty_value') без явного NS, не падали
    // в "cannot resolve i18n namespace".
    setDefaultI18nNamespace('platform');
    bootstrapTestPlatformBrand();
    clearPlatformFilesRouteSegment();
    // Изолированные компоненты без PlatformApp: Files API как у frontend SPA.
    setPlatformFilesRouteSegment('frontend');
}

export interface BootstrapTestBusOptions {
    factories?: CollectableFactory[];
    baseUrl?: string;
    routes?: RouterRoute[];
    slices?: Record<string, SliceDef>;
    effects?: EventEffect[];
}

/**
 * Поднять минимальный bus для тестов без сетевых эффектов.
 * routes = [] чтобы createRouterEffect не зарегистрировался.
 * opts.factories — registerFactory + collectFactories → slices/effects в bus.
 */
export function bootstrapTestBus(opts: BootstrapTestBusOptions = {}) {
    const factories = Array.isArray(opts.factories) ? opts.factories : [];
    for (const factory of factories) {
        registerFactory(factory);
    }
    const collected = factories.length > 0
        ? collectFactories(factories)
        : { slices: {} satisfies Record<string, SliceDef>, effects: [] satisfies EventEffect[] };
    return bootstrapPlatformBus({
        baseUrl: opts.baseUrl || '',
        routes: opts.routes || [],
        slices: { ...collected.slices, ...(opts.slices || {}) },
        effects: [...collected.effects, ...(opts.effects || [])],
    });
}
