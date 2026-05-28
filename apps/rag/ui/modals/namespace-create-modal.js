/**
 * RagNamespaceCreateModal — создание нового namespace.
 *
 * Form: `rag/namespace_create_form` (createForm) — draft, валидация, submit.
 * Отправка прокидывает payload в `namespacesResource.events.CREATE_REQUESTED`,
 * фабрика делает POST `/rag/api/v1/namespaces` и эмитит CREATED/CREATE_FAILED.
 *
 * После CREATED модалка закрывается через `closeAfterSave()` —
 * `platform-modal-stack` снимает её из DOM. На CREATE_FAILED форма остаётся
 * открытой со старым черновиком (toast об ошибке диспатчит сама фабрика).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';

const FORM_NAME = 'rag/namespace_create_form';
const NAMESPACES_NAME = 'rag/namespaces';

export class RagNamespaceCreateModal extends PlatformFormModal {
    static modalKind = 'rag.namespace_create';
    static i18nNamespace = 'rag';

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-4); }
            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.headerSavePrimary = true;
        this._namespaces = this.useResource(NAMESPACES_NAME);
        this._form = this.useForm(FORM_NAME);
    }

    connectedCallback() {
        super.connectedCallback();
        this._form.openForm({ name: '', description: '' });
        this.useEvent(this._namespaces.resource.events.CREATED, () => {
            this.closeAfterSave();
        });
        this.useEvent(this._namespaces.resource.events.CREATE_FAILED, () => {
            this._form.openForm(this._form.draft);
        });
    }

    disconnectedCallback() {
        this._form.close();
        super.disconnectedCallback();
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.isDirty = this._isDraftDirty();
    }

    _isDraftDirty() {
        const draft = this._form.draft;
        if (typeof draft.name === 'string' && draft.name.length > 0) return true;
        if (typeof draft.description === 'string' && draft.description.length > 0) return true;
        return false;
    }

    _onNameChange(event) {
        const v = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._form.setField('name', v);
    }

    _onDescriptionChange(event) {
        const v = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._form.setField('description', v);
    }

    async _performSave() {
        this._form.submit();
    }

    _saveHeaderTitle() {
        return this._form.submitting
            ? this.t('namespace_create_modal.submitting')
            : this.t('namespace_create_modal.submit');
    }

    renderHeader() {
        return this.t('namespace_create_modal.header');
    }

    renderSaveHeaderButton() {
        const draft = this._form.draft;
        const has_name = typeof draft.name === 'string' && draft.name.trim().length > 0;
        const disabled = this._form.submitting || !has_name;
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled,
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
            <form class="form-grid" @submit=${(event) => { event.preventDefault(); this._performSave(); }}>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('namespace_create_modal.label_name')}
                    .hint=${this.t('namespace_create_modal.name_hint')}
                    .placeholder=${this.t('namespace_create_modal.name_placeholder')}
                    .value=${draft.name}
                    ?disabled=${this._form.submitting}
                    @change=${this._onNameChange}
                ></platform-field>
                ${this._renderFieldError('name')}

                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('namespace_create_modal.label_description')}
                    .placeholder=${this.t('namespace_create_modal.description_placeholder')}
                    .value=${draft.description}
                    ?disabled=${this._form.submitting}
                    @change=${this._onDescriptionChange}
                ></platform-field>
                ${this._renderFieldError('description')}
            </form>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button
                    type="button"
                    class="btn btn-secondary"
                    @click=${() => this.close()}
                >
                    ${this.t('namespace_create_modal.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${this._form.submitting}
                    @click=${() => this._performSave()}
                >
                    ${this._form.submitting
                        ? this.t('namespace_create_modal.submitting')
                        : this.t('namespace_create_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('rag-namespace-create-modal', RagNamespaceCreateModal);
registerModalKind(RagNamespaceCreateModal.modalKind, 'rag-namespace-create-modal');
