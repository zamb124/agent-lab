/**
 * Стартовый экран базы знаний: недавние правки и создание первой страницы.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

const RECENT_LIMIT = 12;

export class WikiHomePage extends PlatformPage {
    static i18nNamespace = 'wiki';

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                height: 100%;
                overflow-y: auto;
            }

            .wrap {
                max-width: var(--wiki-page-max-width);
                margin: 0 auto;
                padding: var(--space-8) var(--space-6);
            }

            .title {
                margin: 0;
                font-size: var(--text-3xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
            }

            .subtitle {
                margin: var(--space-2) 0 var(--space-6);
                color: var(--text-secondary);
            }

            .section-title {
                margin: var(--space-8) 0 var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: var(--tracking-wide);
                text-transform: uppercase;
            }

            .card {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                width: 100%;
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--wiki-surface-muted);
                color: var(--text-primary);
                font-family: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
            }

            .card + .card {
                margin-top: var(--space-2);
            }

            .card:hover {
                border-color: var(--wiki-accent);
            }

            .card-icon {
                font-size: 20px;
                line-height: 1;
            }

            .card-body {
                flex: 1;
                min-width: 0;
            }

            .card-title {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .card-meta {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .empty {
                padding: var(--space-8);
                text-align: center;
                color: var(--text-tertiary);
            }

            .empty-hint {
                margin-top: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-disabled);
            }
        `,
    ];

    constructor() {
        super();
        this._pages = this.useResource('wiki/pages');
        this._createPage = this.useOp('wiki/page_create');
        this._locale = this.select((state) => state.i18n.locale);
    }

    async _createRootPage() {
        const created = await this._createPage.run({ title: '' });
        if (created === null) {
            return;
        }
        await this._pages.load();
        this.navigate('wiki_page', { pageId: created.page.wiki_page_id });
    }

    _recent() {
        return [...this._pages.items]
            .sort((left, right) => String(right.updated_at).localeCompare(String(left.updated_at)))
            .slice(0, RECENT_LIMIT);
    }

    render() {
        const recent = this._recent();
        return html`
            <div class="wrap">
                <h1 class="title">${this.t('home.title')}</h1>
                <p class="subtitle">${this.t('home.subtitle')}</p>
                <platform-button variant="primary" data-wiki-home-create @click=${this._createRootPage}>
                    ${this.t('home.create_page')}
                </platform-button>

                ${recent.length === 0
                    ? html`<div class="empty">
                          ${this.t('home.empty')}
                          <div class="empty-hint">${this.t('home.empty_hint')}</div>
                      </div>`
                    : html`
                        <div class="section-title">${this.t('home.recent_title')}</div>
                        ${recent.map((page) => html`
                            <button
                                class="card"
                                type="button"
                                data-wiki-home-page=${page.wiki_page_id}
                                @click=${() => this.navigate('wiki_page', { pageId: page.wiki_page_id })}
                            >
                                <span class="card-icon">
                                    ${page.icon === ''
                                        ? html`<platform-icon name="file" size="18"></platform-icon>`
                                        : page.icon}
                                </span>
                                <span class="card-body">
                                    <span class="card-title">
                                        ${page.title === '' ? this.t('page.untitled') : page.title}
                                    </span>
                                    <span class="card-meta">
                                        ${formatPlatformDateTime(new Date(page.updated_at), this._locale.value)}
                                    </span>
                                </span>
                            </button>
                        `)}
                    `}
            </div>
        `;
    }
}

customElements.define('wiki-home-page', WikiHomePage);
