/**
 * Публичный список статей блога.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

export class BlogListPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                min-height: var(--app-vh, 100vh);
                background: var(--landing-bg, #0f0f0f);
                color: var(--landing-text, #fff);
            }
            .wrap {
                max-width: 960px;
                margin: 0 auto;
                padding: 100px 20px 80px;
                box-sizing: border-box;
            }
            h1 {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: clamp(32px, 5vw, 48px);
                margin: 0 0 12px;
                color: var(--landing-secondary, #e8e8e8);
            }
            .sub {
                margin: 0 0 40px;
                font-size: 17px;
                color: rgba(232, 232, 232, 0.72);
            }
            ul {
                list-style: none;
                padding: 0;
                margin: 0;
                display: flex;
                flex-direction: column;
                gap: 16px;
            }
            li {
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
                padding: 20px 22px;
                background: rgba(255, 255, 255, 0.03);
            }
            .title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 22px;
                margin: 0 0 10px;
                color: var(--landing-secondary, #e8e8e8);
            }
            .sum {
                margin: 0 0 14px;
                font-size: 15px;
                line-height: 1.55;
                color: rgba(232, 232, 232, 0.78);
            }
            button.linkish {
                background: transparent;
                border: none;
                color: var(--landing-primary, #5768fe);
                font-family: 'Fira Sans', sans-serif;
                font-size: 15px;
                font-weight: 600;
                cursor: pointer;
                padding: 0;
                text-decoration: underline;
            }
            .err {
                color: #ff8a8a;
                font-size: 15px;
            }
            .empty {
                color: rgba(232, 232, 232, 0.65);
                font-size: 16px;
            }
        `,
    ];

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
            <div class="wrap">
                <h1>${this.t('blog_page.title')}</h1>
                <p class="sub">${this.t('blog_page.subtitle')}</p>
                ${busy ? html`<glass-spinner></glass-spinner>` : null}
                ${err ? html`<p class="err">${this.t('blog_page.load_error')}</p>` : null}
                ${!busy && !err && items.length === 0 ? html`<p class="empty">${this.t('blog_page.empty')}</p>` : null}
                <ul>
                    ${items.map(
                        (row) => html`
                            <li>
                                <h2 class="title">${this._titleFor(row)}</h2>
                                <p class="sum">${this._summaryFor(row)}</p>
                                <button
                                    type="button"
                                    class="linkish"
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
        `;
    }
}

customElements.define('blog-list-page', BlogListPage);
