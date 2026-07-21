import { describe, expect, it } from 'vitest';
import { getBlankHitlNodeConfig } from '../../../../apps/flows/ui/_helpers/flows-hitl-defaults.js';

describe('getBlankHitlNodeConfig', () => {
    it('seeds title and message with @state: refs', () => {
        const cfg = getBlankHitlNodeConfig();
        expect(cfg.handoff_mode).toBe('single_reply');
        expect(cfg.handoff_task_title).toContain('@state:content');
        expect(cfg.handoff_user_message).toContain('@state:content');
        expect(cfg.handoff_task_title).not.toContain('{content}');
        expect(cfg.handoff_user_message).not.toContain('{content}');
    });
});
