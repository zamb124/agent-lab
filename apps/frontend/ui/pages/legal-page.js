/**
 * Страница legal — Privacy Policy или Terms of Service по атрибуту kind.
 */
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import { mergePlatformI18nVars } from '@platform/lib/utils/platform-i18n-vars.js';
import { applyPublicDocumentMeta } from '../utils/public-document-meta.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

const PRIVACY_SECTIONS = 14;
const TERMS_SECTIONS = 13;
const PARAGRAPH_KEYS = ['p1', 'p2', 'p3'];

export class LegalPage extends PlatformPage {
    static properties = {
        kind: { type: String },
    };

    static styles = [PlatformPage.styles, ...marketingPublicContentPageStyles];

    constructor() {
        super();
        this.kind = 'policy';
        this._localeSel = this.select((s) => s.i18n.locale);
        this._bundleSel = this.select((s) => s.i18n.translations[s.i18n.locale]);
        this._siteBundle = this.useOp('frontend/public_site_bundle');
    }

    connectedCallback() {
        super.connectedCallback();
        void this._siteBundle.run(null);
        queueMicrotask(() => this._syncDocumentMeta());
    }

    _syncDocumentMeta() {
        if (typeof window === 'undefined') return;
        const origin = window.location.origin;
        const path = this.kind === 'terms' ? '/terms' : '/policy';
        applyPublicDocumentMeta({
            title: this._lt('title', undefined, this._ns()),
            description: this._lt('updated', undefined, this._ns()),
            canonicalUrl: `${origin}${path}`,
            ogImageUrl: `${origin}/static/frontend/assets/images/main_img.png`,
        });
    }

    _ns() {
        return this.kind === 'terms' ? 'terms' : 'privacy';
    }

    _sectionsCount() {
        return this.kind === 'terms' ? TERMS_SECTIONS : PRIVACY_SECTIONS;
    }

    _legalRecord() {
        const bundleRes = this._siteBundle.lastResult;
        if (!bundleRes || typeof bundleRes !== 'object') {
            return null;
        }
        const legal = bundleRes.legal;
        if (!legal || typeof legal !== 'object') {
            return null;
        }
        return legal;
    }

    _legalI18nVars() {
        const legal = this._legalRecord();
        if (!legal) {
            return {};
        }
        return {
            company_name_ru: legal.company_name_ru,
            company_name_en: legal.company_name_en,
            legal_form_ru: legal.legal_form_ru,
            legal_form_en: legal.legal_form_en,
            contact_email: legal.contact_email,
            support_email: legal.support_email,
            dpo_email: legal.dpo_email,
            legal_address_ru: legal.legal_address_ru,
            legal_address_en: legal.legal_address_en,
        };
    }

    _lt(key, vars, ns) {
        return this.t(key, mergePlatformI18nVars({ ...this._legalI18nVars(), ...vars }), ns);
    }

    _bundleSection(index) {
        const ns = this._ns();
        const bundle = this._bundleSel.value;
        if (!bundle || !bundle[ns]) return null;
        return bundle[ns][`section_${index}`] || null;
    }

    _renderSection(index) {
        const ns = this._ns();
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
                          ${data.list.map(
                              (_item, listIndex) =>
                                  html`<li>${this._lt(`section_${index}.list.${listIndex}`, undefined, ns) || data.list[listIndex]}</li>`,
                          )}
                      </ul>`
                    : null}
            </section>
        `;
    }

    render() {
        const ns = this._ns();
        const total = this._sectionsCount();
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
