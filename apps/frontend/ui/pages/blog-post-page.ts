/**
 * Публичная страница статьи блога.
 */
import { html } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import { applyPublicDocumentMeta } from '../_helpers/public-document-meta.js';
import { getPlatformBrandBootstrap } from '@platform/lib/utils/platform-brand.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-button.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

export class BlogPostPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static override properties: PropertyDeclarations = {
        slug: { type: String },
    }
    declare slug: string;
;

    static override styles: CSSResultGroup = [PlatformPage.styles, ...marketingPublicContentPageStyles];

    constructor() {
        super();
        this.slug = '';
        this._postOp = this.useOp('frontend/public_blog_post');
        this._localeSel = this.select((s: Record<string, any>) => s.i18n.locale);
    }
    private _postOp: OpController;
    private _localeSel: SelectController<any>;


    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (changed.has('slug')) {
            const slug = this.slug;
            if (typeof slug !== 'string' || slug === '') {
                return;
            }
            void this._loadPost(slug);
        }
    }

    async _loadPost(slug: string) {
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
            title = (res as Record<string, any>).title_ru;
            description = (res as Record<string, any>).summary_ru;
            bodyHtml = (res as Record<string, any>).body_ru;
        } else if (locale === 'en') {
            title = (res as Record<string, any>).title_en;
            description = (res as Record<string, any>).summary_en;
            bodyHtml = (res as Record<string, any>).body_en;
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
        const brand = getPlatformBrandBootstrap();
        const platformName = brand ? brand.platformName : 'Platform';
        applyPublicDocumentMeta({
            title: `${title} | ${platformName}`,
            description,
            canonicalUrl: `${origin}/blog/${encodeURIComponent(slug)}`,
            ogImageUrl: `${origin}/static/frontend/assets/images/main_img.png`,
        });
    }

    _title(post: Record<string, any>) {
        const locale = this._localeSel.value;
        if (locale === 'ru') return post.title_ru;
        if (locale === 'en') return post.title_en;
        throw new Error('blog-post-page: i18n.locale must be ru or en');
    }

    _body(post: Record<string, any>) {
        const locale = this._localeSel.value;
        if (locale === 'ru') return post.body_ru;
        if (locale === 'en') return post.body_en;
        throw new Error('blog-post-page: i18n.locale must be ru or en');
    }

    override render(): TemplateResult {
        const busy = this._postOp.busy;
        const err = this._postOp.error;
        const post = this._postOp.lastResult;
        const hasPost = post && typeof post === 'object' && typeof (post as Record<string, any>).slug === 'string';
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
