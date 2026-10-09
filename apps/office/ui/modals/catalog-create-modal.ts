/**
 * OfficeCatalogCreateModal — создание каталога документов.
 *
 * `useForm('office/catalog_create_form')` → submit диспатчит
 * `catalogsResource.events.CREATE_REQUESTED`. После CREATED — closeAfterSave.
 * По умолчанию `company_visible: true` (каталог виден всей компании в текущем namespace).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import type { FormController, ResourceController } from '@platform/lib/base/use-resource.js';

const FORM_NAME = 'office/catalog_create_form';
const CATALOGS_NAME = 'office/catalogs';

export class OfficeCatalogCreateModal extends PlatformFormModal {
    static modalKind = 'office.catalog_create';
    static i18nNamespace = 'documents';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        parentCatalogId: { type: String },
    }
    declare parentCatalogId: string;

    private _catalogs: ResourceController;
    private _form: FormController;

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
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
        this.parentCatalogId = '';
        this._catalogs = this.useResource(CATALOGS_NAME);
        this._form = this.useForm(FORM_NAME);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._form.openForm({
            title: '',
            company_visible: true,
            parent_catalog_id: typeof this.parentCatalogId === 'string' ? this.parentCatalogId : '',
        });
        this.useEvent(this._catalogs.resource.events.CREATED, () => this.closeAfterSave());
    }

    override disconnectedCallback(): void {
        this._form.close();
        super.disconnectedCallback();
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        const draft = this._form.draft;
        this.isDirty = typeof draft.title === 'string' && draft.title.length > 0;
    }

    private _onTitleChange(e: CustomEvent<{ value?: unknown }>) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._form.setField('title', v);
    }
    private _onCompanyVisibleChange(e: CustomEvent<{ value?: unknown }>) { this._form.setField('company_visible', Boolean(e.detail.value)); }

    override async _performSave(): Promise<void> { this._form.submit(); }

    override _saveHeaderTitle() {
        return this._form.submitting
            ? this.t('catalog_create_modal.saving')
            : this.t('catalog_create_modal.submit');
    }

    override renderHeader(): TemplateResult | string { return this.t('catalog_create_modal.header'); }

    override renderSaveHeaderButton(): TemplateResult {
        const draft = this._form.draft;
        const has_title = typeof draft.title === 'string' && draft.title.trim().length > 0;
        return this._renderHeaderSaveIcon({
            onClick: () => { void this._performSave(); },
            disabled: this._form.submitting || !has_title,
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
                    .label=${this.t('catalog_create_modal.label_title')}
                    .placeholder=${this.t('catalog_create_modal.title_placeholder')}
                    .value=${draft.title}
                    .error=${titleErrorKey ? this.t(titleErrorKey) : ''}
                    ?disabled=${this._form.submitting}
                    @change=${this._onTitleChange}
                ></platform-field>
                <div class="form-group">
                    <div class="switch-row">
                        <span class="switch-label">${this.t('catalog_create_modal.switch_company_visible')}</span>
                        <platform-switch
                            ?checked=${Boolean(draft.company_visible)}
                            @change=${this._onCompanyVisibleChange}
                        ></platform-switch>
                    </div>
                    <div class="hint">${this.t('catalog_create_modal.create_company_visible_hint')}</div>
                </div>
            </form>
        `;
    }

    override renderFooter(): TemplateResult {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('catalog_create_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._form.submitting}
                        @click=${() => { void this._performSave(); }}>
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
