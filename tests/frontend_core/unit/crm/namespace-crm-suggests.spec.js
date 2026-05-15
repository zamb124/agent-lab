import { describe, it, expect } from 'vitest';
import {
    DEFAULT_SUGGESTS_CRON,
    buildSuggestsSettingsPayload,
    parseSuggestsSettingsFromCrmSettings,
} from '../../../../apps/crm/ui/utils/namespace-crm-suggests.js';

describe('namespace-crm-suggests', () => {
    it('uses disabled defaults when crm_settings has no suggests block', () => {
        expect(parseSuggestsSettingsFromCrmSettings({})).toEqual({
            enabled: false,
            cron: DEFAULT_SUGGESTS_CRON,
            scheduleTaskId: '',
        });
    });

    it('parses saved suggests settings', () => {
        expect(parseSuggestsSettingsFromCrmSettings({
            suggests: {
                enabled: true,
                cron: '*/15 * * * *',
                schedule_task_id: 'task_123',
            },
        })).toEqual({
            enabled: true,
            cron: '*/15 * * * *',
            scheduleTaskId: 'task_123',
        });
    });

    it('builds namespace_update crm_settings.suggests payload', () => {
        expect(buildSuggestsSettingsPayload({
            enabled: true,
            cron: ' 0 2 * * * ',
        })).toEqual({
            enabled: true,
            cron: '0 2 * * *',
        });
    });

    it('falls back to default cron when disabled draft is blank', () => {
        expect(buildSuggestsSettingsPayload({
            enabled: false,
            cron: '   ',
        })).toEqual({
            enabled: false,
            cron: DEFAULT_SUGGESTS_CRON,
        });
    });
});
