/**
 * Публичная страница «О компании».
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { applyPublicDocumentMeta } from '../utils/public-document-meta.js';
import { FrontendLeadFormModal } from '../modals/lead-form-modal.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

export class AboutPage extends PlatformPage {
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
                max-width: 880px;
                margin: 0 auto;
                padding: 100px 20px 80px;
                box-sizing: border-box;
            }
            h1 {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: clamp(32px, 5vw, 48px);
                margin: 0 0 20px;
                color: var(--landing-secondary, #e8e8e8);
            }
            .lead {
                font-family: 'Fira Sans', sans-serif;
                font-size: 18px;
                line-height: 1.65;
                color: rgba(232, 232, 232, 0.85);
                margin: 0 0 36px;
            }
            h2 {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 26px;
                margin: 32px 0 12px;
                color: var(--landing-secondary, #e8e8e8);
            }
            p {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                line-height: 1.65;
                color: rgba(232, 232, 232, 0.78);
                margin: 0 0 16px;
            }
            .cta-btn {
                margin-top: 28px;
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

    connectedCallback() {
        super.connectedCallback();
        queueMicrotask(() => this._syncMeta());
    }

    _syncMeta() {
        if (typeof window === 'undefined') return;
        const origin = window.location.origin;
        applyPublicDocumentMeta({
            title: this.t('meta.about_title'),
            description: this.t('meta.about_description'),
            canonicalUrl: `${origin}/about`,
            ogImageUrl: `${origin}/static/frontend/assets/images/main_img.png`,
        });
    }

    render() {
        return html`
            <landing-header></landing-header>
            <div class="wrap">
                <h1>${this.t('about_page.title')}</h1>
                <p class="lead">${this.t('about_page.lead')}</p>
                <h2>${this.t('about_page.mission_title')}</h2>
                <p>${this.t('about_page.mission_text')}</p>
                <h2>${this.t('about_page.trust_title')}</h2>
                <p>${this.t('about_page.trust_text')}</p>
                <h2>${this.t('about_page.cta_title')}</h2>
                <button type="button" class="cta-btn" @click=${() => this.openModal(FrontendLeadFormModal)}>
                    ${this.t('about_page.cta_button')}
                </button>
            </div>
            <landing-footer></landing-footer>
        `;
    }
}

customElements.define('about-page', AboutPage);
