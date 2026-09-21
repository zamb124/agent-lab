import { translate } from '../events/effects/i18n.effect.js';
import { getPlatformBus, hasPlatformBus } from '../events/bus-singleton.js';

/**
 * Текст ошибки границы: `platform:errors.<error_code>` или `errors.unknown`.
 *
 * @param {string} errorCode
 * @param {Record<string, string|number|boolean>|null|undefined} errorParams
 * @returns {string}
 */
export function formatPlatformError(errorCode, errorParams) {
    if (typeof errorCode !== 'string' || errorCode.length === 0) {
        throw new Error('formatPlatformError: errorCode required');
    }
    const params = {
        ...(errorParams && typeof errorParams === 'object' && !Array.isArray(errorParams)
            ? errorParams
            : {}),
        code: errorCode,
    };
    if (!hasPlatformBus()) {
        return errorCode;
    }
    const i18nState = getPlatformBus().getState().i18n;
    if (!i18nState) {
        return errorCode;
    }
    const named = translate(i18nState, `errors.${errorCode}`, params, 'platform');
    if (named !== `errors.${errorCode}`) {
        return named;
    }
    return translate(i18nState, 'errors.unknown', params, 'platform');
}
