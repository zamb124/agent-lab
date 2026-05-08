import { describe, it, expect } from 'vitest';
import {
    formatPlatformDate,
    formatPlatformDateTime,
    formatPlatformTime,
} from '../../../../core/frontend/static/lib/utils/format-platform-date.js';

describe('formatPlatformDate', () => {
    it('throws на невалидную локаль', () => {
        expect(() => formatPlatformDate(new Date(), '')).toThrow();
        expect(() => formatPlatformDate(new Date(), 'fr')).toThrow();
    });

    it('"—" на невалидную дату', () => {
        expect(formatPlatformDate(null, 'ru')).toBe('—');
        expect(formatPlatformDate('not-a-date', 'ru')).toBe('—');
        expect(formatPlatformDate(NaN, 'ru')).toBe('—');
    });

    it('принимает Date / ISO string / timestamp', () => {
        const date = new Date('2026-05-15T10:30:00Z');
        const fromDate = formatPlatformDate(date, 'ru');
        const fromString = formatPlatformDate('2026-05-15T10:30:00Z', 'ru');
        const fromMs = formatPlatformDate(date.getTime(), 'ru');
        expect(fromDate).toBe(fromString);
        expect(fromDate).toBe(fromMs);
    });

    it('default options — short date', () => {
        const result = formatPlatformDate('2026-05-15T10:30:00Z', 'ru');
        expect(result).toMatch(/\d{2}\.\d{2}\.\d{4}/);
    });
});

describe('formatPlatformDateTime', () => {
    it('форматирует date+time', () => {
        const result = formatPlatformDateTime('2026-05-15T10:30:00Z', 'ru');
        expect(result).toMatch(/\d{2}\.\d{2}\.\d{4}/);
        expect(result).toMatch(/\d{2}:\d{2}/);
    });
});

describe('formatPlatformTime', () => {
    it('только время', () => {
        const result = formatPlatformTime('2026-05-15T10:30:00Z', 'ru');
        expect(result).toMatch(/^\d{2}:\d{2}$/);
    });
});
