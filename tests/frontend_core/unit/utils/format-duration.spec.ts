import { describe, it, expect } from 'vitest';
import { formatDurationSeconds, formatDurationMs } from '../../../../core/frontend/static/lib/utils/format-duration.js';

describe('formatDurationSeconds', () => {
    it('00:00 для невалидного', () => {
        expect(formatDurationSeconds(null)).toBe('00:00');
        expect(formatDurationSeconds(-1)).toBe('00:00');
        expect(formatDurationSeconds('45')).toBe('00:00');
    });

    it('форматирует секунды и минуты', () => {
        expect(formatDurationSeconds(0)).toBe('00:00');
        expect(formatDurationSeconds(45)).toBe('00:45');
        expect(formatDurationSeconds(60)).toBe('01:00');
        expect(formatDurationSeconds(125)).toBe('02:05');
        expect(formatDurationSeconds(599)).toBe('09:59');
    });

    it('часы (auto) появляются при >= 3600 сек', () => {
        expect(formatDurationSeconds(3600)).toBe('1:00:00');
        expect(formatDurationSeconds(3661)).toBe('1:01:01');
    });

    it('withHours: always — добавляет часы всегда', () => {
        expect(formatDurationSeconds(125, { withHours: 'always' })).toBe('0:02:05');
    });
});

describe('formatDurationMs', () => {
    it('из миллисекунд', () => {
        expect(formatDurationMs(0)).toBe('00:00');
        expect(formatDurationMs(1500)).toBe('00:01');
        expect(formatDurationMs(125000)).toBe('02:05');
    });
});
