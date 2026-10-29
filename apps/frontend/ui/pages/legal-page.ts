/**
 * Страница legal — policy / terms / cookies / cookie_consent по атрибуту kind.
 */
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import { mergePlatformI18nVars } from '@platform/lib/utils/platform-i18n-vars.js';
import { applyPublicDocumentMeta } from '../_helpers/public-document-meta.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const PARAGRAPH_KEYS = ['p1', 'p2', 'p3'];
const LEGAL_KINDS = Object.freeze({
    policy: Object.freeze({ ns: 'privacy', path: '/policy', sections: 14 }),
    terms: Object.freeze({ ns: 'terms', path: '/terms', sections: 13 }),
    cookies: Object.freeze({ ns: 'cookies', path: '/cookies', sections: 8 }),
    cookie_consent: Object.freeze({ ns: 'cookie_consent', path: '/consent/cookies', sections: 8 }),
});

function isLegalKind(kind: string): kind is keyof typeof LEGAL_KINDS {
    return Object.prototype.hasOwnProperty.call(LEGAL_KINDS, kind);
}
const LEGAL_I18N_STRING_KEYS = [
    'company_name_ru',
    'company_name_en',
    'legal_form_ru',
    'legal_form_en',
    'inn',
    'kpp',
    'ogrn',
    'legal_address_ru',
    'legal_address_en',
    'contact_email',
    'support_email',
    'dpo_email',
    'phone',
    'retention_logs',
    'retention_messages',
    'retention_accounts',
    'cloud_provider',
    'cloud_region',
    'analytics_tools',
    'billing_provider',
    'bank_name_ru',
    'bank_name_en',
    'bank_account',
    'bank_bik',
    'bank_correspondent_account',
    'bank_inn',
    'bank_address_ru',
    'bank_address_en',
];

export class LegalPage extends PlatformPage {
    static override properties: PropertyDeclarations = {
        kind: { type: String },
    }
    declare kind: string;
;

    static override styles: CSSResultGroup = [PlatformPage.styles, ...marketingPublicContentPageStyles];

    constructor() {
        super();
        this.kind = 'policy';
        this._localeSel = this.select((s: Record<string, any>) => s.i18n.locale);
        this._bundleSel = this.select((s: Record<string, any>) => s.i18n.translations[s.i18n.locale]);
        this._siteBundle = this.useOp('frontend/public_site_bundle');
    }
    private _localeSel: SelectController<any>;
    private _bundleSel: SelectController<any>;
    private _siteBundle: OpController;


    override connectedCallback(): void {
        super.connectedCallback();
        void this._siteBundle.run(null);
        queueMicrotask(() => this._syncDocumentMeta());
    }

    _spec() {
        if (!isLegalKind(this.kind)) {
            throw new Error(`legal-page: unknown kind ${this.kind}`);
        }
        return LEGAL_KINDS[this.kind];
    }

    _syncDocumentMeta() {
        if (typeof window === 'undefined') return;
        const spec = this._spec();
        const origin = window.location.origin;
        applyPublicDocumentMeta({
            title: this._lt('title', undefined, spec.ns),
            description: this._lt('updated', undefined, spec.ns),
            canonicalUrl: `${origin}${spec.path}`,
            ogImageUrl: `${origin}/static/frontend/assets/images/main_img.png`,
        });
    }

    _legalRecord() {
        const bundleRes = this._siteBundle.lastResult;
        if (!isPlainRecord(bundleRes)) {
            return null;
        }
        const legal = bundleRes.legal;
        if (!isPlainRecord(legal)) {
            return null;
        }
        return legal;
    }

    _legalI18nVars() {
        const legal = this._legalRecord();
        if (!legal) {
            return {};
        }
        const vars: Record<string, any> = {};
        for (const key of LEGAL_I18N_STRING_KEYS) {
            const value = legal[key];
            if (typeof value !== 'string' || value === '') {
                throw new Error(`legal-page: legal.${key} required`);
            }
            vars[key] = value;
        }
        if (typeof legal.min_age !== 'number') {
            throw new Error('legal-page: legal.min_age required');
        }
        vars.min_age = legal.min_age;
        return vars;
    }

    _lt(key: string, vars: any, ns: any) {
        return this.t(key, mergePlatformI18nVars({ ...this._legalI18nVars(), ...vars }), ns);
    }

    _bundleSection(index: number) {
        const ns = this._spec().ns;
        const bundle = this._bundleSel.value;
        if (!bundle || !bundle[ns]) return null;
        const section = bundle[ns][`section_${index}`];
        if (!section) return null;
        return section;
    }

    _renderSection(index: number) {
        const ns = this._spec().ns;
        const data = this._bundleSection(index);
        if (!data) return null;
        return html`
            <section>
                <h2>${this._lt(`section_${index}.title`, undefined, ns)}</h2>
                ${PARAGRAPH_KEYS.map((paragraphKey) =>
                    typeof data[paragraphKey] === 'string'
                        ? html`<p>${this._lt(`section_${index}.${paragraphKey}`, undefined, ns)}</p>`
                        : null,
                )}
                ${Array.isArray(data.list)
                    ? html`<ul>
                          ${data.list.map((_item: unknown, listIndex: number) =>
                                  html`<li>${this._lt(`section_${index}.list.${listIndex}`, undefined, ns)}</li>`,
                          )}
                      </ul>`
                    : null}
            </section>
        `;
    }

    override render(): TemplateResult {
        const spec = this._spec();
        const ns = spec.ns;
        const total = spec.sections;
        const indices = Array.from({ length: total }, (_value, index) => index + 1);
        return html`
            <landing-header></landing-header>
            <div class="marketing-page-container">
                <div class="marketing-content">
                    <header class="marketing-content-hero">
                        <h1 class="marketing-content-title">${this._lt('title', undefined, ns)}</h1>
                        <p class="updated">${this._lt('updated', undefined, ns)} ${this._lt('updated_at', undefined, ns)}</p>
                    </header>
                    <div class="marketing-prose">${indices.map((index) => this._renderSection(index))}</div>
                </div>
                <landing-footer></landing-footer>
            </div>
        `;
    }
}

customElements.define('legal-page', LegalPage);
