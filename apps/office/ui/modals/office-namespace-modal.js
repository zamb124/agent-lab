/**
 * Создание CRM namespace из приложения «Документы» (BFF → CRM).
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/platform-icon.js';

export class OfficeNamespaceModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        _name: { state: true },
        _description: { state: true },
        _templateId: { state: true },
        _templates: { state: true },
        _saving: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .form-grid {
                display: grid;
                gap: var(--space-4);
            }

            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }


            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }

            .template-grid {
                display: grid;
                gap: var(--space-2);
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            }

            .template-card {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-surface-muted);
                padding: var(--space-3);
                cursor: pointer;
                transition: border-color var(--duration-fast), background var(--duration-fast),
                    transform var(--duration-fast);
            }

            .template-card:hover {
                border-color: var(--crm-selected-stroke);
                transform: translateY(-1px);
            }

            .template-card.active {
                border-color: var(--crm-selected-stroke);
                background: var(--crm-selected-bg);
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

            .template-id {
                margin-top: var(--space-2);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-full);
                display: inline-flex;
                padding: 2px var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
                    'Liberation Mono', 'Courier New', monospace;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this._name = '';
        this._description = '';
        this._templateId = 'sales';
        this._templates = [];
        this._saving = false;
    }

    renderHeader() {
        return this.i18n.t('namespace_modal.header', {}, 'crm');
    }

    _onNameInput(e) {
        this._name = e.target.value;
    }

    _onDescriptionInput(e) {
        this._description = e.target.value;
    }

    async firstUpdated() {
        super.firstUpdated?.();
        const officeApi = this.services.get('officeApi');
        if (!officeApi) {
            throw new Error('officeApi service is required');
        }
        const list = await officeApi.listNamespaceTemplates();
        if (!Array.isArray(list)) {
            throw new Error('Namespace templates response must be an array');
        }
        this._templates = list;
        if (!this._templates.some((template) => template.template_id === this._templateId) && this._templates.length > 0) {
            this._templateId = this._templates[0].template_id;
        }
    }

    _resolveTemplateIcon(iconName) {
        const value = typeof iconName === 'string' ? iconName.trim() : '';
        return value || 'folder';
    }

    async _onSave() {
        if (!this._name.trim()) {
            this.error(this.i18n.t('namespace_modal.err_name_required', {}, 'crm'));
            return;
        }

        this._saving = true;
        try {
            const officeApi = this.services.get('officeApi');
            if (!officeApi) {
                throw new Error('officeApi service is required');
            }
            await officeApi.createNamespace({
                name: this._name.trim(),
                description: this._description.trim() || null,
                template_id: this._templateId,
            });

            this.success(this.i18n.t('namespace_modal.success_created', {}, 'crm'));
            this.dispatchEvent(
                new CustomEvent('saved', {
                    detail: { name: this._name.trim() },
                    bubbles: true,
                    composed: true,
                }),
            );
            this.close();
        } catch (error) {
            const message =
                error instanceof Error
                    ? error.message
                    : this.i18n.t('namespace_modal.err_create', {}, 'crm');
            this.error(message);
        } finally {
            this._saving = false;
        }
    }

    renderBody() {
        return html`
            <div class="form-grid">
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('namespace_modal.label_template', {}, 'crm')}</label>
                    <div class="template-grid">
                        ${this._templates.map(
                            (template) => html`
                                <button
                                    type="button"
                                    class="template-card ${this._templateId === template.template_id ? 'active' : ''}"
                                    @click=${() => {
                                        this._templateId = template.template_id;
                                    }}
                                >
                                    <div class="template-title">
                                        <platform-icon
                                            name=${this._resolveTemplateIcon(template.icon)}
                                            size="16"
                                        ></platform-icon>
                                        ${template.name}
                                    </div>
                                    <div class="template-description">
                                        ${template.description ||
                                        this.i18n.t('note_content.no_description', {}, 'crm')}
                                    </div>
                                    <div class="template-id">${template.template_id}</div>
                                </button>
                            `,
                        )}
                    </div>
                    <div class="hint">${this.i18n.t('namespace_modal.template_hint', {}, 'crm')}</div>
                </div>

                <div class="form-group">
                    <label class="form-label">${this.i18n.t('namespace_modal.label_name', {}, 'crm')}</label>
                    <input
                        type="text"
                        class="form-input"
                        placeholder=${this.i18n.t('namespace_modal.name_placeholder', {}, 'crm')}
                        .value=${this._name}
                        @input=${this._onNameInput}
                    />
                    <div class="hint">${this.i18n.t('namespace_modal.name_hint', {}, 'crm')}</div>
                </div>

                <div class="form-group">
                    <label class="form-label">${this.i18n.t('namespace_modal.label_description', {}, 'crm')}</label>
                    <textarea
                        class="form-textarea"
                        rows="3"
                        placeholder=${this.i18n.t('namespace_modal.desc_placeholder', {}, 'crm')}
                        .value=${this._description}
                        @input=${this._onDescriptionInput}
                    ></textarea>
                </div>
            </div>
        `;
    }

    renderSaveHeaderButton() {
        const title = this._saving
            ? this.i18n.t('namespace_modal.creating', {}, 'crm')
            : this.i18n.t('namespace_modal.submit', {}, 'crm');
        return this._renderHeaderSaveIcon({
            onClick: () => this._onSave(),
            disabled: this._saving || !this._name.trim(),
            title,
        });
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.i18n.t('cancel', {}, 'common')}
                </button>
            </div>
        `;
    }
}

customElements.define('office-namespace-modal', OfficeNamespaceModal);
