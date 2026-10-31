/**
 * Selectors: createSelector (memoization), selectorFamily (cache по ключу), pluck.
 */

import { describe, it, expect, vi } from 'vitest';
import { createSelector, selectorFamily, pluck } from '@platform/lib/events/selectors.js';

describe('createSelector', () => {
    it('бросает на пустых inputs', () => {
        expect(() => Reflect.apply(createSelector, null, [[], () => null])).toThrow(/inputs/);
        expect(() => Reflect.apply(createSelector, null, ['not array', () => null])).toThrow(/inputs/);
    });

    it('бросает если projector не функция', () => {
        expect(() => Reflect.apply(createSelector, null, [[(s: unknown) => s], 'not function'])).toThrow(/projector/);
    });

    it('пересчитывает только при изменении входов (по reference)', () => {
        const projector = vi.fn((a: unknown, b: unknown) => Number(a) + Number(b));
        const sel = createSelector([(s: { a: number; b: number }) => s.a, (s: { a: number; b: number }) => s.b], projector);
        const stateA = { a: 1, b: 2 };
        expect(sel(stateA)).toBe(3);
        expect(sel(stateA)).toBe(3);
        expect(projector).toHaveBeenCalledOnce();
        const stateB = { a: 1, b: 5 };
        expect(sel(stateB)).toBe(6);
        expect(projector).toHaveBeenCalledTimes(2);
    });

    it('пересчитывает при reference-изменении даже если значение «равно»', () => {
        const projector = vi.fn((arr: unknown) => (Array.isArray(arr) ? arr.length : -1));
        const sel = createSelector([(s: { list: number[] }) => s.list], projector);
        sel({ list: [1, 2] });
        sel({ list: [1, 2] });
        expect(projector).toHaveBeenCalledTimes(2);
    });
});

describe('selectorFamily', () => {
    it('кеширует селекторы по ключу', () => {
        const build = vi.fn((id: string) => (state: { byId: Record<string, string> }) => state.byId[id]);
        const family = selectorFamily({ key: (id: string) => id, build });
        const sel1 = family('a');
        const sel2 = family('a');
        const sel3 = family('b');
        expect(sel1).toBe(sel2);
        expect(sel1).not.toBe(sel3);
        expect(build).toHaveBeenCalledTimes(2);
        const state = { byId: { a: 'A', b: 'B' } };
        expect(sel1(state)).toBe('A');
        expect(sel3(state)).toBe('B');
    });

    it('бросает без { key, build }', () => {
        expect(() => Reflect.apply(selectorFamily, null, [{}])).toThrow(/key, build/);
    });
});

describe('pluck', () => {
    it('читает значение по точечному пути', () => {
        const sel = pluck('auth.user.name');
        expect(sel({ auth: { user: { name: 'Alice' } } })).toBe('Alice');
    });

    it('возвращает undefined если по пути нет ничего', () => {
        const sel = pluck('a.b.c');
        expect(sel({})).toBeUndefined();
        expect(sel({ a: null })).toBeUndefined();
    });

    it('обрабатывает один сегмент', () => {
        expect(pluck('foo')({ foo: 'bar' })).toBe('bar');
    });
});
