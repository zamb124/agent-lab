/**
 * Публичная страница статьи блога.
 */
import { html } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import { applyPublicDocumentMeta } from '../utils/public-document-meta.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-button.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

export class BlogPostPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static properties = {
        slug: { type: String },
    };

    static styles = [PlatformPage.styles, ...marketingPublicContentPageStyles];

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
            <div class="marketing-page-container">
                <div class="marketing-content">
                    <p>
                        <button type="button" class="marketing-text-link" @click=${() => this.navigate('blog', {})}>
                            ${this.t('blog_page.back')}
                        </button>
                    </p>
                    ${busy ? html`<glass-spinner></glass-spinner>` : null}
                    ${err && !hasPost ? html`<p class="marketing-text-error">${this.t('blog_page.post_error')}</p>` : null}
                    ${hasPost
                        ? html`
                              <header class="marketing-content-hero">
                                  <h1 class="marketing-content-title">${this._title(post)}</h1>
                              </header>
                              <div class="marketing-prose body">${unsafeHTML(this._body(post))}</div>
                              <div class="marketing-content-cta">
                                  <platform-button variant="primary" @click=${() => this.navigate('digital-workers', {})}>
                                      ${this.t('blog_page.cta_demo')}
                                  </platform-button>
                              </div>
                          `
                        : null}
                </div>
                <landing-footer></landing-footer>
            </div>
        `;
    }
}

customElements.define('blog-post-page', BlogPostPage);
