import { describe, expect, it } from 'vitest';
import {
    canInjectPublicAnalytics,
    cookieConsentDecisionIsCurrent,
} from '../../../../apps/frontend/ui/_helpers/cookie-consent-analytics.js';

const BASE_INJECT = {
    routeKey: 'landing',
    isLandingRoute: true,
    hydrated: true,
    analyticsAllowed: true,
    consentTextVersion: '2026-08-20.1',
    bundleVersion: '2026-08-20.1',
    analyticsConfigured: true,
};

const BASE_DECISION = {
    hydrated: true,
    decision: 'accept_all',
    consentTextVersion: '2026-08-20.1',
    analyticsOffered: true,
    bundleVersion: '2026-08-20.1',
    analyticsConfigured: true,
};

describe('canInjectPublicAnalytics', () => {
    it('разрешает инжект только после opt-in на landing', () => {
        expect(canInjectPublicAnalytics(BASE_INJECT)).toBe(true);
    });

    it('не инжектит без analytics_allowed', () => {
        expect(canInjectPublicAnalytics({ ...BASE_INJECT, analyticsAllowed: false })).toBe(false);
    });

    it('не инжектит до hydrate', () => {
        expect(canInjectPublicAnalytics({ ...BASE_INJECT, hydrated: false })).toBe(false);
    });

    it('не инжектит при другой версии текста', () => {
        expect(canInjectPublicAnalytics({ ...BASE_INJECT, consentTextVersion: 'old' })).toBe(false);
    });

    it('не инжектит если аналитика не настроена', () => {
        expect(canInjectPublicAnalytics({ ...BASE_INJECT, analyticsConfigured: false })).toBe(false);
    });

    it('не инжектит вне landing-маршрутов', () => {
        expect(canInjectPublicAnalytics({
            ...BASE_INJECT,
            routeKey: 'login',
            isLandingRoute: false,
        })).toBe(false);
    });
});

describe('cookieConsentDecisionIsCurrent', () => {
    it('принимает сохранённое решение той же версии', () => {
        expect(cookieConsentDecisionIsCurrent(BASE_DECISION)).toBe(true);
    });

    it('требует новый баннер при смене версии', () => {
        expect(cookieConsentDecisionIsCurrent({
            ...BASE_DECISION,
            consentTextVersion: 'old',
        })).toBe(false);
    });

    it('требует новый баннер если аналитика появилась после necessary_only', () => {
        expect(cookieConsentDecisionIsCurrent({
            ...BASE_DECISION,
            decision: 'necessary_only',
            analyticsOffered: false,
            analyticsConfigured: true,
        })).toBe(false);
    });
});
