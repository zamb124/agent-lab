/**
 * Публичная страница статьи блога.
 */
import { html, css } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { applyPublicDocumentMeta } from '../utils/public-document-meta.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

export class BlogPostPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static properties = {
        slug: { type: String },
    };

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
                max-width: 820px;
                margin: 0 auto;
                padding: 100px 20px 80px;
                box-sizing: border-box;
            }
            h1 {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: clamp(28px, 4vw, 40px);
                margin: 0 0 24px;
                color: var(--landing-secondary, #e8e8e8);
            }
            .body {
                font-family: 'Fira Sans', sans-serif;
                font-size: 17px;
                line-height: 1.65;
                color: var(--landing-text-soft, rgba(232, 232, 232, 0.88));
            }
            .body :is(p, ul, ol) {
                margin: 0 0 16px;
            }
            .toolbar {
                margin-bottom: 28px;
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                align-items: center;
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
            .cta-row {
                margin-top: 40px;
                padding-top: 28px;
                border-top: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.12));
            }
            .cta-btn {
                padding: 14px 28px;
                border-radius: 40px;
                border: none;
                background: var(--landing-primary, #5768fe);
                color: #fff;
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
            }
        `,
    ];

    constructor() {
        super();
        this.slug = '';
        this._postOp = this.useOp('frontend/public_blog_post');
        this._localeSel = this.select((s) => s.i18n.locale);
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('slug')) {
            const slug = this.slug;
            if (typeof slug !== 'string' || slug === '') {
                return;
            }
            void this._loadPost(slug);
        }
    }

    async _loadPost(slug) {
        const res = await this._postOp.run({ slug });
        if (!res || typeof res !== 'object') {
            return;
        }
        if (typeof window === 'undefined') return;
        const origin = window.location.origin;
        const locale = this._localeSel.value;
        let title;
        let description;
        let bodyHtml;
        if (locale === 'ru') {
            title = res.title_ru;
            description = res.summary_ru;
            bodyHtml = res.body_ru;
        } else if (locale === 'en') {
            title = res.title_en;
            description = res.summary_en;
            bodyHtml = res.body_en;
        } else {
            throw new Error('blog-post-page: i18n.locale must be ru or en');
        }
        if (typeof title !== 'string' || title === '') {
            throw new Error('blog-post-page: title missing');
        }
        if (typeof description !== 'string' || description === '') {
            throw new Error('blog-post-page: summary missing');
        }
        if (typeof bodyHtml !== 'string') {
            throw new Error('blog-post-page: body missing');
        }
        applyPublicDocumentMeta({
            title: `${title} | Humanitec`,
            description,
            canonicalUrl: `${origin}/blog/${encodeURIComponent(slug)}`,
            ogImageUrl: `${origin}/static/frontend/assets/images/main_img.png`,
        });
    }

    _title(post) {
        const locale = this._localeSel.value;
        if (locale === 'ru') return post.title_ru;
        if (locale === 'en') return post.title_en;
        throw new Error('blog-post-page: i18n.locale must be ru or en');
    }

    _body(post) {
        const locale = this._localeSel.value;
        if (locale === 'ru') return post.body_ru;
        if (locale === 'en') return post.body_en;
        throw new Error('blog-post-page: i18n.locale must be ru or en');
    }

    render() {
        const busy = this._postOp.busy;
        const err = this._postOp.error;
        const post = this._postOp.lastResult;
        const hasPost = post && typeof post === 'object' && typeof post.slug === 'string';
        return html`
            <landing-header></landing-header>
            <div class="wrap">
                <div class="toolbar">
                    <button type="button" class="linkish" @click=${() => this.navigate('blog', {})}>
                        ${this.t('blog_page.back')}
                    </button>
                </div>
                ${busy ? html`<glass-spinner></glass-spinner>` : null}
                ${err && !hasPost ? html`<p class="err">${this.t('blog_page.post_error')}</p>` : null}
                ${hasPost
                    ? html`
                          <h1>${this._title(post)}</h1>
                          <div class="body">${unsafeHTML(this._body(post))}</div>
                          <div class="cta-row">
                              <button type="button" class="cta-btn" @click=${() => this.navigate('digital-workers', {})}>
                                  ${this.t('blog_page.cta_demo')}
                              </button>
                          </div>
                      `
                    : null}
            </div>
            <landing-footer></landing-footer>
        `;
    }
}

customElements.define('blog-post-page', BlogPostPage);
