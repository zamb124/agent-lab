/**
 * UI-пресеты SMS channel: 1 клик → skeleton в channel_config (HTTP-супербаза).
 * Новый провайдер = запись здесь + svg в assets/sms-providers + i18n.
 */

/** @typedef {{
 *   preset_id: string,
 *   iconSrc: string,
 *   labelKey: string,
 *   subtitleKey: string,
 *   channel_config: {
 *     preset_id: string,
 *     url: string,
 *     method: string,
 *     headers: Record<string, string>,
 *     body_template: string,
 *     timeout: number,
 *   },
 * }} SmsPreset */

export const SMS_PRESET_IDS = Object.freeze(['smsru', 'twilio', 'custom']);

export const SMS_PROVIDER_ICON_BASE = '/flows/static/assets/sms-providers';

/**
 * @param {string} presetId
 * @returns {string}
 */
export function smsProviderIconSrc(presetId: any) {
    if (typeof presetId !== 'string' || presetId.length === 0) {
        throw new Error('smsProviderIconSrc: presetId required');
    }
    return `${SMS_PROVIDER_ICON_BASE}/${encodeURIComponent(presetId)}.svg`;
}

/**
 * @param {string} presetId
 * @returns {SmsPreset}
 */
export function getSmsPreset(presetId: any) {
    if (presetId === 'smsru') {
        return {
            preset_id: 'smsru',
            iconSrc: smsProviderIconSrc('smsru'),
            labelKey: 'channel_node_editor.sms_preset_smsru',
            subtitleKey: 'channel_node_editor.sms_preset_smsru_hint',
            channel_config: {
                preset_id: 'smsru',
                url: 'https://sms.ru/sms/send',
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body_template: JSON.stringify(
                    {
                        api_id: '@var:sms_api_id',
                        to: '@state:phone',
                        msg: '@state:response',
                        json: 1,
                    },
                    null,
                    2,
                ),
                timeout: 30,
            },
        };
    }
    if (presetId === 'twilio') {
        return {
            preset_id: 'twilio',
            iconSrc: smsProviderIconSrc('twilio'),
            labelKey: 'channel_node_editor.sms_preset_twilio',
            subtitleKey: 'channel_node_editor.sms_preset_twilio_hint',
            channel_config: {
                preset_id: 'twilio',
                url: 'https://api.twilio.com/2010-04-01/Accounts/@var:twilio_account_sid/Messages.json',
                method: 'POST',
                headers: {
                    Authorization: 'Basic @var:twilio_basic_auth',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body_template: JSON.stringify(
                    {
                        To: '@state:phone',
                        From: '@var:twilio_from_number',
                        Body: '@state:response',
                    },
                    null,
                    2,
                ),
                timeout: 30,
            },
        };
    }
    if (presetId === 'custom') {
        return {
            preset_id: 'custom',
            iconSrc: smsProviderIconSrc('custom'),
            labelKey: 'channel_node_editor.sms_preset_custom',
            subtitleKey: 'channel_node_editor.sms_preset_custom_hint',
            channel_config: {
                preset_id: 'custom',
                url: 'https://example.com/sms/send',
                method: 'POST',
                headers: {
                    Authorization: 'Bearer @var:sms_token',
                    'Content-Type': 'application/json',
                },
                body_template: JSON.stringify(
                    {
                        to: '@state:phone',
                        message: '@state:response',
                    },
                    null,
                    2,
                ),
                timeout: 30,
            },
        };
    }
    throw new Error(`getSmsPreset: unknown preset_id ${presetId}`);
}

/**
 * @returns {readonly SmsPreset[]}
 */
export function listSmsPresets() {
    return SMS_PRESET_IDS.map((presetId) => getSmsPreset(presetId));
}

/**
 * Сравнивает супербазу с skeleton пресета (без учёта пробелов в body_template JSON).
 * @param {Record<string, unknown>} config
 * @param {Record<string, unknown>} skeleton
 * @returns {boolean}
 */
export function smsConfigMatchesPresetSkeleton(config: any, skeleton: any) {
    if (!config || typeof config !== 'object' || !skeleton || typeof skeleton !== 'object') {
        return false;
    }
    if (config.preset_id !== skeleton.preset_id) {
        return false;
    }
    if (config.url !== skeleton.url || config.method !== skeleton.method) {
        return false;
    }
    if (Number(config.timeout) !== Number(skeleton.timeout)) {
        return false;
    }
    const cfgHeaders = config.headers && typeof config.headers === 'object' ? config.headers : {};
    const skHeaders = skeleton.headers && typeof skeleton.headers === 'object' ? skeleton.headers : {};
    if (JSON.stringify(cfgHeaders) !== JSON.stringify(skHeaders)) {
        return false;
    }
    const normalizeBody = (raw: any) => {
        if (typeof raw !== 'string') {
            if (raw === undefined || raw === null) return JSON.stringify({});
            return JSON.stringify(raw);
        }
        const trimmed = raw.trim();
        if (trimmed.length === 0) {
            return '{}';
        }
        try {
            return JSON.stringify(JSON.parse(trimmed));
        } catch (err) {
            if (!(err instanceof SyntaxError)) throw err;
            // Тело пресета — шаблон сообщения, он не обязан быть JSON.
            return trimmed;
        }
    };
    return normalizeBody(config.body_template) === normalizeBody(skeleton.body_template);
}
