import { describe, expect, it } from 'vitest';
import {
    FLOW_CODE_LANGUAGES,
    flowCodeLanguageSegmentItems,
} from '../../../../apps/flows/ui/_helpers/flows-code-languages.js';

describe('flowCodeLanguageSegmentItems', () => {
    it('exposes iconSrc and iconFallback for every language', () => {
        const items = flowCodeLanguageSegmentItems({ iconOnly: true });
        expect(items).toHaveLength(FLOW_CODE_LANGUAGES.length);
        for (const [index, item] of items.entries()) {
            const meta = FLOW_CODE_LANGUAGES[index];
            expect(item.value).toBe(meta.value);
            expect(item.iconSrc).toBe(`/static/core/assets/icons/${meta.icon}.svg`);
            expect(item.iconFallback).toBe(meta.shortLabel);
            expect(item.title).toBe(meta.label);
            expect(item).not.toHaveProperty('icon');
            expect(item).not.toHaveProperty('label');
        }
    });

    it('includes label when iconOnly is false', () => {
        const items = flowCodeLanguageSegmentItems({ iconOnly: false });
        expect(items[0].label).toBe(FLOW_CODE_LANGUAGES[0].label);
    });
});
