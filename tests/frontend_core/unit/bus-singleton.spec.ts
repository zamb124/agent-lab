/**
 * Глобальный singleton EventBus — точка доступа из компонентов.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    setPlatformBus,
    getPlatformBus,
    hasPlatformBus,
    resetPlatformBusForTests,
    awaitPlatformBus,
    cancelPlatformBusWait,
} from '@platform/lib/events/bus-singleton.js';
import { installDomShim } from '../helpers/dom-shim.js';
import { buildPlatformBus } from '../helpers/bus-fixtures.js';

let dom: ReturnType<typeof installDomShim> | undefined;

beforeEach(() => {
    dom = installDomShim();
    resetPlatformBusForTests();
});

afterEach(() => {
    resetPlatformBusForTests();
    dom?.uninstall();
});

describe('bus-singleton: contract', () => {
    it('hasPlatformBus до setPlatformBus → false', () => {
        expect(hasPlatformBus()).toBe(false);
    });

    it('getPlatformBus до setPlatformBus → throw', () => {
        expect(() => getPlatformBus()).toThrow(/not initialized/);
    });

    it('setPlatformBus + getPlatformBus возвращает тот же bus', () => {
        const bus = buildPlatformBus();
        setPlatformBus(bus);
        expect(hasPlatformBus()).toBe(true);
        expect(getPlatformBus()).toBe(bus);
    });

    it('setPlatformBus с тем же bus — идемпотентно', () => {
        const bus = buildPlatformBus();
        setPlatformBus(bus);
        expect(() => setPlatformBus(bus)).not.toThrow();
    });

    it('setPlatformBus с другим bus — throw', () => {
        const a = buildPlatformBus();
        const b = buildPlatformBus();
        setPlatformBus(a);
        expect(() => setPlatformBus(b)).toThrow(/already initialized/);
    });

    it('setPlatformBus с invalid bus (no dispatch) — throw', () => {
        expect(() => Reflect.apply(setPlatformBus, null, [null])).toThrow(/invalid bus/);
        expect(() => Reflect.apply(setPlatformBus, null, [{}])).toThrow(/invalid bus/);
        expect(() => Reflect.apply(setPlatformBus, null, [{ dispatch: 'not a function' }])).toThrow(/invalid bus/);
    });

    it('resetPlatformBusForTests — после reset getPlatformBus снова бросает', () => {
        const bus = buildPlatformBus();
        setPlatformBus(bus);
        resetPlatformBusForTests();
        expect(hasPlatformBus()).toBe(false);
        expect(() => getPlatformBus()).toThrow(/not initialized/);
    });
});

describe('bus-singleton: очередь потребителей (DSD-гидратация)', () => {
    it('setPlatformBus вызывает bindPlatformBus всем ожидающим', () => {
        const bound: string[] = [];
        awaitPlatformBus({ bindPlatformBus: () => bound.push('a') });
        awaitPlatformBus({ bindPlatformBus: () => bound.push('b') });
        setPlatformBus(buildPlatformBus());
        expect(bound).toEqual(['a', 'b']);
    });

    it('cancelPlatformBusWait снимает потребителя из очереди', () => {
        const bound: string[] = [];
        const consumer = { bindPlatformBus: () => bound.push('a') };
        awaitPlatformBus(consumer);
        cancelPlatformBusWait(consumer);
        setPlatformBus(buildPlatformBus());
        expect(bound).toEqual([]);
    });

    it('очередь одноразовая: потребители не получают второй bind', () => {
        const bound: string[] = [];
        awaitPlatformBus({ bindPlatformBus: () => bound.push('a') });
        setPlatformBus(buildPlatformBus());
        resetPlatformBusForTests();
        setPlatformBus(buildPlatformBus());
        expect(bound).toEqual(['a']);
    });
});
