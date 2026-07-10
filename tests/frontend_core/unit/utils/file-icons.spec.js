import { describe, it, expect } from 'vitest';
import { resolveUiIconFile } from '@platform/lib/utils/file-icons.js';

describe('resolveUiIconFile', () => {
    it('maps minus to minus.svg basename', () => {
        expect(resolveUiIconFile('minus')).toBe('minus');
    });

    it('maps chevron-down and chevron-up to their own SVG basenames', () => {
        expect(resolveUiIconFile('chevron-down')).toBe('chevron-down');
        expect(resolveUiIconFile('chevron-up')).toBe('chevron-up');
    });

    it('maps arrow-up and arrow-down to chevron SVG basenames', () => {
        expect(resolveUiIconFile('arrow-up')).toBe('chevron-up');
        expect(resolveUiIconFile('arrow-down')).toBe('chevron-down');
    });

    it('preserves explicit collapse, expand, and minimize names', () => {
        expect(resolveUiIconFile('collapse')).toBe('collapse');
        expect(resolveUiIconFile('expand')).toBe('expand');
        expect(resolveUiIconFile('minimize')).toBe('minimize');
    });
});
