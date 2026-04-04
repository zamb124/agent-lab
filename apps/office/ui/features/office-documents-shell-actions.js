/**
 * Глобальные действия «Документы»: новый документ, загрузка, событие перезагрузки списка.
 * Слушает window: office-documents-open-empty, office-documents-pick-file.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { OfficeStore } from '../store/office.store.js';
import { ensureActiveCatalogId } from '../utils/ensure-active-catalog.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

/** @typedef {'word'|'cell_xlsx'|'cell_csv'|'slide'} OfficeEmptyKind */

const OFFICE_EMPTY_DOC_STYLE_ID = 'office-empty-doc-modal-global-styles';

/**
 * glass-modal при open переносится в document.body — правила из shadow этого компонента
 * на слот-контент не действуют. Стили модалки задаём один раз на document.
 */
function ensureOfficeEmptyDocGlobalStyles() {
    if (document.getElementById(OFFICE_EMPTY_DOC_STYLE_ID)) {
        return;
    }
    const el = document.createElement('style');
    el.id = OFFICE_EMPTY_DOC_STYLE_ID;
    el.textContent = `
.office-empty-doc-modal {
    --office-type-accent: #5a9fd4;
    --office-type-accent-deep: #4a67c4;
}
.office-empty-doc-modal .empty-name-block {
    margin-bottom: var(--space-4, 1rem);
}
.office-empty-doc-modal .empty-name-label,
.office-empty-doc-modal .type-section-label {
    display: block;
    margin-bottom: var(--space-2, 0.5rem);
    font-size: var(--text-xs, 0.75rem);
    color: var(--text-secondary, #64748b);
}
.office-empty-doc-modal .type-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-3, 0.75rem);
}
@media (max-width: 420px) {
    .office-empty-doc-modal .type-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}
.office-empty-doc-modal .type-tile {
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-2, 0.5rem);
    min-height: 118px;
    width: 100%;
    margin: 0;
    padding: var(--space-3, 0.75rem) var(--space-2, 0.5rem);
    font: inherit;
    text-align: center;
    cursor: pointer;
    color: inherit;
    border: 2px solid var(--border-default, #e2e8f0);
    border-radius: var(--radius-lg, 12px);
    background: var(--glass-solid-subtle, #f8fafc);
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
    transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
    position: relative;
    -webkit-tap-highlight-color: transparent;
}
.office-empty-doc-modal .type-tile:hover:not(:disabled):not(.type-tile--disabled) {
    border-color: var(--office-type-accent);
    background: color-mix(in srgb, var(--office-type-accent) 8%, var(--glass-solid-subtle, #f8fafc));
}
.office-empty-doc-modal .type-tile--selected {
    border-color: var(--office-type-accent-deep);
    background: color-mix(in srgb, var(--office-type-accent) 16%, var(--glass-solid-subtle, #f8fafc));
    box-shadow:
        0 0 0 1px var(--office-type-accent-deep),
        0 4px 14px color-mix(in srgb, var(--office-type-accent-deep) 24%, transparent);
}
.office-empty-doc-modal .type-tile--selected::after {
    content: "";
    position: absolute;
    top: 8px;
    right: 8px;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--office-type-accent-deep);
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E");
    background-size: 12px 12px;
    background-position: center;
    background-repeat: no-repeat;
}
.office-empty-doc-modal .type-tile--disabled {
    opacity: 0.55;
    cursor: not-allowed;
    pointer-events: none;
    box-shadow: none;
}
.office-empty-doc-modal .type-tile-label {
    font-size: var(--text-xs, 0.75rem);
    font-weight: 600;
    color: var(--text-primary, #0f172a);
    line-height: 1.2;
    max-width: 100%;
}
.office-empty-doc-modal .type-tile-hint {
    font-size: 10px;
    color: var(--text-tertiary, #94a3b8);
    line-height: 1.25;
    max-width: 100%;
}
.office-empty-doc-modal .type-tile .icon-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 52px;
    height: 52px;
    flex-shrink: 0;
}
.office-empty-doc-shell [slot="actions"] {
    display: flex;
    gap: var(--space-3, 0.75rem);
    justify-content: flex-end;
    flex-wrap: wrap;
}
`;
    document.head.appendChild(el);
}

