/**
 * Баннер согласия на cookie: opt-in, равнозначные кнопки, настройки категорий.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { cookieConsentDecisionIsCurrent } from '../../_helpers/cookie-consent-analytics.js';
import '@platform/lib/components/fields/platform-field.js';
import type {CSSResultGroup, PropertyValues, TemplateResult} from 'lit';
import type { OpController, ControllerFor } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { SliceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function bundleConsent(bundle: Record<string, unknown>): { version: string; analyticsConfigured: boolean } {
    const version = bundle.cookie_consent_text_version;
    if (typeof version !== 'string' || version === '') {
        throw new Error('cookie-consent-banner: cookie_consent_text_version required');
    }
    const analyticsConfigured = bundle.analytics_configured;
    if (typeof analyticsConfigured !== 'boolean') {
        throw new Error('cookie-consent-banner: analytics_configured boolean required');
    }
    return { version, analyticsConfigured };
}

function analyticsAlreadyInjected(): boolean {
    return Reflect.get(window, '__linnexAnalyticsInjected') === true;
}

const COOKIE_CONSENT_STORAGE_KEY = platformStorageKey('frontend', 'cookie_consent');


const PUBLIC_BANNER_ROUTES = new Set([
    'landing',
    'search',
    'product-agents', 'product-rag', 'product-crm', 'product-sync', 'product-documents',
    'policy', 'terms', 'cookies', 'cookie-consent', 'support',
    'digital-workers',
    'blog', 'blog-post', 'about', 'roadmap',
    'login', 'join', 'select-company',
]);

export class CookieConsentBanner extends PlatformElement {
    static i18nNamespace = 'cookies';

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host {
                display: none;
            }
            :host([visible]) {
                display: block;
                position: fixed;
                left: 0;
                right: 0;
                bottom: 0;
                z-index: 10000;
                pointer-events: none;
            }
            .panel {
                pointer-events: auto;
                margin: 0 auto;
                max-width: 960px;
                padding: var(--space-4);
                background: var(--bg-elevated);
                border: 1px solid var(--border-default);
                border-bottom: none;
                border-radius: var(--radius-lg) var(--radius-lg) 0 0;
                color: var(--text-primary);
                box-shadow: var(--glass-shadow-medium);
            }
            .title {
                margin: 0 0 var(--space-2);
                font-size: var(--text-lg);
                font-weight: 600;
            }
            .body {
                margin: 0 0 var(--space-3);
                font-size: var(--text-sm);
                line-height: 1.5;
                color: var(--text-tertiary);
            }
            .links {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                margin: 0 0 var(--space-4);
            }
            .links a {
                color: var(--accent);
                font-size: var(--text-sm);
            }
            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .actions .btn {
                flex: 1 1 160px;
                min-height: 44px;
            }
            .categories {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                margin: 0 0 var(--space-4);
            }
            @media (max-width: 480px) {
                .actions {
                    flex-direction: column;
                }
                .actions .btn {
                    width: 100%;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._consent = this.useSlice('frontend/cookie_consent');
        this._recordOp = this.useOp('frontend/cookie_consent_record');
        this._siteBundle = this.useOp('frontend/public_site_bundle');
        this._localeSel = this.select((s: Record<string, unknown>) => s.i18n.locale);
        this._routeSel = this.select((s: Record<string, unknown>) => s.router.routeKey);
        this._consentSel = this.select((s: Record<string, unknown>) => s.frontendCookieConsent);
        this.useEvent(CoreEvents.STORAGE_LOADED, (event) => this._onStorageLoaded(event));
    }
    private _consent: ControllerFor<'frontend/cookie_consent'>;
    private _recordOp: OpController;
    private _siteBundle: OpController;
    private _localeSel: SelectController<any>;
    private _routeSel: SelectController<any>;
    private _consentSel: SelectController<any>;


    override connectedCallback(): void {
        super.connectedCallback();
        void this._siteBundle.run(null);
        const consent = this._consentSel.value;
        if (!consent.hydrated) {
            this.dispatch(CoreEvents.STORAGE_LOAD_REQUESTED, { key: COOKIE_CONSENT_STORAGE_KEY });
        }
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated && super.updated(changed);
        this.toggleAttribute('visible', this._shouldShow());
    }

    _onStorageLoaded(event: PlatformEvent) {
        if (!isPlainRecord(event.payload)) {
            return;
        }
        const payload = event.payload;
        if (!payload || payload.key !== COOKIE_CONSENT_STORAGE_KEY) {
            return;
        }
        if (this._consentSel.value.hydrated) {
            return;
        }
        if (payload.value === null) {
            this._consent.hydrate(null);
            return;
        }
        this._consent.hydrate(payload.value);
    }

    _bundle(): Record<string, unknown> | null {
        const bundleRes = this._siteBundle.lastResult;
        return isPlainRecord(bundleRes) ? bundleRes : null;
    }

    _shouldShow() {
        const routeKey = this._routeSel.value;
        if (typeof routeKey !== 'string' || !PUBLIC_BANNER_ROUTES.has(routeKey)) {
            return false;
        }
        const bundle = this._bundle();
        if (!bundle) {
            return false;
        }
        const { version, analyticsConfigured } = bundleConsent(bundle);
        const consent = this._consentSel.value;
        if (consent.settingsOpen) {
            return true;
        }
        return !cookieConsentDecisionIsCurrent({
            hydrated: consent.hydrated,
            decision: consent.decision,
            consentTextVersion: consent.consentTextVersion,
            analyticsOffered: consent.analyticsOffered,
            bundleVersion: version,
            analyticsConfigured,
        });
    }

    _legalUrl(pathname: string) {
        const lang = this._localeSel.value;
        if (lang === 'ru') {
            return `${pathname}?lang=ru`;
        }
        if (lang === 'en') {
            return `${pathname}?lang=en`;
        }
        throw new Error('cookie-consent-banner: i18n.locale must be ru or en');
    }

    _persistSnapshot(consent: Record<string, unknown>) {
        this.dispatch(CoreEvents.STORAGE_PERSIST_REQUESTED, {
            key: COOKIE_CONSENT_STORAGE_KEY,
            value: {
                cookieConsentId: consent.cookieConsentId,
                consentTextVersion: consent.consentTextVersion,
                decision: consent.decision,
                analyticsAllowed: consent.analyticsAllowed,
                analyticsOffered: consent.analyticsOffered,
                decidedAt: consent.decidedAt,
            },
        });
    }

    async _submit(decision: string, analyticsAllowed: boolean) {
        const bundle = this._bundle();
        if (!bundle) {
            throw new Error('cookie-consent-banner: site bundle required');
        }
        const { version, analyticsConfigured } = bundleConsent(bundle);
        const locale = this._localeSel.value;
        if (locale !== 'ru' && locale !== 'en') {
            throw new Error('cookie-consent-banner: locale must be ru or en');
        }
        const previousId = this._consentSel.value.cookieConsentId;
        const payload: Record<string, unknown> = {
            decision,
            analytics_allowed: analyticsAllowed,
            consent_text_version: version,
            locale,
        };
        if (previousId !== '') {
            payload.supersedes_cookie_consent_id = previousId;
        }
        const recorded = await this._recordOp.run(payload);
        if (!isPlainRecord(recorded)) {
            throw new Error('cookie-consent-banner: consent journal write failed');
        }
        const cookieConsentId = recorded.cookie_consent_id;
        const decidedAt = recorded.created_at;
        const consentTextVersion = recorded.consent_text_version;
        const recordedDecision = recorded.decision;
        const recordedAnalytics = recorded.analytics_allowed;
        if (typeof cookieConsentId !== 'string' || cookieConsentId === '') {
            throw new Error('cookie-consent-banner: cookie_consent_id required');
        }
        if (typeof decidedAt !== 'string' || decidedAt === '') {
            throw new Error('cookie-consent-banner: created_at required');
        }
        if (typeof consentTextVersion !== 'string' || consentTextVersion === '') {
            throw new Error('cookie-consent-banner: consent_text_version required');
        }
        if (typeof recordedDecision !== 'string' || recordedDecision === '') {
            throw new Error('cookie-consent-banner: decision required');
        }
        if (typeof recordedAnalytics !== 'boolean') {
            throw new Error('cookie-consent-banner: analytics_allowed boolean required');
        }
        const snapshot = {
            cookieConsentId,
            consentTextVersion,
            decision: recordedDecision,
            analyticsAllowed: recordedAnalytics,
            analyticsOffered: analyticsConfigured,
            decidedAt,
        };
        this._consent.decide(snapshot);
        this._persistSnapshot(snapshot);
        if (analyticsAlreadyInjected() && recordedAnalytics === false) {
            window.location.reload();
        }
    }

    _onAcceptAll() {
        void this._submit('accept_all', true);
    }

    _onNecessaryOnly() {
        void this._submit('necessary_only', false);
    }

    _onUnderstood() {
        void this._submit('necessary_only', false);
    }

    _onSaveSettings() {
        const analyticsAllowed = this._consentSel.value.analyticsDraft;
        void this._submit('custom', analyticsAllowed);
    }

    _renderCategories(analyticsConfigured: boolean) {
        const consent = this._consentSel.value;
        return html`
            <div class="categories">
                <platform-field
                    .type=${'boolean'}
                    .value=${true}
                    .label=${this.t('banner.category_necessary')}
                    .hint=${this.t('banner.category_necessary_hint')}
                    mode="edit"
                    disabled
                ></platform-field>
                ${analyticsConfigured
                    ? html`
                          <platform-field
                              .type=${'boolean'}
                              .value=${consent.analyticsDraft}
                              .label=${this.t('banner.category_analytics')}
                              .hint=${this.t('banner.category_analytics_hint')}
                              mode="edit"
                              @change=${(event: CustomEvent) => {
                                  this._consent.setAnalyticsDraft({ value: event.detail.value });
                              }}
                          ></platform-field>
                      `
                    : null}
            </div>
        `;
    }

    override render(): TemplateResult {
        const bundle = this._bundle();
        if (!bundle) {
            return html``;
        }
        const { analyticsConfigured } = bundleConsent(bundle);
        const consent = this._consentSel.value;
        const busy = this._recordOp.busy;
        const body = analyticsConfigured
            ? this.t('banner.body')
            : this.t('banner.body_necessary_only');
        return html`
            <div class="panel" role="dialog" aria-labelledby="cookie-consent-title">
                <h2 class="title" id="cookie-consent-title">${this.t('banner.title')}</h2>
                <p class="body">${body}</p>
                <div class="links">
                    <a href=${this._legalUrl('/cookies')}>${this.t('banner.link_policy')}</a>
                    <a href=${this._legalUrl('/consent/cookies')}>${this.t('banner.link_consent')}</a>
                </div>
                ${consent.settingsOpen ? this._renderCategories(analyticsConfigured) : null}
                <div class="actions">
                    ${consent.settingsOpen
                        ? html`
                              <button class="btn btn-secondary" type="button" ?disabled=${busy}
                                  @click=${this._onSaveSettings}>
                                  ${this.t('banner.save')}
                              </button>
                          `
                        : analyticsConfigured
                          ? html`
                                <button class="btn btn-secondary" type="button" ?disabled=${busy}
                                    @click=${this._onAcceptAll}>
                                    ${this.t('banner.accept_all')}
                                </button>
                                <button class="btn btn-secondary" type="button" ?disabled=${busy}
                                    @click=${this._onNecessaryOnly}>
                                    ${this.t('banner.necessary_only')}
                                </button>
                                <button class="btn btn-secondary" type="button" ?disabled=${busy}
                                    @click=${() => this._consent.openSettings(null)}>
                                    ${this.t('banner.settings')}
                                </button>
                            `
                          : html`
                                <button class="btn btn-secondary" type="button" ?disabled=${busy}
                                    @click=${this._onUnderstood}>
                                    ${this.t('banner.understood')}
                                </button>
                            `}
                </div>
            </div>
        `;
    }
}

customElements.define('cookie-consent-banner', CookieConsentBanner);
