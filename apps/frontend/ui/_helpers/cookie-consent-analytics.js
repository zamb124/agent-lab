/**
 * Гейт инжекта публичной аналитики: только после opt-in и совпадения версии текста.
 */

/**
 * @param {{
 *   routeKey: string,
 *   isLandingRoute: boolean,
 *   hydrated: boolean,
 *   analyticsAllowed: boolean,
 *   consentTextVersion: string,
 *   bundleVersion: string,
 *   analyticsConfigured: boolean,
 * }} params
 * @returns {boolean}
 */
export function canInjectPublicAnalytics(params) {
    if (!params || typeof params !== 'object') {
        throw new Error('canInjectPublicAnalytics: params required');
    }
    if (typeof params.routeKey !== 'string' || params.routeKey === '') {
        throw new Error('canInjectPublicAnalytics: routeKey required');
    }
    if (typeof params.isLandingRoute !== 'boolean') {
        throw new Error('canInjectPublicAnalytics: isLandingRoute boolean required');
    }
    if (typeof params.hydrated !== 'boolean') {
        throw new Error('canInjectPublicAnalytics: hydrated boolean required');
    }
    if (typeof params.analyticsAllowed !== 'boolean') {
        throw new Error('canInjectPublicAnalytics: analyticsAllowed boolean required');
    }
    if (typeof params.consentTextVersion !== 'string') {
        throw new Error('canInjectPublicAnalytics: consentTextVersion string required');
    }
    if (typeof params.bundleVersion !== 'string' || params.bundleVersion === '') {
        throw new Error('canInjectPublicAnalytics: bundleVersion required');
    }
    if (typeof params.analyticsConfigured !== 'boolean') {
        throw new Error('canInjectPublicAnalytics: analyticsConfigured boolean required');
    }
    if (!params.isLandingRoute) return false;
    if (!params.hydrated) return false;
    if (!params.analyticsConfigured) return false;
    if (!params.analyticsAllowed) return false;
    if (params.consentTextVersion !== params.bundleVersion) return false;
    return true;
}

/**
 * Решение в localStorage ещё действительно для текущей версии текста и набора инструментов.
 *
 * @param {{
 *   hydrated: boolean,
 *   decision: string,
 *   consentTextVersion: string,
 *   analyticsOffered: boolean,
 *   bundleVersion: string,
 *   analyticsConfigured: boolean,
 * }} params
 * @returns {boolean}
 */
export function cookieConsentDecisionIsCurrent(params) {
    if (!params || typeof params !== 'object') {
        throw new Error('cookieConsentDecisionIsCurrent: params required');
    }
    if (typeof params.hydrated !== 'boolean') {
        throw new Error('cookieConsentDecisionIsCurrent: hydrated boolean required');
    }
    if (typeof params.decision !== 'string') {
        throw new Error('cookieConsentDecisionIsCurrent: decision string required');
    }
    if (typeof params.consentTextVersion !== 'string') {
        throw new Error('cookieConsentDecisionIsCurrent: consentTextVersion string required');
    }
    if (typeof params.analyticsOffered !== 'boolean') {
        throw new Error('cookieConsentDecisionIsCurrent: analyticsOffered boolean required');
    }
    if (typeof params.bundleVersion !== 'string' || params.bundleVersion === '') {
        throw new Error('cookieConsentDecisionIsCurrent: bundleVersion required');
    }
    if (typeof params.analyticsConfigured !== 'boolean') {
        throw new Error('cookieConsentDecisionIsCurrent: analyticsConfigured boolean required');
    }
    if (!params.hydrated) return false;
    if (params.decision === '') return false;
    if (params.consentTextVersion !== params.bundleVersion) return false;
    if (params.analyticsConfigured && !params.analyticsOffered) return false;
    return true;
}
