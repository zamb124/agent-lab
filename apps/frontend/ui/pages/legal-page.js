/**
 * Страница legal — Privacy Policy или Terms of Service по атрибуту kind.
 */
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
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
    }

    connectedCallback() {
        super.connectedCallback();
        queueMicrotask(() => this._syncDocumentMeta());
    }

    _syncDocumentMeta() {
        if (typeof window === 'undefined') return;
        const origin = window.location.origin;
        const path = this.kind === 'terms' ? '/terms' : '/policy';
        applyPublicDocumentMeta({
            title: this.t('title', undefined, this._ns()),
            description: this.t('updated', undefined, this._ns()),
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
                <h2>${this.t(`section_${index}.title`, undefined, ns)}</h2>
                ${PARAGRAPH_KEYS.map((paragraphKey) =>
                    typeof data[paragraphKey] === 'string'
                        ? html`<p>${this.t(`section_${index}.${paragraphKey}`, undefined, ns)}</p>`
                        : null,
                )}
                ${Array.isArray(data.list)
                    ? html`<ul>
                          ${data.list.map(
                              (_item, listIndex) =>
                                  html`<li>${this.t(`section_${index}.list.${listIndex}`, undefined, ns) || data.list[listIndex]}</li>`,
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
                        <h1 class="marketing-content-title">${this.t('title', undefined, ns)}</h1>
                        <p class="updated">${this.t('updated', undefined, ns)} ${this.t('updated_at', undefined, ns)}</p>
                    </header>
                    <div class="marketing-prose">${indices.map((index) => this._renderSection(index))}</div>
                </div>
                <landing-footer></landing-footer>
            </div>
        `;
    }
}

customElements.define('legal-page', LegalPage);
