/**
 * CRMSpacesPage — страница со всеми namespace компании.
 *
 * Маршрут: `/crm/spaces` (parent: `settings`).
 *
 * Источники данных:
 *   - useResource('crm/namespaces', { autoload: true }) — список namespace.
 *
 * UI: page-header + кнопка «Создать пространство» → modal `crm.namespace`
 * (mode='create'); сетка карточек namespace с кнопками:
 *   - «Настройки» → navigate('space', { itemId: name }) — отдельная страница
 *     `space-detail-page` с полным редактированием namespace и его типов.
 *   - «Открыть» → setPlatformNamespaceSelection + navigate('notes').
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { setPlatformNamespaceSelection } from '@platform/lib/utils/platform-namespace.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';

const NAMESPACES_NAME = 'crm/namespaces';

export class CRMSpacesPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
                margin-top: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .header-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
            }

            .toolbar {
                display: flex;
                gap: var(--space-2);
                padding: 0 var(--space-4) var(--space-3);
            }

            .body {
                flex: 1;
                min-height: 0;
                padding: 0 var(--space-4) var(--space-4);
                overflow-y: auto;
            }

            .center {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-6);
            }

            .grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            }

            .card {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-surface);
            }
            .card-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-base);
                font-weight: 600;
                color: var(--text-primary);
                margin: 0;
            }
            .card-name {
                font-family: var(--font-mono);
                color: var(--text-primary);
            }
            .card-description {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.4;
                white-space: pre-wrap;
                min-height: 1.4em;
            }
            .card-empty-description {
                color: var(--text-tertiary);
                font-style: italic;
            }
            .card-actions {
                display: flex;
                gap: 6px;
                flex-wrap: wrap;
                margin-top: var(--space-2);
            }
            .btn {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
            }
            .btn:hover { background: var(--crm-surface-muted); color: var(--text-primary); }
            .btn-primary {
                background: var(--accent);
                border-color: var(--accent);
                color: white;
            }
            .btn-primary:hover { filter: brightness(1.05); }
        `,
    ];

    constructor() {
        super();
        this._namespaces = this.useResource(NAMESPACES_NAME, { autoload: true });
        this._authSel = this.select((s) => s.auth.user);
    }

    _onCreate() {
        this.openModal('crm.namespace', { mode: 'create' });
    }

    _onEdit(name) {
        this.navigate('space', { itemId: name });
    }

    _onOpenSpace(name) {
        const user = this._authSel.value;
        if (!user || typeof user.company_id !== 'string') {
            throw new Error('CRMSpacesPage._onOpenSpace: company_id required');
        }
        setPlatformNamespaceSelection(user.company_id, name);
        this.navigate('notes');
    }

    render() {
        const items = this._namespaces.items;
        const loading = this._namespaces.loading && items.length === 0;
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <div class="header-wrap">
                <page-header
                    title=${this.t('spaces_page.title')}
                    subtitle=${this.t('spaces_page.subtitle')}
                ></page-header>
            </div>
            <div class="toolbar">
                <button type="button" class="btn btn-primary" @click=${() => this._onCreate()}>
                    <platform-icon name="plus" size="14"></platform-icon>
                    ${this.t('spaces_page.action_create')}
                </button>
            </div>
            <div class="body">
                ${loading
                    ? html`<div class="center"><glass-spinner size="lg"></glass-spinner></div>`
                    : items.length === 0
                        ? html`
                            <div class="center">
                                <platform-icon name="folder" size="48"></platform-icon>
                                <p>${this.t('spaces_page.empty_message')}</p>
                            </div>
                        `
                        : html`
                            <div class="grid">
                                ${items.map((ns) => this._renderCard(ns))}
                            </div>
                        `}
            </div>
        `;
    }

    _renderCard(ns) {
        const description = typeof ns.description === 'string' && ns.description.length > 0
            ? ns.description
            : '';
        return html`
            <article class="card">
                <h3 class="card-title">
                    <platform-icon name="folder" size="14"></platform-icon>
                    <span class="card-name">${ns.name}</span>
                </h3>
                ${description.length > 0
                    ? html`<p class="card-description">${description}</p>`
                    : html`<p class="card-description card-empty-description">${this.t('spaces_page.empty_description')}</p>`}
                <div class="card-actions">
                    <button type="button" class="btn btn-primary" @click=${() => this._onEdit(ns.name)}>
                        <platform-icon name="settings" size="12"></platform-icon>
                        ${this.t('spaces_page.action_settings')}
                    </button>
                    <button type="button" class="btn" @click=${() => this._onOpenSpace(ns.name)}>
                        <platform-icon name="arrow-right" size="12"></platform-icon>
                        ${this.t('spaces_page.action_open')}
                    </button>
                </div>
            </article>
        `;
    }
}

customElements.define('crm-spaces-page', CRMSpacesPage);
