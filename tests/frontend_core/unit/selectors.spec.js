/**
 * Selectors: createSelector (memoization), selectorFamily (cache по ключу), pluck.
 */

import { describe, it, expect, vi } from 'vitest';
import { createSelector, selectorFamily, pluck } from '@platform/lib/events/selectors.js';

describe('createSelector', () => {
    it('бросает на пустых inputs', () => {
        expect(() => createSelector([], () => null)).toThrow(/inputs/);
        expect(() => createSelector('not array', () => null)).toThrow(/inputs/);
    });

    it('бросает если projector не функция', () => {
        expect(() => createSelector([(s) => s], 'not function')).toThrow(/projector/);
    });

    it('пересчитывает только при изменении входов (по reference)', () => {
        const projector = vi.fn((a, b) => a + b);
        const sel = createSelector([(s) => s.a, (s) => s.b], projector);
        const stateA = { a: 1, b: 2 };
        expect(sel(stateA)).toBe(3);
        expect(sel(stateA)).toBe(3);
        expect(projector).toHaveBeenCalledOnce();
        const stateB = { a: 1, b: 5 };
        expect(sel(stateB)).toBe(6);
        expect(projector).toHaveBeenCalledTimes(2);
    });

    it('пересчитывает при reference-изменении даже если значение «равно»', () => {
        const projector = vi.fn((arr) => arr.length);
        const sel = createSelector([(s) => s.list], projector);
        sel({ list: [1, 2] });
        sel({ list: [1, 2] });
        expect(projector).toHaveBeenCalledTimes(2);
    });
});

describe('selectorFamily', () => {
    it('кеширует селекторы по ключу', () => {
        const build = vi.fn((id) => (state) => state.byId[id]);
        const family = selectorFamily({ key: (id) => id, build });
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
        expect(() => selectorFamily({})).toThrow(/key, build/);
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
