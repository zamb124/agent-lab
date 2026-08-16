import { describe, expect, it } from 'vitest';

import { hitlComposerSendLabel } from '../../../../core/frontend/static/lib/flow-ui/utils/text.js';

describe('hitlComposerSendLabel', () => {
    it('returns null when mode is absent', () => {
        expect(hitlComposerSendLabel('en', null)).toBeNull();
        expect(hitlComposerSendLabel('ru', undefined)).toBeNull();
    });

    it('labels single_reply and takeover', () => {
        expect(hitlComposerSendLabel('en', 'single_reply')).toBe('Reply and complete');
        expect(hitlComposerSendLabel('ru', 'single_reply')).toBe('Ответить и завершить');
        expect(hitlComposerSendLabel('en', 'takeover')).toBe('Send');
        expect(hitlComposerSendLabel('ru', 'takeover')).toBe('Отправить');
    });

    it('throws on unsupported mode', () => {
        expect(() => hitlComposerSendLabel('en', 'none')).toThrow(/unsupported HITL mode/);
    });
});
