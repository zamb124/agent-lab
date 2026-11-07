import { describe, it, expect } from 'vitest';
import {
    collectJsonImages,
    formatJsonLeafPreview,
    resolveBase64Image,
    resolveJsonImageObject,
} from '../../../../core/frontend/static/lib/utils/base64-image.js';
import { jsonTreeChildPath } from '../../../../core/frontend/static/lib/utils/json-tree-path.js';

/** 1×1 PNG */
const TINY_PNG_B64 =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

describe('base64-image', () => {
    it('sniffs raw png base64 and builds data url', () => {
        const image = resolveBase64Image(TINY_PNG_B64);
        expect(image).not.toBeNull();
        expect(image?.mimeType).toBe('image/png');
        expect(image?.src.startsWith('data:image/png;base64,')).toBe(true);
        expect(image?.byteLength).toBeGreaterThan(0);
    });

    it('resolves object with content_type and bytes_b64', () => {
        const image = resolveJsonImageObject({
            content_type: 'image/png',
            bytes_b64: TINY_PNG_B64,
            width: 1,
        });
        expect(image).not.toBeNull();
        expect(image?.mimeType).toBe('image/png');
    });

    it('formats leaf preview for scalars and images', () => {
        expect(formatJsonLeafPreview('hello')).toBe('hello');
        expect(formatJsonLeafPreview(42)).toBe('42');
        expect(formatJsonLeafPreview(true)).toBe('true');
        expect(formatJsonLeafPreview(null)).toBe('null');
        const preview = formatJsonLeafPreview(TINY_PNG_B64);
        expect(preview).toContain('image/png');
        expect(formatJsonLeafPreview({
            content_type: 'image/png',
            bytes_b64: TINY_PNG_B64,
        })).toContain('image/png');
        expect(formatJsonLeafPreview({ a: 1 })).toBeNull();
    });

    it('collects images under object and string leaves', () => {
        const images = collectJsonImages({
            page: { content_type: 'image/png', bytes_b64: TINY_PNG_B64 },
            raw: TINY_PNG_B64,
        }, 'result');
        expect(images.map((item) => item.path).sort()).toEqual(['result.page', 'result.raw']);
    });
});

describe('jsonTreeChildPath', () => {
    it('builds path for object and array', () => {
        expect(jsonTreeChildPath('result', 'nested', false)).toBe('result.nested');
        expect(jsonTreeChildPath('', 'root', false)).toBe('root');
        expect(jsonTreeChildPath('hits', 2, true)).toBe('hits[2]');
        expect(() => jsonTreeChildPath('hits', -1, true)).toThrow(/non-negative/);
        expect(() => jsonTreeChildPath('result', '', false)).toThrow(/non-empty/);
    });
});
