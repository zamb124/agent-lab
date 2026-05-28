/**
 * Страница legal — отображает Privacy Policy или Terms of Service по атрибуту kind.
 *
 * Контент берется из i18n-бандлов:
 *   privacy.json (namespace 'privacy')
 *   terms.json   (namespace 'terms')
 *
 * Структура бандла: title, updated, updated_at, section_1..N с {title, p1..p3?, list?}.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
const PRIVACY_SECTIONS = 14;
const TERMS_SECTIONS = 13;
const PARAGRAPH_KEYS = ['p1', 'p2', 'p3'];

export class LegalPage extends PlatformPage {
    static properties = {
        kind: { type: String },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                max-width: 880px;
                margin: 0 auto;
                padding: var(--space-12) var(--space-6);
                color: var(--text-primary);
            }
            .back-row {
                margin-bottom: var(--space-8);
                display: flex;
                justify-content: flex-start;
            }
            h1 { font-size: var(--text-3xl); margin-bottom: var(--space-2); }
            .updated { color: var(--text-secondary); font-size: var(--text-sm); margin-bottom: var(--space-8); }
            section { margin-bottom: var(--space-8); }
            section h2 { font-size: var(--text-xl); margin-bottom: var(--space-3); }
            section p { color: var(--text-secondary); line-height: 1.7; margin-bottom: var(--space-3); }
            section ul { padding-left: 20px; }
            section li { color: var(--text-secondary); line-height: 1.7; margin-bottom: var(--space-2); }
        `,
    ];

    constructor() {
        super();
        this.kind = 'policy';
        this._localeSel = this.select((s) => s.i18n.locale);
        this._bundleSel = this.select((s) => s.i18n.translations[s.i18n.locale]);
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

    _goHome() {
        this.navigate('landing', {});
    }

    _renderSection(index) {
        const ns = this._ns();
        const data = this._bundleSection(index);
        if (!data) return null;
        return html`
            <section>
                <h2>${this.t(`section_${index}.title`, undefined, ns)}</h2>
                ${PARAGRAPH_KEYS.map((pk) =>
                    typeof data[pk] === 'string'
                        ? html`<p>${this.t(`section_${index}.${pk}`, undefined, ns)}</p>`
                        : null,
                )}
                ${Array.isArray(data.list)
                    ? html`<ul>
                          ${data.list.map(
                              (_item, idx) => html`<li>${this.t(`section_${index}.list.${idx}`, undefined, ns) || data.list[idx]}</li>`,
                          )}
                      </ul>`
                    : null}
            </section>
        `;
    }

    render() {
        const ns = this._ns();
        const total = this._sectionsCount();
        const indices = Array.from({ length: total }, (_v, i) => i + 1);
        return html`
            <div class="back-row">
                <glass-button variant="ghost" @click=${this._goHome}>
                    <platform-icon name="arrow-left" size="18"></platform-icon>
                    ${this.t('support_page.back_home')}
                </glass-button>
            </div>
            <h1>${this.t('title', undefined, ns)}</h1>
            <p class="updated">
                ${this.t('updated', undefined, ns)} ${this.t('updated_at', undefined, ns)}
            </p>
            ${indices.map((i) => this._renderSection(i))}
        `;
    }
}

customElements.define('legal-page', LegalPage);
