/**
 * Согласие на cookie: slice выбора + POST в журнал.
 *
 * API:
 *   POST /frontend/api/public/cookie-consent
 */
import { createAsyncOp, createSlice } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const DECISIONS = new Set(['accept_all', 'necessary_only', 'custom']);

export const cookieConsentRecordOp = createAsyncOp({
    name: 'frontend/cookie_consent_record',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/public/cookie-consent' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('frontend/cookie_consent_record: payload required');
        }
        const decision = (payload as Record<string, any>).decision;
        if (typeof decision !== 'string' || !DECISIONS.has(decision)) {
            throw new Error('frontend/cookie_consent_record: decision required');
        }
        if (typeof (payload as Record<string, any>).analytics_allowed !== 'boolean') {
            throw new Error('frontend/cookie_consent_record: analytics_allowed boolean required');
        }
        const consentTextVersion = (payload as Record<string, any>).consent_text_version;
        if (typeof consentTextVersion !== 'string' || consentTextVersion === '') {
            throw new Error('frontend/cookie_consent_record: consent_text_version required');
        }
        const locale = (payload as Record<string, any>).locale;
        if (locale !== 'ru' && locale !== 'en') {
            throw new Error('frontend/cookie_consent_record: locale must be ru or en');
        }
        const body = {
            decision,
            analytics_allowed: (payload as Record<string, any>).analytics_allowed,
            consent_text_version: consentTextVersion,
            locale,
        };
        const supersedes = (payload as Record<string, any>).supersedes_cookie_consent_id;
        if (typeof supersedes === 'string' && supersedes !== '') {
            (body as Record<string, any>).supersedes_cookie_consent_id = supersedes;
        }
        return httpRequest({
            method: 'POST',
            url: '/frontend/api/public/cookie-consent',
            body,
            credentials: 'same-origin',
        });
    },
});

export const cookieConsentSlice = createSlice({
    name: 'frontend/cookie_consent',
    extraInitial: {
        hydrated: false,
        settingsOpen: false,
        cookieConsentId: '',
        consentTextVersion: '',
        decision: '',
        analyticsAllowed: false,
        analyticsOffered: false,
        decidedAt: '',
        analyticsDraft: false,
    },
    extraEvents: {
        HYDRATED: 'hydrated',
        DECIDED: 'decided',
        SETTINGS_OPENED: 'settings_opened',
        SETTINGS_CLOSED: 'settings_closed',
        ANALYTICS_DRAFT_SET: 'analytics_draft_set',
    },
    actions: {
        hydrate: 'hydrated',
        decide: 'decided',
        openSettings: 'settings_opened',
        closeSettings: 'settings_closed',
        setAnalyticsDraft: 'analytics_draft_set',
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.HYDRATED) {
            const payload = event.payload;
            if (payload === null) {
                return { ...state, hydrated: true };
            }
            if (!payload || typeof payload !== 'object') {
                throw new Error('cookieConsentSlice.hydrate: payload object or null required');
            }
            const cookieConsentId = (payload as Record<string, any>).cookieConsentId;
            const consentTextVersion = (payload as Record<string, any>).consentTextVersion;
            const decision = (payload as Record<string, any>).decision;
            const decidedAt = (payload as Record<string, any>).decidedAt;
            if (typeof cookieConsentId !== 'string') {
                throw new Error('cookieConsentSlice.hydrate: cookieConsentId string required');
            }
            if (typeof consentTextVersion !== 'string') {
                throw new Error('cookieConsentSlice.hydrate: consentTextVersion string required');
            }
            if (typeof decision !== 'string') {
                throw new Error('cookieConsentSlice.hydrate: decision string required');
            }
            if (decision !== '' && !DECISIONS.has(decision)) {
                throw new Error('cookieConsentSlice.hydrate: unknown decision');
            }
            if (typeof (payload as Record<string, any>).analyticsAllowed !== 'boolean') {
                throw new Error('cookieConsentSlice.hydrate: analyticsAllowed boolean required');
            }
            if (typeof (payload as Record<string, any>).analyticsOffered !== 'boolean') {
                throw new Error('cookieConsentSlice.hydrate: analyticsOffered boolean required');
            }
            if (typeof decidedAt !== 'string') {
                throw new Error('cookieConsentSlice.hydrate: decidedAt string required');
            }
            return {
                ...state,
                hydrated: true,
                cookieConsentId,
                consentTextVersion,
                decision,
                analyticsAllowed: (payload as Record<string, any>).analyticsAllowed,
                analyticsOffered: (payload as Record<string, any>).analyticsOffered,
                decidedAt,
                analyticsDraft: (payload as Record<string, any>).analyticsAllowed,
            };
        }
        if (event.type === events.DECIDED) {
            const payload = event.payload;
            if (!payload || typeof payload !== 'object') {
                throw new Error('cookieConsentSlice.decide: payload required');
            }
            const cookieConsentId = (payload as Record<string, any>).cookieConsentId;
            const consentTextVersion = (payload as Record<string, any>).consentTextVersion;
            const decision = (payload as Record<string, any>).decision;
            const decidedAt = (payload as Record<string, any>).decidedAt;
            if (typeof cookieConsentId !== 'string' || cookieConsentId === '') {
                throw new Error('cookieConsentSlice.decide: cookieConsentId required');
            }
            if (typeof consentTextVersion !== 'string' || consentTextVersion === '') {
                throw new Error('cookieConsentSlice.decide: consentTextVersion required');
            }
            if (typeof decision !== 'string' || !DECISIONS.has(decision)) {
                throw new Error('cookieConsentSlice.decide: decision required');
            }
            if (typeof (payload as Record<string, any>).analyticsAllowed !== 'boolean') {
                throw new Error('cookieConsentSlice.decide: analyticsAllowed boolean required');
            }
            if (typeof (payload as Record<string, any>).analyticsOffered !== 'boolean') {
                throw new Error('cookieConsentSlice.decide: analyticsOffered boolean required');
            }
            if (typeof decidedAt !== 'string' || decidedAt === '') {
                throw new Error('cookieConsentSlice.decide: decidedAt required');
            }
            return {
                ...state,
                hydrated: true,
                settingsOpen: false,
                cookieConsentId,
                consentTextVersion,
                decision,
                analyticsAllowed: (payload as Record<string, any>).analyticsAllowed,
                analyticsOffered: (payload as Record<string, any>).analyticsOffered,
                decidedAt,
                analyticsDraft: (payload as Record<string, any>).analyticsAllowed,
            };
        }
        if (event.type === events.SETTINGS_OPENED) {
            return {
                ...state,
                settingsOpen: true,
                analyticsDraft: state.analyticsAllowed,
            };
        }
        if (event.type === events.SETTINGS_CLOSED) {
            return { ...state, settingsOpen: false };
        }
        if (event.type === events.ANALYTICS_DRAFT_SET) {
            const payload = event.payload;
            if (!payload || typeof (payload as Record<string, any>).value !== 'boolean') {
                throw new Error('cookieConsentSlice.setAnalyticsDraft: value boolean required');
            }
            return { ...state, analyticsDraft: (payload as Record<string, any>).value };
        }
        return state;
    },
});
