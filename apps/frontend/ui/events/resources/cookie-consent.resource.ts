/**
 * Согласие на cookie: slice выбора + POST в журнал.
 *
 * API:
 *   POST /frontend/api/public/cookie-consent
 */
import { createAsyncOp, createSlice } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const DECISIONS = new Set(['accept_all', 'necessary_only', 'custom']);

export const cookieConsentRecordOp = createAsyncOp({
    name: 'frontend/cookie_consent_record',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/public/cookie-consent' },
    request: async ({ payload }) => {
        if (!isPlainRecord(payload)) {
            throw new Error('frontend/cookie_consent_record: payload required');
        }
        const decision = payload.decision;
        if (typeof decision !== 'string' || !DECISIONS.has(decision)) {
            throw new Error('frontend/cookie_consent_record: decision required');
        }
        const analyticsAllowed = payload.analytics_allowed;
        if (typeof analyticsAllowed !== 'boolean') {
            throw new Error('frontend/cookie_consent_record: analytics_allowed boolean required');
        }
        const consentTextVersion = payload.consent_text_version;
        if (typeof consentTextVersion !== 'string' || consentTextVersion === '') {
            throw new Error('frontend/cookie_consent_record: consent_text_version required');
        }
        const locale = payload.locale;
        if (locale !== 'ru' && locale !== 'en') {
            throw new Error('frontend/cookie_consent_record: locale must be ru or en');
        }
        const body: Record<string, string | boolean> = {
            decision,
            analytics_allowed: analyticsAllowed,
            consent_text_version: consentTextVersion,
            locale,
        };
        const supersedes = payload.supersedes_cookie_consent_id;
        if (typeof supersedes === 'string' && supersedes !== '') {
            body.supersedes_cookie_consent_id = supersedes;
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
            if (!isPlainRecord(payload)) {
                throw new Error('cookieConsentSlice.hydrate: payload object or null required');
            }
            const cookieConsentId = payload.cookieConsentId;
            const consentTextVersion = payload.consentTextVersion;
            const decision = payload.decision;
            const decidedAt = payload.decidedAt;
            const analyticsAllowed = payload.analyticsAllowed;
            const analyticsOffered = payload.analyticsOffered;
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
            if (typeof analyticsAllowed !== 'boolean') {
                throw new Error('cookieConsentSlice.hydrate: analyticsAllowed boolean required');
            }
            if (typeof analyticsOffered !== 'boolean') {
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
                analyticsAllowed,
                analyticsOffered,
                decidedAt,
                analyticsDraft: analyticsAllowed,
            };
        }
        if (event.type === events.DECIDED) {
            const payload = event.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('cookieConsentSlice.decide: payload required');
            }
            const cookieConsentId = payload.cookieConsentId;
            const consentTextVersion = payload.consentTextVersion;
            const decision = payload.decision;
            const decidedAt = payload.decidedAt;
            const analyticsAllowed = payload.analyticsAllowed;
            const analyticsOffered = payload.analyticsOffered;
            if (typeof cookieConsentId !== 'string' || cookieConsentId === '') {
                throw new Error('cookieConsentSlice.decide: cookieConsentId required');
            }
            if (typeof consentTextVersion !== 'string' || consentTextVersion === '') {
                throw new Error('cookieConsentSlice.decide: consentTextVersion required');
            }
            if (typeof decision !== 'string' || !DECISIONS.has(decision)) {
                throw new Error('cookieConsentSlice.decide: decision required');
            }
            if (typeof analyticsAllowed !== 'boolean') {
                throw new Error('cookieConsentSlice.decide: analyticsAllowed boolean required');
            }
            if (typeof analyticsOffered !== 'boolean') {
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
                analyticsAllowed,
                analyticsOffered,
                decidedAt,
                analyticsDraft: analyticsAllowed,
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
            const draft = isPlainRecord(payload) ? payload.value : undefined;
            if (typeof draft !== 'boolean') {
                throw new Error('cookieConsentSlice.setAnalyticsDraft: value boolean required');
            }
            return { ...state, analyticsDraft: draft };
        }
        return state;
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'frontend/cookie_consent_record': typeof cookieConsentRecordOp;
        'frontend/cookie_consent': typeof cookieConsentSlice;
    }
}
