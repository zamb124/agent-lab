/**
 * Регистрация и сброс factory-registry между тестами фабрик.
 *
 * В каждом spec-файле:
 *   import { resetFactories } from '../helpers/factory-fixtures.js';
 *   beforeEach(() => resetFactories());
 */

import { clearFactoryRegistry } from '@platform/lib/events/factory-registry.js';
import { _resetResourceRegistryForTests } from '@platform/lib/events/factories/_internal.js';

export function resetFactories() {
    clearFactoryRegistry();
    _resetResourceRegistryForTests();
}
