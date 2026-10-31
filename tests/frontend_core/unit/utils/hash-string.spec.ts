import { describe, it, expect } from 'vitest';
import {
    hashString31,
    hueFromString,
    initialsFromName,
    indexFromSeed,
} from '../../../../core/frontend/static/lib/utils/hash-string.js';

describe('hashString31', () => {
    it('детерминированный', () => {
        expect(hashString31('abc')).toBe(hashString31('abc'));
    });

    it('пустая строка → 0', () => {
        expect(hashString31('')).toBe(0);
        expect(hashString31(null)).toBe(0);
        expect(hashString31(undefined)).toBe(0);
    });

    it('разные seed дают разный hash', () => {
        expect(hashString31('a')).not.toBe(hashString31('b'));
    });
});

describe('hueFromString', () => {
    it('диапазон 0..359', () => {
        for (const seed of ['', 'a', 'abcdef', 'user_id_42', 'humanitec']) {
            const h = hueFromString(seed);
            expect(h).toBeGreaterThanOrEqual(0);
            expect(h).toBeLessThan(360);
        }
    });
});

describe('initialsFromName', () => {
    it('пустая → ?', () => {
        expect(initialsFromName('')).toBe('?');
        expect(initialsFromName(null)).toBe('?');
    });

    it('одно слово — первые 2 буквы UPPER', () => {
        expect(initialsFromName('Иван')).toBe('ИВ');
        expect(initialsFromName('Bob')).toBe('BO');
    });

    it('два слова — первые буквы каждого', () => {
        expect(initialsFromName('Иван Петров')).toBe('ИП');
        expect(initialsFromName('John Doe Smith')).toBe('JD');
    });
});

describe('indexFromSeed', () => {
    it('throws при невалидном modulo', () => {
        expect(() => indexFromSeed('a', 0)).toThrow();
        expect(() => indexFromSeed('a', -1)).toThrow();
        expect(() => indexFromSeed('a', 1.5)).toThrow();
    });

    it('диапазон 0..modulo-1', () => {
        for (const seed of ['a', 'b', 'c', 'd']) {
            const i = indexFromSeed(seed, 5);
            expect(i).toBeGreaterThanOrEqual(0);
            expect(i).toBeLessThan(5);
        }
    });
});
