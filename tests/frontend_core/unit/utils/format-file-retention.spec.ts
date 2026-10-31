import { describe, expect, it } from 'vitest';
import { formatFileRetentionRemaining } from '@platform/lib/utils/format-file-retention.js';

describe('formatFileRetentionRemaining', () => {
    it('returns permanent when expires_at is absent', () => {
        expect(formatFileRetentionRemaining(null, 'ru')).toBe('permanent');
        expect(formatFileRetentionRemaining(undefined, 'ru')).toBe('permanent');
        expect(formatFileRetentionRemaining('', 'ru')).toBe('permanent');
    });

    it('returns expired for past timestamps', () => {
        const past = new Date('2020-01-01T00:00:00.000Z').toISOString();
        expect(formatFileRetentionRemaining(past, 'ru', Date.parse('2026-01-01T00:00:00.000Z'))).toBe('expired');
    });

    it('returns relative label for future timestamps', () => {
        const now = Date.parse('2026-01-01T00:00:00.000Z');
        const future = new Date(now + 3 * 86400 * 1000).toISOString();
        const label = formatFileRetentionRemaining(future, 'ru', now);
        expect(typeof label).toBe('string');
        expect(label).not.toBe('permanent');
        expect(label).not.toBe('expired');
    });
});
