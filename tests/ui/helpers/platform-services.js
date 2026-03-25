import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';

/**
 * Инициализация платформенных сервисов для компонентных тестов (как в приложении).
 * @param {string} [baseUrl]
 */
export async function setupPlatformServices(baseUrl = '') {
  await ServiceRegistry.registerCore(baseUrl);
}

/**
 * Сброс реестра между тестами или сьюитами.
 */
export function teardownPlatformServices() {
  ServiceRegistry.resetForUiTests();
}
