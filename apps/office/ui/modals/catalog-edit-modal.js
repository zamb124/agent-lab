/**
 * OfficeCatalogEditModal — изменение каталога (title + is_public).
 *
 * props (`UI_MODAL_OPEN.payload.props`): { catalogId, title, isPublic }.
 * `useForm('office/catalog_edit_form')` openForm с props в connectedCallback.
 * Submit диспатчит `catalogsResource.events.UPDATE_REQUESTED`.
 * После UPDATED — closeAfterSave.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';

const FORM_NAME = 'office/catalog_edit_form';
const CATALOGS_NAME = 'office/catalogs';

export class OfficeCatalogEditModal extends PlatformFormModal {
    static modalKind = 'office.catalog_edit';
    static i18nNamespace = 'documents';

    static properties = {
        ...PlatformFormModal.properties,
        catalogId: { type: String },
        title: { type: String },
        isPublic: { type: Boolean },
    };

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
        this.catalogId = '';
        this.title = '';
        this.isPublic = false;
        this._catalogs = this.useResource(CATALOGS_NAME);
        this._form = this.useForm(FORM_NAME);
        this._seeded = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(this._catalogs.resource.events.UPDATED, () => this.closeAfterSave());
    }

    disconnectedCallback() {
        this._form.close();
        super.disconnectedCallback();
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (!this._seeded && typeof this.catalogId === 'string' && this.catalogId.length > 0) {
            this._form.openForm({
                catalog_id: this.catalogId,
                title: this.title,
                is_public: Boolean(this.isPublic),
            });
            this._seeded = true;
        }
        const draft = this._form.draft;
        const dirty_title = typeof draft.title === 'string' && draft.title !== this.title;
        const dirty_public = Boolean(draft.is_public) !== Boolean(this.isPublic);
        this.isDirty = dirty_title || dirty_public;
    }

    _onTitleChange(e) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._form.setField('title', v);
    }
    _onPublicChange(e) { this._form.setField('is_public', Boolean(e.detail.value)); }

    async _performSave() { this._form.submit(); }

    _saveHeaderTitle() {
        return this._form.submitting
            ? this.t('catalog_edit_modal.saving')
            : this.t('catalog_edit_modal.submit');
    }

    renderHeader() { return this.t('catalog_edit_modal.header'); }

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
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('catalog_edit_modal.label_title')}
                    .value=${draft.title}
                    ?disabled=${this._form.submitting}
                    @change=${this._onTitleChange}
                ></platform-field>
                ${this._renderFieldError('title')}
                <div class="form-group">
                    <div class="switch-row">
                        <span class="switch-label">${this.t('catalog_edit_modal.switch_public')}</span>
                        <platform-switch
                            ?checked=${Boolean(draft.is_public)}
                            @change=${this._onPublicChange}
                        ></platform-switch>
                    </div>
                    <div class="hint">
                        ${draft.is_public
                            ? this.t('catalog_edit_modal.members_public_hint')
                            : this.t('catalog_edit_modal.members_private_hint')}
                    </div>
                </div>
            </form>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('catalog_edit_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._form.submitting}
                        @click=${() => this._performSave()}>
                    ${this._form.submitting
                        ? this.t('catalog_edit_modal.saving')
                        : this.t('catalog_edit_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('office-catalog-edit-modal', OfficeCatalogEditModal);
registerModalKind(OfficeCatalogEditModal.modalKind, 'office-catalog-edit-modal');
