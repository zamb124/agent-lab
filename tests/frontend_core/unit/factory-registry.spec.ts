/**
 * factory-registry: уникальность по имени, kind validation, idempotent.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
    registerFactory,
    getFactory,
    hasFactory,
    clearFactoryRegistry,
} from '@platform/lib/events/factory-registry.js';
import type { FactoryKind, PlatformFactory } from '@platform/lib/events/factory-registry.js';

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'svc/foo': PlatformFactory;
        'svc/missing': PlatformFactory;
    }
}

const stub = (name: string, kind: FactoryKind = 'async-op'): PlatformFactory => ({ name, kind });

describe('factory-registry', () => {
    beforeEach(() => clearFactoryRegistry());

    it('registerFactory требует объект с name + известным kind', () => {
        expect(() => Reflect.apply(registerFactory, null, [null])).toThrow(/factory object/);
        expect(() => Reflect.apply(registerFactory, null, [{}])).toThrow(/factory.name/);
        expect(() => Reflect.apply(registerFactory, null, [{ name: 'x' }])).toThrow(/unknown factory.kind/);
        expect(() => Reflect.apply(registerFactory, null, [{ name: 'x', kind: 'mystery' }])).toThrow(/unknown factory.kind/);
    });

    it('пропускает все известные kinds', () => {
        const kinds: FactoryKind[] = ['async-op', 'resource-collection', 'cursor-list', 'facets', 'form'];
        for (const k of kinds) {
            registerFactory(stub(`svc/${k.replace('-', '_')}`, k));
        }
    });

    it('повторная регистрация той же фабрики идемпотентна', () => {
        const f = stub('svc/foo');
        expect(registerFactory(f)).toBe(f);
        expect(registerFactory(f)).toBe(f);
    });

    it('повторная регистрация другой фабрики с тем же именем — throw', () => {
        registerFactory(stub('svc/foo'));
        expect(() => registerFactory(stub('svc/foo'))).toThrow(/already registered/);
    });

    it('getFactory без аргумента — throw', () => {
        expect(() => Reflect.apply(getFactory, null, [''])).toThrow(/name required/);
    });

    it('getFactory неизвестной — throw', () => {
        expect(() => getFactory('svc/missing', 'async-op')).toThrow(/not registered/);
    });

    it('getFactory с expectedKind — throw на mismatch', () => {
        registerFactory(stub('svc/foo', 'async-op'));
        expect(() => getFactory('svc/foo', 'resource-collection')).toThrow(/expected/);
        expect(getFactory('svc/foo', 'async-op').name).toBe('svc/foo');
    });

    it('hasFactory true/false', () => {
        expect(hasFactory('svc/foo')).toBe(false);
        registerFactory(stub('svc/foo'));
        expect(hasFactory('svc/foo')).toBe(true);
    });

    it('clearFactoryRegistry чистит реестр', () => {
        registerFactory(stub('svc/foo'));
        clearFactoryRegistry();
        expect(hasFactory('svc/foo')).toBe(false);
    });
});
