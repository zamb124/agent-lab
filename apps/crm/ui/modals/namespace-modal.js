/**
 * Namespace Modal - Создание нового пространства (namespace)
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore } from '../store/crm.store.js';

export class NamespaceModal extends PlatformModal {
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

            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .btn-secondary {
                background: var(--crm-button-secondary-bg);
                border: 1px solid var(--crm-button-secondary-bg);
                color: var(--crm-button-secondary-text);
            }

            .btn-secondary:hover {
                background: var(--crm-button-secondary-hover);
                border-color: var(--crm-button-secondary-hover);
                color: var(--crm-button-secondary-text);
            }

            .btn-primary {
                background: var(--crm-button-primary-bg);
                border: 1px solid var(--crm-button-primary-bg);
                color: var(--crm-button-primary-text);
            }

            .btn-primary:hover:not(:disabled) {
                background: var(--crm-button-primary-hover);
                border-color: var(--crm-button-primary-hover);
            }

            .btn-primary:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
        `
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
        return 'Новое пространство';
    }

    _onNameInput(e) {
        this._name = e.target.value;
    }

    _onDescriptionInput(e) {
        this._description = e.target.value;
    }

    async firstUpdated() {
        super.firstUpdated?.();
        const crmApi = this.services.get('crmApi');
        this._templates = await CRMStore.loadNamespaceTemplates(crmApi);
        if (!this._templates.some((template) => template.template_id === this._templateId) && this._templates.length > 0) {
            this._templateId = this._templates[0].template_id;
        }
    }

    _onTemplateChange(e) {
        this._templateId = e.target.value;
    }

    async _onSave() {
        if (!this._name.trim()) {
            this.error('Название обязательно');
            return;
        }

        this._saving = true;

        const crmApi = this.services.get('crmApi');
        await CRMStore.createNamespace(
            crmApi,
            this._name.trim(),
            this._description.trim() || null,
            this._templateId
        );

        this.success('Пространство создано');
        this._saving = false;
        
        this.dispatchEvent(new CustomEvent('saved', {
            detail: { name: this._name.trim() },
            bubbles: true,
            composed: true,
        }));
        
        this.close();
    }

    renderBody() {
        return html`
            <div class="form-grid">
                <div class="form-group">
                    <label class="form-label">Шаблон *</label>
                    <select
                        class="form-select"
                        .value=${this._templateId}
                        @change=${this._onTemplateChange}
                    >
                        ${this._templates.map((template) => html`
                            <option value=${template.template_id}>${template.name}</option>
                        `)}
                    </select>
                    <div class="hint">
                        Пространство создается с преднастроенными типами сущностей.
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">Название *</label>
                    <input
                        type="text"
                        class="form-input"
                        placeholder="Например: personal, work, project-x"
                        .value=${this._name}
                        @input=${this._onNameInput}
                    />
                    <div class="hint">
                        Уникальный идентификатор пространства. Рекомендуется латиница и snake_case.
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">Описание</label>
                    <textarea
                        class="form-textarea"
                        rows="3"
                        placeholder="Опишите назначение пространства"
                        .value=${this._description}
                        @input=${this._onDescriptionInput}
                    ></textarea>
                </div>
            </div>
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
                    Отмена
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${this._saving || !this._name.trim()}
                    @click=${this._onSave}
                >
                    ${this._saving ? 'Создание...' : 'Создать'}
                </button>
            </div>
        `;
    }
}

customElements.define('namespace-modal', NamespaceModal);
