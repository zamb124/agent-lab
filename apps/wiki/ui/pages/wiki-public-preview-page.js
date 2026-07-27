/**
 * Страница по публичной ссылке: только чтение, без сайдбара и без сессии.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-rich-editor.js';

export class WikiPublicPreviewPage extends PlatformPage {
    static i18nNamespace = 'wiki';

    static properties = {
        token: { type: String },
        _page: { state: true },
        _failed: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                min-height: 100%;
            }

            .paper {
                max-width: var(--wiki-page-max-width);
                margin: 0 auto;
                padding: var(--space-8) var(--space-6) var(--space-10);
            }

            .icon {
                font-size: 48px;
                line-height: 1;
            }

            .title {
                margin: var(--space-2) 0 var(--space-6);
                font-size: 40px;
                font-weight: var(--font-bold);
                line-height: 1.15;
                letter-spacing: -0.02em;
                color: var(--text-primary);
            }

            .state {
                padding: var(--space-10);
                text-align: center;
                color: var(--text-tertiary);
            }

            .state-hint {
                margin-top: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-disabled);
            }

            @media (max-width: 767px) {
                .paper {
                    padding: var(--space-5) var(--space-4) var(--space-10);
                }
                .title {
                    font-size: 28px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.token = '';
        this._page = null;
        this._failed = false;
        this._publicPage = this.useOp('wiki/public_page');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('token') && this.token !== '') {
            void this._load();
        }
    }

    async _load() {
        this._failed = false;
        this._page = null;
        try {
            this._page = await this._publicPage.run({ link_token: this.token });
        } catch {
            // Отключённая или просроченная ссылка — обычный сценарий чтения,
            // а не сбой: показываем понятное объяснение вместо тоста ошибки.
            this._failed = true;
        }
    }

    render() {
        if (this._failed) {
            return html`<div class="state">
                ${this.t('public.not_found')}
                <div class="state-hint">${this.t('public.not_found_hint')}</div>
            </div>`;
        }
        if (this._page === null) {
            return html`<div class="state"><glass-spinner size="sm"></glass-spinner></div>`;
        }
        return html`
            <div class="paper">
                ${this._page.icon === '' ? '' : html`<div class="icon">${this._page.icon}</div>`}
                <h1 class="title">
                    ${this._page.title === '' ? this.t('page.untitled') : this._page.title}
                </h1>
                <platform-rich-editor readonly .value=${this._page.content}></platform-rich-editor>
            </div>
        `;
    }
}

customElements.define('wiki-public-preview-page', WikiPublicPreviewPage);
