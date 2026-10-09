/**
 * office-catalog-picker-sheet — выбор каталога на mobile.
 *
 * kind: 'office.catalog_picker'
 */

import { html, css } from 'lit';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import { catalogsResource } from '../../events/resources/catalogs.resource.js';
import type { DocumentsOpController } from '../../events/documents.types.js';
import '@platform/lib/components/platform-icon.js';
import type { CSSResultGroup, TemplateResult } from 'lit';
import type { ResourceController } from '@platform/lib/base/use-resource.js';

const CATALOGS_NAME = catalogsResource.name;
const DOCUMENTS_OP = 'office/documents';

export class OfficeCatalogPickerSheet extends PlatformBottomSheet {
    static bottomSheetKind = 'office.catalog_picker';
    static i18nNamespace = 'documents';
    private _catalogs: ResourceController;
    private _documents: DocumentsOpController;

    static override styles: CSSResultGroup = [
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
        this._documents = this.useOp(DOCUMENTS_OP) as unknown as DocumentsOpController;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.heading = this.t('explorer.catalogPickerTitle');
        this._catalogs.load(null);
    }

    private _activeCatalogId() {
        const state = this._documents.state as { activeCatalogId?: unknown };
        if (typeof state.activeCatalogId === 'string' && state.activeCatalogId.length > 0) {
            return state.activeCatalogId;
        }
        return '';
    }

    private _selectRoot() {
        this._documents.setExplorerView({ explorerView: 'catalog' });
        this._documents.setActiveCatalog({ catalogId: null });
        this._documents.setFilterCatalogs({ catalogIds: [] });
        this._documents.clearFileSelection(null);
        this._requestClose();
    }

    private _select(catalogId: string) {
        if (typeof catalogId !== 'string' || catalogId.length === 0) return;
        this._documents.setActiveCatalog({ catalogId });
        this._documents.setFilterCatalogs({ catalogIds: [catalogId] });
        this._documents.clearFileSelection(null);
        this._requestClose();
    }

    override renderBody(): TemplateResult {
        const items = Array.isArray(this._catalogs.items) ? this._catalogs.items : [];
        const activeId = this._activeCatalogId();
        return html`
            <div class="list">
                <button
                    class="item ${activeId.length === 0 ? 'active' : ''}"
                    type="button"
                    @click=${() => this._selectRoot()}
                >
                    <span>${this.t('nav.allDocuments')}</span>
                </button>
                ${items.map((catalog: Record<string, unknown>) => html`
                    <button
                        class="item ${catalog.catalog_id === activeId ? 'active' : ''}"
                        type="button"
                        @click=${() => this._select(String(catalog.catalog_id ?? ''))}
                    >
                        <span>${catalog.title}</span>
                        <span class="count">${typeof catalog.file_count === 'number' ? catalog.file_count : 0}</span>
                    </button>
                `)}
            </div>
        `;
    }
}

customElements.define('office-catalog-picker-sheet', OfficeCatalogPickerSheet);
registerBottomSheetKind(OfficeCatalogPickerSheet.bottomSheetKind, 'office-catalog-picker-sheet');
