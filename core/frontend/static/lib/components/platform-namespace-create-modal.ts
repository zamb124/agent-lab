/**
 * PlatformNamespaceCreateModal — канон модалки создания namespace.
 *
 * Сервис наследует класс и в конструкторе заполняет контроллеры:
 *   this._namespaces = this.useResource('<svc>/namespaces');
 *   this._form       = this.useForm('<svc>/namespace_create_form');
 *   this._templates  = this.useOp('<svc>/namespace_templates');  // опционально:
 *                                                            // секция выбора шаблона
 *   static modalKind = '<svc>.namespace_create';
 *
 * i18n — `static i18nNamespace = 'platform'`: канонный набор `namespace_modal.*`
 * живёт в бандле platform (одна модалка — одна формулировка):
 *   header, label_name, name_hint, name_placeholder, label_description,
 *   description_placeholder, cancel, submit, saving; при templates-op ещё
 *   label_template, template_hint, template_no_description, templates_empty.
 *
 * После CREATED выбирает созданный namespace в platform-namespace selection
 * и закрывается; CREATE_FAILED оставляет форму открытой с драфтом.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from './glass-form-modal.js';
import { setPlatformNamespaceSelection } from '../utils/platform-namespace.js';
import { isPlainRecord } from '../events/payload.js';
import type { SelectController } from '../events/select-controller.js';
import type { FormController, OpController, ResourceController } from '../base/use-resource.js';
import type { AuthUser } from '../events/reducers/auth.js';
import type { CSSResultGroup, PropertyValues, TemplateResult } from 'lit';
import './platform-icon.js';
import './platform-empty-state.js';
import './fields/platform-field.js';

export abstract class PlatformNamespaceCreateModal extends PlatformFormModal {
    static i18nNamespace = 'platform';
    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-4); }
            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
            .form-group .form-label {
                display: block;
                margin-bottom: var(--space-2);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
            }
            .form-group .hint {
                margin-top: var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            .form-error {
                margin-top: var(--space-2);
                color: var(--danger);
                font-size: var(--text-xs);
            }
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
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
            .template-description {
                margin-top: var(--space-1);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: var(--leading-normal);
            }
        `,
    ];

    _namespaces!: ResourceController;
    _form!: FormController;
    _templates: OpController | null = null;
    private _templateSeeded = false;
    private _authSel: SelectController<AuthUser | null>;

    constructor() {
        super();
        this.size = 'md';
        this.headerSavePrimary = true;
        this._authSel = this.select((s) => s.auth.user);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._form.openForm(this._initialDraft());
        if (this._templates !== null && !this._templates.lastResult && !this._templates.busy) {
            this._templates.run(null);
        }
        this.useEvent(this._namespaces.resource.events.CREATED, (event) => {
            if (!isPlainRecord(event.payload)) {
                throw new Error('PlatformNamespaceCreateModal: created payload required');
            }
            this._onCreated(event.payload.item);
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

    _initialDraft(): Record<string, unknown> {
        return this._templates === null
            ? { name: '', description: '' }
            : { template_id: '', name: '', description: '' };
    }

    private _templateItems(): Array<Record<string, unknown>> {
        const result = this._templates === null ? null : this._templates.lastResult;
        if (!isPlainRecord(result) || !Array.isArray(result.items)) {
            return [];
        }
        const rows: Record<string, unknown>[] = [];
        for (const item of result.items) {
            if (!isPlainRecord(item)) {
                throw new Error('PlatformNamespaceCreateModal: template must be an object');
            }
            rows.push(item);
        }
        return rows;
    }

    private _maybeSeedTemplate(): void {
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
            throw new Error('PlatformNamespaceCreateModal: template missing');
        }
        this._form.setField('template_id', first.template_id);
        this._templateSeeded = true;
    }

    private _isDraftDirty(): boolean {
        const draft = this._form.draft;
        if (typeof draft.name === 'string' && draft.name.length > 0) return true;
        if (typeof draft.description === 'string' && draft.description.length > 0) return true;
        return false;
    }

    private _onCreated(item: unknown): void {
        const user = this._authSel.value;
        if (user === null) {
            throw new Error('PlatformNamespaceCreateModal: cannot select created namespace without company_id');
        }
        const companyId = user.company_id;
        if (typeof companyId !== 'string') {
            throw new Error('PlatformNamespaceCreateModal: cannot select created namespace without company_id');
        }
        if (!isPlainRecord(item)) {
            throw new Error('PlatformNamespaceCreateModal: created namespace required');
        }
        const name = item.name;
        if (typeof name !== 'string' || name.length === 0) {
            throw new Error('PlatformNamespaceCreateModal: created namespace name required');
        }
        setPlatformNamespaceSelection(companyId, name);
        this.closeAfterSave();
    }

    private _fieldError(field: string): string {
        const errorKey = this._form.errors[field];
        return errorKey ? this.t(errorKey) : '';
    }

    override async _performSave(): Promise<void> {
        this._form.submit();
    }

    override _saveHeaderTitle(): string {
        return this._form.submitting
            ? this.t('namespace_modal.saving')
            : this.t('namespace_modal.submit');
    }

    override renderHeader(): unknown {
        return this.t('namespace_modal.header');
    }

    override renderSaveHeaderButton(): TemplateResult {
        const draft = this._form.draft;
        const hasName = typeof draft.name === 'string' && draft.name.trim().length > 0;
        const needsTemplate = this._templates !== null;
        const hasTemplate = typeof draft.template_id === 'string' && draft.template_id.length > 0;
        const disabled = this._form.submitting || !hasName || (needsTemplate && !hasTemplate);
        return this._renderHeaderSaveIcon({
            onClick: () => { void this._performSave(); },
            disabled,
            title: this._saveHeaderTitle(),
        });
    }

    private _renderTemplates(): TemplateResult {
        const items = this._templateItems();
        if (this._templates !== null && this._templates.busy && items.length === 0) {
            return html`<platform-empty-state loading></platform-empty-state>`;
        }
        if (items.length === 0) {
            return html`<platform-empty-state icon="layers" title=${this.t('namespace_modal.templates_empty')}></platform-empty-state>`;
        }
        const draft = this._form.draft;
        return html`
            <div class="template-grid">
                ${items.map((template) => html`
                    <button
                        type="button"
                        class="template-card ${draft.template_id === template.template_id ? 'active' : ''}"
                        @click=${() => this._form.setField('template_id', template.template_id)}
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

    private _templateIcon(icon: unknown): string {
        if (typeof icon !== 'string' || icon.trim().length === 0) return 'folder';
        return icon.trim();
    }

    override renderBody(): unknown {
        const draft = this._form.draft;
        return html`
            <form class="form-grid" @submit=${(e: SubmitEvent) => { e.preventDefault(); void this._performSave(); }}>
                ${this._templates === null ? html`` : html`
                    <div class="form-group">
                        <label class="form-label">${this.t('namespace_modal.label_template')}</label>
                        ${this._renderTemplates()}
                        ${this._fieldError('template_id').length > 0
                            ? html`<div class="form-error">${this._fieldError('template_id')}</div>`
                            : html``}
                        <div class="hint">${this.t('namespace_modal.template_hint')}</div>
                    </div>
                `}
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('namespace_modal.label_name')}
                    .hint=${this.t('namespace_modal.name_hint')}
                    .placeholder=${this.t('namespace_modal.name_placeholder')}
                    .value=${draft.name}
                    .error=${this._fieldError('name')}
                    ?disabled=${this._form.submitting}
                    @change=${(e: CustomEvent<{ value?: unknown }>) =>
                        this._form.setField('name', e.detail && typeof e.detail.value === 'string' ? e.detail.value : '')}
                ></platform-field>
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('namespace_modal.label_description')}
                    .placeholder=${this.t('namespace_modal.description_placeholder')}
                    .value=${draft.description}
                    .error=${this._fieldError('description')}
                    ?disabled=${this._form.submitting}
                    @change=${(e: CustomEvent<{ value?: unknown }>) =>
                        this._form.setField('description', e.detail && typeof e.detail.value === 'string' ? e.detail.value : '')}
                ></platform-field>
            </form>
        `;
    }

    override renderFooter(): TemplateResult {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('namespace_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._form.submitting}
                        @click=${() => { void this._performSave(); }}>
                    ${this._saveHeaderTitle()}
                </button>
            </div>
        `;
    }
}
