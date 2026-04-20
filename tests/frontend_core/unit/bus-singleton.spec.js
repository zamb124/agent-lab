/**
 * Глобальный singleton EventBus — точка доступа из компонентов.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    setPlatformBus,
    getPlatformBus,
    hasPlatformBus,
    resetPlatformBusForTests,
} from '@platform/lib/events/bus-singleton.js';
import { installDomShim } from '../helpers/dom-shim.js';
import { buildBus } from '../helpers/bus-fixtures.js';

let dom;

beforeEach(() => {
    dom = installDomShim();
    resetPlatformBusForTests();
});

afterEach(() => {
    resetPlatformBusForTests();
    dom.uninstall();
});

describe('bus-singleton: contract', () => {
    it('hasPlatformBus до setPlatformBus → false', () => {
        expect(hasPlatformBus()).toBe(false);
    });

    it('getPlatformBus до setPlatformBus → throw', () => {
        expect(() => getPlatformBus()).toThrow(/not initialized/);
    });

    it('setPlatformBus + getPlatformBus возвращает тот же bus', () => {
        const { bus } = buildBus({ slices: {} });
        setPlatformBus(bus);
        expect(hasPlatformBus()).toBe(true);
        expect(getPlatformBus()).toBe(bus);
    });

    it('setPlatformBus с тем же bus — идемпотентно', () => {
        const { bus } = buildBus({ slices: {} });
        setPlatformBus(bus);
        expect(() => setPlatformBus(bus)).not.toThrow();
    });

    it('setPlatformBus с другим bus — throw', () => {
        const a = buildBus({ slices: {} }).bus;
        const b = buildBus({ slices: {} }).bus;
        setPlatformBus(a);
        expect(() => setPlatformBus(b)).toThrow(/already initialized/);
    });

    it('setPlatformBus с invalid bus (no dispatch) — throw', () => {
        expect(() => setPlatformBus(null)).toThrow(/invalid bus/);
        expect(() => setPlatformBus({})).toThrow(/invalid bus/);
        expect(() => setPlatformBus({ dispatch: 'not a function' })).toThrow(/invalid bus/);
    });

    it('resetPlatformBusForTests — после reset getPlatformBus снова бросает', () => {
        const { bus } = buildBus({ slices: {} });
        setPlatformBus(bus);
        resetPlatformBusForTests();
        expect(hasPlatformBus()).toBe(false);
        expect(() => getPlatformBus()).toThrow(/not initialized/);
    });
});
