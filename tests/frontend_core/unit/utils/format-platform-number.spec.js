import { describe, it, expect } from 'vitest';
import {
    formatPlatformNumber,
    formatPlatformCurrencyRub,
} from '../../../../core/frontend/static/lib/utils/format-platform-number.js';

describe('formatPlatformNumber', () => {
    it('throws на невалидную локаль', () => {
        expect(() => formatPlatformNumber(100, '')).toThrow();
        expect(() => formatPlatformNumber(100, 'fr')).toThrow();
        expect(() => formatPlatformNumber(100, null)).toThrow();
    });

    it('"—" на невалидное число', () => {
        expect(formatPlatformNumber(NaN, 'ru')).toBe('—');
        expect(formatPlatformNumber('100', 'ru')).toBe('—');
    });

    it('форматирует целые числа', () => {
        expect(formatPlatformNumber(1000, 'en')).toBe('1,000');
        // RU использует non-breaking space (\u00A0)
        expect(formatPlatformNumber(1000, 'ru')).toMatch(/^1\u00A0?000$/);
    });
});

describe('formatPlatformCurrencyRub', () => {
    it('добавляет ₽', () => {
        const result = formatPlatformCurrencyRub(100, 'ru');
        expect(result).toContain('₽');
    });

    it('"—" на невалидное', () => {
        expect(formatPlatformCurrencyRub(NaN, 'ru')).toBe('—');
    });
});
