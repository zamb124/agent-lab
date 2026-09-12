/**
 * Span 1–12 от указателя: шаг = ширина родителя / 12.
 */

import { describe, expect, it } from 'vitest';

import {
    ALIGN_VALUES,
    SPAN_COLUMNS,
    blockAlign,
    blockSpan,
    clampSpan,
    spanFromPointer,
} from '../../../../core/frontend/static/lib/flow-ui/editor/span-layout.js';

describe('layout-handles', () => {
    it('clamps span to 1..12 and reads defaults from the block', () => {
        expect(SPAN_COLUMNS).toBe(12);
        expect(ALIGN_VALUES).toEqual(['start', 'center', 'end']);
        expect(clampSpan(0)).toBe(1);
        expect(clampSpan(13)).toBe(12);
        expect(clampSpan(6.4)).toBe(6);
        expect(clampSpan(Number.NaN)).toBe(12);
        expect(blockSpan({})).toBe(12);
        expect(blockSpan({ span: 4 })).toBe(4);
        expect(blockAlign({})).toBe('start');
        expect(blockAlign({ align: 'end' })).toBe('end');
        expect(blockAlign({ align: 'left' })).toBe('start');
    });

    it('snaps span from pointer delta against 1/12 of the container', () => {
        expect(spanFromPointer(12, 0, 0, 1200)).toBe(12);
        expect(spanFromPointer(12, 100, 0, 1200)).toBe(11);
        expect(spanFromPointer(6, 0, 250, 1200)).toBe(9);
        expect(spanFromPointer(1, 0, -400, 1200)).toBe(1);
        expect(spanFromPointer(12, 0, 50, 1200)).toBe(12);
        expect(spanFromPointer(8, 10, 10, 0)).toBe(8);
    });
});
