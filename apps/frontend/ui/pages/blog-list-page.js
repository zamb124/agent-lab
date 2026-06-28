/**
 * Публичный список статей блога.
 */
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

export class BlogListPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static styles = [PlatformPage.styles, ...marketingPublicContentPageStyles];

    constructor() {
        super();
        this._listOp = this.useOp('frontend/public_blog_list');
        this._localeSel = this.select((s) => s.i18n.locale);
    }

    connectedCallback() {
        super.connectedCallback();
        void this._listOp.run(null);
    }

    _titleFor(row) {
        const locale = this._localeSel.value;
        if (locale === 'ru') return row.title_ru;
        if (locale === 'en') return row.title_en;
        throw new Error('blog-list-page: i18n.locale must be ru or en');
    }

    _summaryFor(row) {
        const locale = this._localeSel.value;
        if (locale === 'ru') return row.summary_ru;
        if (locale === 'en') return row.summary_en;
        throw new Error('blog-list-page: i18n.locale must be ru or en');
    }

    render() {
        const busy = this._listOp.busy;
        const err = this._listOp.error;
        const raw = this._listOp.lastResult;
        let items = [];
        if (raw && typeof raw === 'object' && Array.isArray(raw.items)) {
            items = raw.items;
        }
        return html`
            <landing-header></landing-header>
            <div class="marketing-page-container">
                <div class="marketing-content">
                    <header class="marketing-content-hero">
                        <h1 class="marketing-content-title">${this.t('blog_page.title')}</h1>
                        <p class="marketing-content-lede">${this.t('blog_page.subtitle')}</p>
                    </header>
                    ${busy ? html`<glass-spinner></glass-spinner>` : null}
                    ${err ? html`<p class="marketing-text-error">${this.t('blog_page.load_error')}</p>` : null}
                    ${!busy && !err && items.length === 0
                        ? html`<p class="marketing-text-muted">${this.t('blog_page.empty')}</p>`
                        : null}
                    <ul class="marketing-content-card-list">
                        ${items.map(
                            (row) => html`
                                <li class="marketing-content-card glass-medium">
                                    <h2 class="marketing-content-card-title">${this._titleFor(row)}</h2>
                                    <p class="marketing-content-card-summary">${this._summaryFor(row)}</p>
                                    <button
                                        type="button"
                                        class="marketing-text-link"
                                        @click=${() => this.navigate('blog-post', { slug: row.slug })}
                                    >
                                        ${this.t('blog_page.read')}
                                    </button>
                                </li>
                            `,
                        )}
                    </ul>
                </div>
                <landing-footer></landing-footer>
            </div>
        `;
    }
}

customElements.define('blog-list-page', BlogListPage);
