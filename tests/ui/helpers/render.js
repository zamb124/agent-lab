/**
 * Тонкая обёртка над @open/wc/testing: единая точка импорта для тестов платформы.
 */
export {
  fixture,
  fixtureSync,
  fixtureCleanup,
  html,
  elementUpdated,
  oneEvent,
  waitUntil,
} from '@open-wc/testing';

export { expect, assert } from '@open-wc/testing';
