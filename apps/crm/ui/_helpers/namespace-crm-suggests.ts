/**
 * Поля фоновых AI-suggest-ов из `NamespaceCRMSettings`.
 */

import { isPlainRecord } from '@platform/lib/events/payload.js';

export const DEFAULT_SUGGESTS_CRON = '0 2 * * *';

/**
 * @param {object|null|undefined} cs
 * @returns {{ enabled: boolean, cron: string, scheduleTaskId: string }}
 */
export function parseSuggestsSettingsFromCrmSettings(cs: Record<string, unknown> | null | undefined): { enabled: boolean; cron: string; scheduleTaskId: string } {
    const result = {
        enabled: false,
        cron: DEFAULT_SUGGESTS_CRON,
        scheduleTaskId: '',
    };
    if (!isPlainRecord(cs)) {
        return result;
    }
    const suggests = cs.suggests;
    if (!isPlainRecord(suggests)) {
        return result;
    }
    result.enabled = suggests.enabled === true;
    if (typeof suggests.cron === 'string' && suggests.cron.trim().length > 0) {
        result.cron = suggests.cron.trim();
    }
    if (typeof suggests.schedule_task_id === 'string' && suggests.schedule_task_id.length > 0) {
        result.scheduleTaskId = suggests.schedule_task_id;
    }
    return result;
}

/**
 * @param {{ enabled: boolean, cron: string }} draft
 * @returns {{ enabled: boolean, cron: string }}
 */
export function buildSuggestsSettingsPayload(draft: { enabled?: unknown; cron?: unknown }): { enabled: boolean; cron: string } {
    const cron = typeof draft.cron === 'string' && draft.cron.trim().length > 0
        ? draft.cron.trim()
        : DEFAULT_SUGGESTS_CRON;
    return {
        enabled: draft.enabled === true,
        cron,
    };
}
