/**
 * NamespacesPage — список namespaces сервиса RAG.
 *
 * Зона ответственности: показать список (или empty/loading), открыть модалку
 * создания. Доменные данные тянутся через `useResource('rag/namespaces')`,
 * клик по карточке навигирует на `namespace_detail`.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/namespace-card.js';

export class NamespacesPage extends PlatformPage {
    static i18nNamespace = 'rag';

    static styles = [
        PlatformPage.styles,
        buttonStyles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
                gap: var(--space-6);
                flex-grow: 1;
            }
            .empty,
            .loading {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                flex-grow: 1;
                text-align: center;
                padding: var(--space-12);
            }
            .empty-icon {
                width: 80px; height: 80px;
                display: flex; align-items: center; justify-content: center;
                margin-bottom: var(--space-4);
                opacity: 0.3;
                color: var(--text-tertiary);
            }
            .empty-text {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }
            .empty-hint { font-size: var(--text-sm); color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this._namespaces = this.useResource('rag/namespaces', { autoload: true });
    }

    _openCreate() {
        this.openModal('rag.namespace_create');
    }

    render() {
        if (this._namespaces.loading) {
            return html`
                <div class="loading">
                    <glass-spinner size="lg"></glass-spinner>
                </div>
            `;
        }

        const items = this._namespaces.items;

        return html`
            <page-header
                title=${this.t('namespace_list.header_title')}
                subtitle=${this.t('namespace_list.header_subtitle')}
            >
                <button slot="actions" class="btn btn-primary" @click=${() => this._openCreate()}>
                    <platform-icon name="plus" size="18"></platform-icon>
                    <span>${this.t('namespace_list.create_button')}</span>
                </button>
            </page-header>
            ${items.length > 0 ? html`
                <div class="grid">
                    ${items.map((ns) => html`<namespace-card .namespace=${ns}></namespace-card>`)}
                </div>
            ` : html`
                <div class="empty">
                    <div class="empty-icon"><platform-icon name="folder" size="64"></platform-icon></div>
                    <div class="empty-text">${this.t('namespace_list.empty_title')}</div>
                    <div class="empty-hint">${this.t('namespace_list.empty_hint')}</div>
                </div>
            `}
        `;
    }
}

customElements.define('rag-namespaces-page', NamespacesPage);
