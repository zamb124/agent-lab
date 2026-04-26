/**
 * 5-полевой cron (мин часы D M DoW) для сопоставления с python croniter.
 */

export const CRON_FIELD_PRESET_CUSTOM = 'custom';

const PRESETS = Object.freeze([
    { id: 'every_5m', cron: '*/5 * * * *' },
    { id: 'every_15m', cron: '*/15 * * * *' },
    { id: 'every_30m', cron: '*/30 * * * *' },
    { id: 'hourly', cron: '0 * * * *' },
    { id: 'daily_9', cron: '0 9 * * *' },
    { id: 'daily_midnight', cron: '0 0 * * *' },
    { id: 'weekly_mon_9', cron: '0 9 * * 1' },
    { id: 'monthly_1_midnight', cron: '0 0 1 * *' },
]);

export const CRON_FIELD_PRESETS = PRESETS;

/**
 * Сжатие пробелов, trim.
 */
export function normalizeCronString(s) {
    if (typeof s !== 'string') {
        return '';
    }
    return s.trim().split(/\s+/).filter(Boolean).join(' ');
}

/**
 * @returns {string | null} id пресета или `null` если нет совпадения
 */
export function findMatchingPresetId(cron) {
    const n = normalizeCronString(cron);
    if (n.length === 0) {
        return null;
    }
    for (const p of PRESETS) {
        if (normalizeCronString(p.cron) === n) {
            return p.id;
        }
    }
    return null;
}

/**
 * @param {string} id
 * @returns {string | null} cron-строка или `null` для `custom`
 */
export function getCronForPresetId(id) {
    if (id === CRON_FIELD_PRESET_CUSTOM) {
        return null;
    }
    const p = PRESETS.find((x) => x.id === id);
    return p ? p.cron : null;
}

const MAX_FIELD_LEN = 120;

/**
 * Ровно пять полей, разделённых пробелами. Итоговая проверка — croniter на сервере.
 */
export function validateCronFiveField(s) {
    if (typeof s !== 'string') {
        return false;
    }
    const n = normalizeCronString(s);
    if (n.length === 0) {
        return false;
    }
    const parts = n.split(' ');
    if (parts.length !== 5) {
        return false;
    }
    for (const p of parts) {
        if (p.length === 0 || p.length > MAX_FIELD_LEN) {
            return false;
        }
    }
    return true;
}
