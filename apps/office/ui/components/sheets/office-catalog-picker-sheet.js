/**
 * office-catalog-picker-sheet — выбор каталога на mobile.
 *
 * kind: 'office.catalog_picker'
 */

import { html, css } from 'lit';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import { catalogsResource } from '../../events/resources/catalogs.resource.js';
import '@platform/lib/components/platform-icon.js';

const CATALOGS_NAME = catalogsResource.name;
const DOCUMENTS_OP = 'office/documents';

export class OfficeCatalogPickerSheet extends PlatformBottomSheet {
    static bottomSheetKind = 'office.catalog_picker';
    static i18nNamespace = 'documents';

    static styles = [
        PlatformBottomSheet.styles,
        css`
            .list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .item {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
            }
            .item.active {
                background: var(--documents-selected-bg, var(--accent-subtle));
                border-color: var(--accent);
                color: var(--accent);
                font-weight: 600;
            }
            .count {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.snap = 'half';
        this._catalogs = this.useResource(CATALOGS_NAME);
        this._documents = this.useOp(DOCUMENTS_OP);
    }

    connectedCallback() {
        super.connectedCallback();
        this.heading = this.t('explorer.catalogPickerTitle');
        this._catalogs.load(null);
    }

    _activeCatalogId() {
        const state = this._documents.state;
        if (typeof state.activeCatalogId === 'string' && state.activeCatalogId.length > 0) {
            return state.activeCatalogId;
        }
        const items = this._catalogs.items;
        return items.length > 0 ? items[0].catalog_id : '';
    }

    _select(catalogId) {
        if (typeof catalogId !== 'string' || catalogId.length === 0) return;
        this._documents.setActiveCatalog({ catalogId });
        this._documents.setFilterCatalogs({ catalogIds: [catalogId] });
        this._documents.clearBindingSelection(null);
        this._requestClose();
    }

    renderBody() {
        const items = Array.isArray(this._catalogs.items) ? this._catalogs.items : [];
        const activeId = this._activeCatalogId();
        return html`
            <div class="list">
                ${items.map((catalog) => html`
                    <button
                        class="item ${catalog.catalog_id === activeId ? 'active' : ''}"
                        type="button"
                        @click=${() => this._select(catalog.catalog_id)}
                    >
                        <span>${catalog.title}</span>
                        <span class="count">${catalog.file_count}</span>
                    </button>
                `)}
            </div>
        `;
    }
}

customElements.define('office-catalog-picker-sheet', OfficeCatalogPickerSheet);
registerBottomSheetKind(OfficeCatalogPickerSheet.bottomSheetKind, 'office-catalog-picker-sheet');
