/**
 * OfficeNamespaceCreateModal — создание workspace через BFF documents.
 *
 * BFF проксирует запрос в CRM (`POST /documents/api/v1/namespaces`).
 * Шаблоны загружаются через `useOp('office/namespace_templates')` (autoload).
 * Отправка идёт в `namespacesResource.events.CREATE_REQUESTED` через
 * `useForm('office/namespace_create_form')`. После успеха — выбираем новый
 * namespace в platform-namespace selection и закрываем модалку.
 */

import { html, css } from 'lit';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { FormController, OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { setPlatformNamespaceSelection } from '@platform/lib/utils/platform-namespace.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-spinner.js';
import type {CSSResultGroup, PropertyValues} from 'lit';

const FORM_NAME = 'office/namespace_create_form';
const NAMESPACES_NAME = 'office/namespaces';
const TEMPLATES_NAME = 'office/namespace_templates';

export class OfficeNamespaceCreateModal extends PlatformFormModal {
    static modalKind = 'office.namespace_create';
    static i18nNamespace = 'documents';

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-4); }
            .template-grid {
                display: grid;
                gap: var(--space-2);
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            }
            .template-card {
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                padding: var(--space-3);
                cursor: pointer;
                text-align: left;
                transition: border-color var(--duration-fast),
                            background var(--duration-fast),
                            transform var(--duration-fast);
            }
            .template-card:hover {
                border-color: var(--accent);
                transform: translateY(-1px);
            }
            .template-card.active {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            .template-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: 600;
                margin-bottom: var(--space-1);
            }
            .template-description {
                color: var(--text-secondary);
                font-size: var(--text-xs);
                line-height: 1.4;
            }
            .empty-templates {
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                border: 1px dashed var(--glass-border-medium);
                border-radius: var(--radius-md);
            }
            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
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
        this._templates = this.useOp(TEMPLATES_NAME);
        this._namespaces = this.useResource(NAMESPACES_NAME);
        this._form = this.useForm(FORM_NAME);
        this._authSel = this.select((s) => s.auth.user);
        this._templateSeeded = false;
    }
    private _templates: OpController;
    private _namespaces: ResourceController;
    private _form: FormController;
    private _authSel: SelectController<unknown>;
    private _templateSeeded: boolean;


    override connectedCallback(): void {
        super.connectedCallback();
        this._form.openForm({ template_id: '', name: '', description: '' });
        if (!this._templates.lastResult && !this._templates.busy) {
            this._templates.run(null);
        }
        this.useEvent(this._namespaces.resource.events.CREATED, (event) => {
            this._onCreated((event.payload as Record<string, unknown>).item);
        });
        this.useEvent(this._namespaces.resource.events.CREATE_FAILED, () => {
            this._form.openForm(this._form.draft);
        });
    }

    override disconnectedCallback(): void {
        this._form.close();
        super.disconnectedCallback();
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this._maybeSeedTemplate();
        this.isDirty = this._isDraftDirty();
    }

    private _templateItems(): Array<Record<string, unknown>> {
        const result = this._templates.lastResult as { items?: unknown } | null;
        if (!result || !Array.isArray(result.items)) return [];
        return result.items as Array<Record<string, unknown>>;
    }

    private _maybeSeedTemplate() {
        if (this._templateSeeded) return;
        const items = this._templateItems();
        if (items.length === 0) return;
        const draft = this._form.draft;
        if (typeof draft.template_id === 'string' && draft.template_id.length > 0) {
            this._templateSeeded = true;
            return;
        }
        const first = items[0];
        if (first === undefined) {
            throw new Error('namespace-create-modal: template missing');
        }
        this._form.setField('template_id', first.template_id);
        this._templateSeeded = true;
    }

    private _isDraftDirty() {
        const draft = this._form.draft;
        if (typeof draft.name === 'string' && draft.name.length > 0) return true;
        if (typeof draft.description === 'string' && draft.description.length > 0) return true;
        return false;
    }

    private _onCreated(item: unknown) {
        const user = this._authSel.value as Record<string, unknown> | null;
        if (!user || typeof user.company_id !== 'string') {
            throw new Error('OfficeNamespaceCreateModal: cannot select created namespace without company_id');
        }
        setPlatformNamespaceSelection(user.company_id, (item as Record<string, unknown>).name as string);
        this.closeAfterSave();
    }

    private _onTemplateSelect(template_id: unknown) { this._form.setField('template_id', template_id); }
    private _onNameChange(event: CustomEvent<{ value?: unknown }>) {
        const v = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._form.setField('name', v);
    }

    private _onDescriptionChange(event: CustomEvent<{ value?: unknown }>) {
        const v = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._form.setField('description', v);
    }

    override async _performSave() {
        this._form.submit();
    }

    override _saveHeaderTitle() {
        return this._form.submitting
            ? this.t('namespace_modal.saving')
            : this.t('namespace_modal.submit');
    }

    override renderHeader() {
        return this.t('namespace_modal.header');
    }

    override renderSaveHeaderButton() {
        const draft = this._form.draft;
        const has_name = typeof draft.name === 'string' && draft.name.trim().length > 0;
        const has_template = typeof draft.template_id === 'string' && draft.template_id.length > 0;
        const disabled = this._form.submitting || !has_name || !has_template;
        return this._renderHeaderSaveIcon({
            onClick: () => { void this._performSave(); },
            disabled,
            title: this._saveHeaderTitle(),
        });
    }

    private _renderTemplates() {
        const items = this._templateItems();
        if (this._templates.busy && items.length === 0) {
            return html`<div class="empty-templates"><glass-spinner></glass-spinner></div>`;
        }
        if (items.length === 0) {
            return html`<div class="empty-templates">${this.t('namespace_modal.templates_empty')}</div>`;
        }
        const draft = this._form.draft;
        return html`
            <div class="template-grid">
                ${items.map((template: Record<string, unknown>) => html`
                    <button
                        type="button"
                        class="template-card ${draft.template_id === template.template_id ? 'active' : ''}"
                        @click=${() => this._onTemplateSelect(template.template_id)}
                    >
                        <div class="template-title">
                            <platform-icon name=${this._templateIcon(template.icon)} size="16"></platform-icon>
                            ${template.name}
                        </div>
                        <div class="template-description">
                            ${typeof template.description === 'string' && template.description.length > 0
                                ? template.description
                                : this.t('namespace_modal.template_no_description')}
                        </div>
                    </button>
                `)}
            </div>
        `;
    }

    private _templateIcon(icon: unknown) {
        if (typeof icon !== 'string' || icon.trim().length === 0) return 'folder';
        return icon.trim();
    }

    private _fieldError(field: string) {
        const error_key = this._form.errors[field];
        return error_key ? this.t(error_key) : '';
    }

    private _renderFieldError(field: string) {
        const text = this._fieldError(field);
        if (!text) return null;
        return html`<div class="form-error">${text}</div>`;
    }

    override renderBody() {
        const draft = this._form.draft;
        return html`
            <form class="form-grid" @submit=${(e: SubmitEvent) => { e.preventDefault(); void this._performSave(); }}>
                <div class="form-group">
                    <label class="form-label">${this.t('namespace_modal.label_template')}</label>
                    ${this._renderTemplates()}
                    ${this._renderFieldError('template_id')}
                    <div class="hint">${this.t('namespace_modal.template_hint')}</div>
                </div>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('namespace_modal.label_name')}
                    .hint=${this.t('namespace_modal.name_hint')}
                    .placeholder=${this.t('namespace_modal.name_placeholder')}
                    .value=${draft.name}
                    .error=${this._fieldError('name')}
                    ?disabled=${this._form.submitting}
                    @change=${this._onNameChange}
                ></platform-field>
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('namespace_modal.label_description')}
                    .placeholder=${this.t('namespace_modal.description_placeholder')}
                    .value=${draft.description}
                    .error=${this._fieldError('description')}
                    ?disabled=${this._form.submitting}
                    @change=${this._onDescriptionChange}
                ></platform-field>
            </form>
        `;
    }

    override renderFooter() {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('namespace_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._form.submitting}
                        @click=${() => { void this._performSave(); }}>
                    ${this._form.submitting
                        ? this.t('namespace_modal.saving')
                        : this.t('namespace_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('office-namespace-create-modal', OfficeNamespaceCreateModal);
registerModalKind(OfficeNamespaceCreateModal.modalKind, 'office-namespace-create-modal');
