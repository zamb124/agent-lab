import { describe, it, expect } from 'vitest';
import { computeAvatarResizeDimensions } from '../../../apps/sync/ui/_helpers/sync-avatar-image-compress.js';

describe('sync-avatar-image-compress', () => {
    it('computeAvatarResizeDimensions: без масштабирования, если длинная сторона <= maxEdge', () => {
        expect(computeAvatarResizeDimensions(400, 300, 512)).toEqual({ width: 400, height: 300 });
        expect(computeAvatarResizeDimensions(512, 512, 512)).toEqual({ width: 512, height: 512 });
    });

    it('computeAvatarResizeDimensions: вписывает длинную сторону в maxEdge', () => {
        expect(computeAvatarResizeDimensions(1000, 500, 512)).toEqual({ width: 512, height: 256 });
        expect(computeAvatarResizeDimensions(500, 1000, 512)).toEqual({ width: 256, height: 512 });
    });

    it('computeAvatarResizeDimensions: неверные аргументы — throw', () => {
        expect(() => computeAvatarResizeDimensions(0, 100, 512)).toThrow();
        expect(() => computeAvatarResizeDimensions(100, 100, 0)).toThrow();
        expect(() => computeAvatarResizeDimensions('a', 100, 512)).toThrow();
    });
});
