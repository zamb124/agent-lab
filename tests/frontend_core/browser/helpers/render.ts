/**
 * Тонкая обёртка над @open-wc/testing — единая точка импорта браузерных тестов.
 */

export {
    fixture,
    fixtureSync,
    fixtureCleanup,
    html,
    elementUpdated,
    oneEvent,
    waitUntil,
    aTimeout,
    nextFrame,
} from '@open-wc/testing';

export { expect, assert } from '@open-wc/testing';
