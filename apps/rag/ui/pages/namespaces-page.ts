/**
 * NamespacesPage — список namespaces сервиса RAG.
 *
 * Зона ответственности: показать список (или empty/loading), открыть модалку
 * создания. Доменные данные тянутся через `useResource('rag/namespaces')`,
 * клик по карточке навигирует на `namespace_detail`.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ResourceController } from '@platform/lib/base/use-resource.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-empty-state.js';
import '../components/namespace-card.js';

export class NamespacesPage extends PlatformPage {
    static i18nNamespace = 'rag';

    private _namespaces: ResourceController;

    static override styles = [
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
            platform-empty-state {
                flex-grow: 1;
            }
        `,
    ];

    constructor() {
        super();
        this._namespaces = this.useResource('rag/namespaces', { autoload: true });
    }

    private _openCreate() {
        this.openModal('rag.namespace_create');
    }

    override render() {
        if (this._namespaces.loading) {
            return html`<platform-empty-state loading></platform-empty-state>`;
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
                    ${items.map((ns: Record<string, unknown>) => html`<namespace-card .namespace=${ns}></namespace-card>`)}
                </div>
            ` : html`
                <platform-empty-state
                    icon="folder"
                    title=${this.t('namespace_list.empty_title')}
                    hint=${this.t('namespace_list.empty_hint')}
                ></platform-empty-state>
            `}
        `;
    }
}

customElements.define('rag-namespaces-page', NamespacesPage);
