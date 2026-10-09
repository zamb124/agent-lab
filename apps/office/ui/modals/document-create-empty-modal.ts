/**
 * OfficeDocumentCreateEmptyModal — создание пустого документа
 * (word/cell/slide; csv через cell + spreadsheet_format='csv').
 *
 * props: { catalogId, openAfterCreate: true }.
 * useOp('office/document_create_empty').run({ title, document_type, catalog_id,
 * openAfterCreate, spreadsheetFormat? }) → бэкенд создаёт пустой OOXML по
 * шаблону. На SUCCEEDED фабрика навигирует в editor (если openAfterCreate)
 * и перезагружает documentsOp.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';

const CREATE_OP_NAME = 'office/document_create_empty';

const TYPE_OPTIONS = [
    { id: 'word',  documentType: 'word',  iconKey: 'word',  labelKey: 'document_create_empty_modal.type_word' },
    { id: 'cell',  documentType: 'cell',  iconKey: 'cell',  labelKey: 'document_create_empty_modal.type_cell' },
    { id: 'csv',   documentType: 'cell',  iconKey: 'csv',   labelKey: 'document_create_empty_modal.type_csv',   spreadsheetFormat: 'csv' },
    { id: 'slide', documentType: 'slide', iconKey: 'slide', labelKey: 'document_create_empty_modal.type_slide' },
];

export class OfficeDocumentCreateEmptyModal extends PlatformFormModal {
    static modalKind = 'office.document_create_empty';
    static i18nNamespace = 'documents';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        catalogId: { type: String },
        openAfterCreate: { type: Boolean },
        _title: { state: true },
        _typeId: { state: true },
    }
    declare catalogId: string;
    declare openAfterCreate: boolean;
    declare _title: string;
    declare _typeId: string;

    private _create: OpController;

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-4); }
            .type-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
                gap: var(--space-2);
            }
            .type-card {
                display: flex; flex-direction: column; align-items: center; justify-content: center;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .type-card:hover { border-color: var(--accent); transform: translateY(-1px); }
            .type-card.active { border-color: var(--accent); background: var(--accent-subtle); color: var(--accent); }
            .type-card .label {
                font-size: var(--text-xs);
                font-weight: 500;
                color: var(--text-secondary);
            }
            .type-card.active .label { color: var(--accent); }
            .footer-actions {
                display: flex; gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'sm';
        this.headerSavePrimary = true;
        this.catalogId = '';
        this.openAfterCreate = true;
        this._title = '';
        this._typeId = 'word';
        this._create = this.useOp(CREATE_OP_NAME);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useEvent(this._create.op.events.SUCCEEDED, () => this.closeAfterSave());
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.isDirty = this._title.length > 0;
    }

    private _onTitleChange(e: CustomEvent<{ value?: unknown }>) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._title = v;
    }
    private _onTypeSelect(id: string) { this._typeId = id; }

    override async _performSave(): Promise<void> {
        const opt = TYPE_OPTIONS.find((t) => t.id === this._typeId);
        if (!opt) {
            throw new Error(`OfficeDocumentCreateEmptyModal: unknown type "${this._typeId}"`);
        }
        const title = this._title.trim();
        if (title.length === 0) return;
        if (typeof this.catalogId !== 'string' || this.catalogId.length === 0) {
            throw new Error('OfficeDocumentCreateEmptyModal: catalogId prop required');
        }
        const payload: Record<string, unknown> = {
            title,
            document_type: opt.documentType,
            catalog_id: this.catalogId,
        };
        if (opt.spreadsheetFormat) payload.spreadsheet_format = opt.spreadsheetFormat;
        const created = await this._create.run(payload) as Record<string, unknown> | null;
        if (this.openAfterCreate === true && created && typeof created.file_id === 'string') {
            this.navigate('document_editor', { fileId: created.file_id });
        }
    }

    override _saveHeaderTitle() {
        return this._create.busy
            ? this.t('document_create_empty_modal.saving')
            : this.t('document_create_empty_modal.submit');
    }

    override renderHeader(): TemplateResult | string { return this.t('document_create_empty_modal.header'); }

    override renderSaveHeaderButton(): TemplateResult {
        return this._renderHeaderSaveIcon({
            onClick: () => { void this._performSave(); },
            disabled: this._create.busy || this._title.trim().length === 0,
            title: this._saveHeaderTitle(),
        });
    }

    override renderBody(): TemplateResult {
        return html`
            <form class="form-grid" @submit=${(e: SubmitEvent) => { e.preventDefault(); void this._performSave(); }}>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('document_create_empty_modal.label_title')}
                    .placeholder=${this.t('document_create_empty_modal.title_placeholder')}
                    .value=${this._title}
                    ?disabled=${this._create.busy}
                    @change=${this._onTitleChange}
                ></platform-field>
                <div class="form-group">
                    <label class="form-label">${this.t('document_create_empty_modal.section_type')}</label>
                    <div class="type-grid">
                        ${TYPE_OPTIONS.map((opt) => html`
                            <button type="button"
                                    class="type-card ${this._typeId === opt.id ? 'active' : ''}"
                                    @click=${() => this._onTypeSelect(opt.id)}>
                                <platform-icon file-icon name=${opt.iconKey} size="32"></platform-icon>
                                <span class="label">${this.t(opt.labelKey)}</span>
                            </button>
                        `)}
                    </div>
                </div>
            </form>
        `;
    }

    override renderFooter(): TemplateResult {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('document_create_empty_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._create.busy || this._title.trim().length === 0}
                        @click=${() => { void this._performSave(); }}>
                    ${this._create.busy
                        ? this.t('document_create_empty_modal.saving')
                        : this.t('document_create_empty_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('office-document-create-empty-modal', OfficeDocumentCreateEmptyModal);
registerModalKind(OfficeDocumentCreateEmptyModal.modalKind, 'office-document-create-empty-modal');
