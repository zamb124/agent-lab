/**
 * OfficeDocumentRenameModal — переименование документа.
 *
 * props: { fileId, currentTitle }.
 * `useForm('office/document_rename_form')` openForm с props в willUpdate.
 * Отправка диспатчит `documentRenameOp.events.REQUESTED`. После SUCCEEDED —
 * closeAfterSave; список документов перезагружается фабрикой
 * (`onSuccess` в documentRenameOp).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { FormController } from '@platform/lib/base/use-resource.js';

const FORM_NAME = 'office/document_rename_form';
const RENAME_OP_NAME = 'office/document_rename';

export class OfficeDocumentRenameModal extends PlatformFormModal {
    static modalKind = 'office.document_rename';
    static i18nNamespace = 'documents';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        fileId: { type: String },
        currentTitle: { type: String },
    }
    declare fileId: string;
    declare currentTitle: string;

    private _rename: OpController;
    private _form: FormController;
    private _seeded: boolean;

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-4); }
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
        this.fileId = '';
        this.currentTitle = '';
        this._rename = this.useOp(RENAME_OP_NAME);
        this._form = this.useForm(FORM_NAME);
        this._seeded = false;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useEvent(this._rename.op.events.SUCCEEDED, () => this.closeAfterSave());
    }

    override disconnectedCallback(): void {
        this._form.close();
        super.disconnectedCallback();
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (!this._seeded && typeof this.fileId === 'string' && this.fileId.length > 0) {
            this._form.openForm({
                file_id: this.fileId,
                title: typeof this.currentTitle === 'string' ? this.currentTitle : '',
            });
            this._seeded = true;
        }
        const draft = this._form.draft;
        const curr = typeof this.currentTitle === 'string' ? this.currentTitle : '';
        this.isDirty = typeof draft.title === 'string' && draft.title.trim() !== curr.trim();
    }

    private _onTitleChange(e: CustomEvent<{ value?: unknown }>) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._form.setField('title', v);
    }

    override async _performSave(): Promise<void> { this._form.submit(); }

    override _saveHeaderTitle() {
        return this._form.submitting
            ? this.t('document_rename_modal.saving')
            : this.t('document_rename_modal.submit');
    }

    override renderHeader(): TemplateResult | string { return this.t('document_rename_modal.header'); }

    override renderSaveHeaderButton(): TemplateResult {
        const draft = this._form.draft;
        const has_title = typeof draft.title === 'string' && draft.title.trim().length > 0;
        return this._renderHeaderSaveIcon({
            onClick: () => { void this._performSave(); },
            disabled: this._form.submitting || !has_title || !this.isDirty,
            title: this._saveHeaderTitle(),
        });
    }

    override renderBody(): TemplateResult {
        const draft = this._form.draft;
        const titleErrorKey = this._form.errors.title;
        return html`
            <form class="form-grid" @submit=${(e: SubmitEvent) => { e.preventDefault(); void this._performSave(); }}>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('document_rename_modal.label_title')}
                    .value=${draft.title}
                    .error=${titleErrorKey ? this.t(titleErrorKey) : ''}
                    ?disabled=${this._form.submitting}
                    @change=${this._onTitleChange}
                ></platform-field>
            </form>
        `;
    }

    override renderFooter(): TemplateResult {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('document_rename_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._form.submitting}
                        @click=${() => { void this._performSave(); }}>
                    ${this._form.submitting
                        ? this.t('document_rename_modal.saving')
                        : this.t('document_rename_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('office-document-rename-modal', OfficeDocumentRenameModal);
registerModalKind(OfficeDocumentRenameModal.modalKind, 'office-document-rename-modal');
