/**
 * OfficeCatalogCreateModal — создание каталога документов.
 *
 * `useForm('office/catalog_create_form')` → submit диспатчит
 * `catalogsResource.events.CREATE_REQUESTED`. После CREATED — closeAfterSave.
 * По умолчанию `is_public: true` (разделяемый каталог в текущем namespace).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-switch.js';

const FORM_NAME = 'office/catalog_create_form';
const CATALOGS_NAME = 'office/catalogs';

export class OfficeCatalogCreateModal extends PlatformFormModal {
    static modalKind = 'office.catalog_create';
    static i18nNamespace = 'documents';

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-4); }
            .switch-row {
                display: flex; align-items: center; justify-content: space-between;
                gap: var(--space-3);
            }
            .switch-label { font-size: var(--text-sm); color: var(--text-primary); font-weight: 500; }
            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
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
        this._catalogs = this.useResource(CATALOGS_NAME);
        this._form = this.useForm(FORM_NAME);
    }

    connectedCallback() {
        super.connectedCallback();
        this._form.openForm({ title: '', is_public: true });
        this.useEvent(this._catalogs.resource.events.CREATED, () => this.closeAfterSave());
    }

    disconnectedCallback() {
        this._form.close();
        super.disconnectedCallback();
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        const draft = this._form.draft;
        this.isDirty = typeof draft.title === 'string' && draft.title.length > 0;
    }

    _onTitleInput(e) { this._form.setField('title', e.target.value); }
    _onPublicChange(e) { this._form.setField('is_public', Boolean(e.detail.value)); }

    async _performSave() { this._form.submit(); }

    _saveHeaderTitle() {
        return this._form.submitting
            ? this.t('catalog_create_modal.saving')
            : this.t('catalog_create_modal.submit');
    }

    renderHeader() { return this.t('catalog_create_modal.header'); }

    renderSaveHeaderButton() {
        const draft = this._form.draft;
        const has_title = typeof draft.title === 'string' && draft.title.trim().length > 0;
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._form.submitting || !has_title,
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
                    <label class="form-label">${this.t('catalog_create_modal.label_title')}</label>
                    <input type="text" class="form-input"
                           autocomplete="off" spellcheck="false"
                           placeholder=${this.t('catalog_create_modal.title_placeholder')}
                           .value=${draft.title}
                           @input=${this._onTitleInput} />
                    ${this._renderFieldError('title')}
                </div>
                <div class="form-group">
                    <div class="switch-row">
                        <span class="switch-label">${this.t('catalog_create_modal.switch_public')}</span>
                        <platform-switch
                            ?checked=${Boolean(draft.is_public)}
                            @change=${this._onPublicChange}
                        ></platform-switch>
                    </div>
                    <div class="hint">${this.t('catalog_create_modal.create_public_hint')}</div>
                </div>
            </form>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('catalog_create_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._form.submitting}
                        @click=${() => this._performSave()}>
                    ${this._form.submitting
                        ? this.t('catalog_create_modal.saving')
                        : this.t('catalog_create_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('office-catalog-create-modal', OfficeCatalogCreateModal);
registerModalKind(OfficeCatalogCreateModal.modalKind, 'office-catalog-create-modal');
