/**
 * OfficeDocumentRenameModal — переименование документа.
 *
 * props: { bindingId, currentTitle, catalogIds }.
 * `useForm('office/document_rename_form')` openForm с props в willUpdate.
 * Submit диспатчит `documentRenameOp.events.REQUESTED`. После SUCCEEDED —
 * closeAfterSave; список документов перезагружается фабрикой
 * (`onSuccess` в documentRenameOp).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

const FORM_NAME = 'office/document_rename_form';
const RENAME_OP_NAME = 'office/document_rename';

export class OfficeDocumentRenameModal extends PlatformFormModal {
    static modalKind = 'office.document_rename';
    static i18nNamespace = 'documents';

    static properties = {
        ...PlatformFormModal.properties,
        bindingId: { type: String },
        currentTitle: { type: String },
        catalogIds: { type: Array },
    };

    static styles = [
        ...PlatformFormModal.styles,
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
        this.bindingId = '';
        this.currentTitle = '';
        this.catalogIds = [];
        this._rename = this.useOp(RENAME_OP_NAME);
        this._form = this.useForm(FORM_NAME);
        this._seeded = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(this._rename.op.events.SUCCEEDED, () => this.closeAfterSave());
    }

    disconnectedCallback() {
        this._form.close();
        super.disconnectedCallback();
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (!this._seeded && typeof this.bindingId === 'string' && this.bindingId.length > 0) {
            this._form.openForm({
                binding_id: this.bindingId,
                title: typeof this.currentTitle === 'string' ? this.currentTitle : '',
                catalog_ids: Array.isArray(this.catalogIds) ? this.catalogIds : [],
            });
            this._seeded = true;
        }
        const draft = this._form.draft;
        const curr = typeof this.currentTitle === 'string' ? this.currentTitle : '';
        this.isDirty = typeof draft.title === 'string' && draft.title.trim() !== curr.trim();
    }

    _onTitleInput(e) { this._form.setField('title', e.target.value); }

    async _performSave() { this._form.submit(); }

    _saveHeaderTitle() {
        return this._form.submitting
            ? this.t('document_rename_modal.saving')
            : this.t('document_rename_modal.submit');
    }

    renderHeader() { return this.t('document_rename_modal.header'); }

    renderSaveHeaderButton() {
        const draft = this._form.draft;
        const has_title = typeof draft.title === 'string' && draft.title.trim().length > 0;
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._form.submitting || !has_title || !this.isDirty,
            title: this._saveHeaderTitle(),
        });
    }

    _renderFieldError(field) {
        const error_key = this._form.errors[field];
        if (!error_key) return null;
        return html`<div class="form-error">${this.t(error_key)}</div>`;
    }

    renderBody() {
        const draft = this._form.draft;
        return html`
            <form class="form-grid" @submit=${(e) => { e.preventDefault(); this._performSave(); }}>
                <div class="form-group">
                    <label class="form-label">${this.t('document_rename_modal.label_title')}</label>
                    <input type="text" class="form-input"
                           autocomplete="off" spellcheck="false"
                           .value=${draft.title}
                           @input=${this._onTitleInput} />
                    ${this._renderFieldError('title')}
                </div>
            </form>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('document_rename_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._form.submitting}
                        @click=${() => this._performSave()}>
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
