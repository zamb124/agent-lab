import { describe, it, expect } from 'vitest';
import { formatFileSize } from '../../../../core/frontend/static/lib/utils/format-file-size.js';

describe('formatFileSize', () => {
    it('возвращает "—" для невалидного входа', () => {
        expect(formatFileSize(null)).toBe('—');
        expect(formatFileSize(undefined)).toBe('—');
        expect(formatFileSize(NaN)).toBe('—');
        expect(formatFileSize(-1)).toBe('—');
        expect(formatFileSize('100')).toBe('—');
    });

    it('0 байт', () => {
        expect(formatFileSize(0)).toBe('0 B');
    });

    it('целые байты без дробной части', () => {
        expect(formatFileSize(512)).toBe('512 B');
        expect(formatFileSize(1023)).toBe('1023 B');
    });

    it('1024 = 1.0 KB', () => {
        expect(formatFileSize(1024)).toBe('1.0 KB');
    });

    it('MB / GB / TB', () => {
        expect(formatFileSize(1024 * 1024)).toBe('1.0 MB');
        expect(formatFileSize(1024 * 1024 * 1024)).toBe('1.0 GB');
        expect(formatFileSize(1024 ** 4)).toBe('1.0 TB');
    });

    it('precision: 0', () => {
        expect(formatFileSize(1500, { precision: 0 })).toBe('1 KB');
    });
});