export class OfficeDocumentsShellActions extends PlatformElement {
    static properties = {
        _emptyOpen: { state: true },
        _emptyTitle: { state: true },
        /** @type {OfficeEmptyKind} */
        _emptyKind: { state: true },
        _uploadBusy: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host {
                display: none;
            }
            .file-input {
                position: absolute;
                width: 0;
                height: 0;
                opacity: 0;
                pointer-events: none;
            }
        `,
    ];

    constructor() {
        super();
        this._emptyOpen = false;
        this._emptyTitle = '';
        /** @type {OfficeEmptyKind} */
        this._emptyKind = 'word';
        this._uploadBusy = false;
        this._onOpenEmpty = () => this._handleOpenEmpty();
        this._onPickFile = () => this._handlePickFile();
    }

    connectedCallback() {
        super.connectedCallback();
        ensureOfficeEmptyDocGlobalStyles();
        window.addEventListener('office-documents-open-empty', this._onOpenEmpty);
        window.addEventListener('office-documents-pick-file', this._onPickFile);
    }

    disconnectedCallback() {
        window.removeEventListener('office-documents-open-empty', this._onOpenEmpty);
        window.removeEventListener('office-documents-pick-file', this._onPickFile);
        super.disconnectedCallback();
    }

    _handleOpenEmpty() {
        if (!OfficeStore.state.integration.configured) {
            return;
        }
        this._emptyTitle = '';
        this._emptyKind = 'word';
        this._emptyOpen = true;
        this.requestUpdate();
    }

    _handlePickFile() {
        if (!OfficeStore.state.integration.configured || this._uploadBusy) {
            return;
        }
        this.renderRoot.querySelector('#office-shell-file-input')?.click();
    }

    _closeEmpty() {
        this._emptyOpen = false;
        this._emptyTitle = '';
        this._emptyKind = 'word';
    }

    _goEdit(bindingId) {
        window.history.pushState({}, '', `/documents/edit/${encodeURIComponent(bindingId)}`);
        window.dispatchEvent(new Event('popstate'));
    }

    /** @param {OfficeEmptyKind} kind */
    _selectKind(kind) {
        this._emptyKind = kind;
        this.requestUpdate();
    }

    _createPayload() {
        const k = this._emptyKind;
        if (k === 'word') {
            return { document_type: 'word' };
        }
        if (k === 'slide') {
            return { document_type: 'slide' };
        }
        if (k === 'cell_csv') {
            return { document_type: 'cell', spreadsheet_format: 'csv' };
        }
        return { document_type: 'cell', spreadsheet_format: 'xlsx' };
    }

    async _saveEmpty() {
        const api = this.services.officeApi;
        const title = (this._emptyTitle || '').trim();
        if (!api || title.length === 0) {
            return;
        }
        try {
            const catalogId = await ensureActiveCatalogId(api, (k) => this.i18n.t(k));
            const res = await api.createEmptyDocument(title, {
                ...this._createPayload(),
                catalog_id: catalogId,
            });
            this.success(this.i18n.t('list.created'));
            this._closeEmpty();
            window.dispatchEvent(new CustomEvent('office-documents-list-reload'));
            if (res.binding_id) {
                this._goEdit(res.binding_id);
            }
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        }
    }

    async _onFileSelected(e) {
        const input = e.target;
        const file = input.files?.[0];
        input.value = '';
        if (!file) {
            return;
        }
        const api = this.services.officeApi;
        if (!api) {
            return;
        }
        this._uploadBusy = true;
        try {
            const catalogId = await ensureActiveCatalogId(api, (k) => this.i18n.t(k));
            const res = await api.uploadDocument(file, undefined, catalogId);
            this.success(this.i18n.t('list.uploaded'));
            window.dispatchEvent(new CustomEvent('office-documents-list-reload'));
            if (res.binding_id) {
                this._goEdit(res.binding_id);
            }
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.error(msg);
        } finally {
            this._uploadBusy = false;
        }
    }

    /**
     * @param {OfficeEmptyKind} kind
     * @param {string} fileIconName
     * @param {string} labelKey
     */
    _typeCard(kind, fileIconName, labelKey) {
        const t = (k, p) => this.i18n.t(k, p);
        const selected = this._emptyKind === kind;
        return html`
            <button
                type="button"
                class="type-tile ${selected ? 'type-tile--selected' : ''}"
                aria-pressed=${selected ? 'true' : 'false'}
                @click=${() => this._selectKind(kind)}
            >
                <div class="icon-wrap">
                    <platform-icon
                        file-icon
                        name=${fileIconName}
                        .size=${44}
                        colored
                    ></platform-icon>
                </div>
                <span class="type-tile-label">${t(labelKey)}</span>
            </button>
        `;
    }

    /**
     * @param {string} fileIconName
     * @param {string} labelKey
     * @param {string} hintKey
     */
    _typeCardDisabled(fileIconName, labelKey, hintKey) {
        const t = (k, p) => this.i18n.t(k, p);
        return html`
            <div
                class="type-tile type-tile--disabled"
                role="group"
                aria-disabled="true"
                title=${t(hintKey)}
            >
                <div class="icon-wrap">
                    <platform-icon
                        file-icon
                        name=${fileIconName}
                        .size=${44}
                        colored
                    ></platform-icon>
                </div>
                <span class="type-tile-label">${t(labelKey)}</span>
                <span class="type-tile-hint">${t(hintKey)}</span>
            </div>
        `;
    }

    render() {
        const t = (k, p) => this.i18n.t(k, p);
        return html`
            <input
                id="office-shell-file-input"
                class="file-input"
                type="file"
                accept=".doc,.docx,.odt,.rtf,.txt,.xls,.xlsx,.ods,.csv,.ppt,.pptx,.odp,.pdf"
                @change=${this._onFileSelected}
            />
            <glass-modal
                class="office-empty-doc-shell"
                .open=${this._emptyOpen}
                heading=${t('list.emptyDocHeading')}
                @modal-closed=${() => this._closeEmpty()}
            >
                <div slot="content" class="office-empty-doc-modal">
                    <div class="empty-name-block">
                        <label class="empty-name-label" for="office-empty-title-input">${t('list.emptyDocLabel')}</label>
                        <glass-input
                            id="office-empty-title-input"
                            .value=${this._emptyTitle}
                            placeholder=${t('list.emptyDocNamePlaceholder')}
                            @input=${(e) => {
                                const v = e.detail?.value;
                                if (typeof v === 'string') {
                                    this._emptyTitle = v;
                                }
                            }}
                        ></glass-input>
                    </div>
                    <span class="type-section-label">${t('list.emptyDocTypesSection')}</span>
                    <div class="type-grid" role="group" aria-label=${t('list.emptyDocTypesSection')}>
                        ${this._typeCard('word', 'word', 'list.emptyDocTypeWord')}
                        ${this._typeCard('cell_xlsx', 'cell', 'list.emptyDocTypeExcel')}
                        ${this._typeCard('cell_csv', 'csv', 'list.emptyDocTypeCsv')}
                        ${this._typeCard('slide', 'slide', 'list.emptyDocTypeSlide')}
                        ${this._typeCardDisabled('pdf', 'list.emptyDocTypePdf', 'list.emptyDocPdfHint')}
                    </div>
                </div>
                <div slot="actions">
                    <platform-button variant="secondary" @click=${this._closeEmpty}>
                        ${t('list.cancel')}
                    </platform-button>
                    <platform-button variant="primary" @click=${() => void this._saveEmpty()}>
                        ${t('list.create')}
                    </platform-button>
                </div>
            </glass-modal>
        `;
    }
}

customElements.define('office-documents-shell-actions', OfficeDocumentsShellActions);
