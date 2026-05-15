/**
 * Fields for background AI suggestions from `NamespaceCRMSettings`.
 */

export const DEFAULT_SUGGESTS_CRON = '0 2 * * *';

/**
 * @param {object|null|undefined} cs
 * @returns {{ enabled: boolean, cron: string, scheduleTaskId: string }}
 */
export function parseSuggestsSettingsFromCrmSettings(cs) {
    const result = {
        enabled: false,
        cron: DEFAULT_SUGGESTS_CRON,
        scheduleTaskId: '',
    };
    if (cs === undefined || cs === null || typeof cs !== 'object') {
        return result;
    }
    const s = cs.suggests;
    if (s === undefined || s === null || typeof s !== 'object') {
        return result;
    }
    result.enabled = s.enabled === true;
    if (typeof s.cron === 'string' && s.cron.trim().length > 0) {
        result.cron = s.cron.trim();
    }
    if (typeof s.schedule_task_id === 'string' && s.schedule_task_id.length > 0) {
        result.scheduleTaskId = s.schedule_task_id;
    }
    return result;
}

/**
 * @param {{ enabled: boolean, cron: string }} draft
 * @returns {{ enabled: boolean, cron: string }}
 */
export function buildSuggestsSettingsPayload(draft) {
    const cron = typeof draft.cron === 'string' && draft.cron.trim().length > 0
        ? draft.cron.trim()
        : DEFAULT_SUGGESTS_CRON;
    return {
        enabled: draft.enabled === true,
        cron,
    };
}
