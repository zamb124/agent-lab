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

export function resetPlatformState() {
    resetPlatformBusForTests();
    clearFactoryRegistry();
    _resetResourceRegistryForTests();
    // Дефолтный namespace 'platform' — чтобы компоненты UI Kit, которые
    // вызывают this.t('platform_field.empty_value') без явного NS, не падали
    // в "cannot resolve i18n namespace".
    setDefaultI18nNamespace('platform');
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
