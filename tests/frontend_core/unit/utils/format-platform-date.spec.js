import { describe, it, expect } from 'vitest';
import {
    formatPlatformDate,
    formatPlatformDateTime,
    formatPlatformTime,
    normalizeIsoDateForField,
    normalizeIsoDateTimeForField,
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

describe('normalizeIsoDateTimeForField', () => {
    it('оставляет канонический формат без изменений', () => {
        expect(normalizeIsoDateTimeForField('2026-06-24T21:00')).toBe('2026-06-24T21:00');
    });

    it('нормализует ISO с секундами и Z в локальное YYYY-MM-DDTHH:mm', () => {
        const normalized = normalizeIsoDateTimeForField('2026-06-24T21:00:00Z');
        expect(normalized).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
        expect(normalized).not.toContain('Z');
    });

    it('пустая строка для null/undefined/""', () => {
        expect(normalizeIsoDateTimeForField(null)).toBe('');
        expect(normalizeIsoDateTimeForField(undefined)).toBe('');
        expect(normalizeIsoDateTimeForField('')).toBe('');
    });
});

describe('normalizeIsoDateForField', () => {
    it('нормализует datetime ISO к локальной дате', () => {
        const normalized = normalizeIsoDateForField('2026-06-24T12:00:00Z');
        expect(normalized).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });
});
