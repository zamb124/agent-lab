/**
 * VariablesModal - модалка управления глобальными переменными
 * CRUD операции с переменными компании для @var: ссылок
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/platform-icon.js';

export class VariablesModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            .modal-container {
                width: 700px;
                max-width: 95vw;
            }
            
            .vars-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                max-height: 400px;
                overflow-y: auto;
                padding: var(--space-2);
            }
            
            .var-item {
                display: grid;
                grid-template-columns: 180px 1fr auto;
                gap: var(--space-3);
                align-items: center;
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
            }
            
            .var-item.system {
                opacity: 0.7;
                background: var(--glass-tint-subtle);
            }
            
            .var-key {
                font-family: var(--font-mono);
                font-size: var(--text-sm);
                color: var(--accent);
                word-break: break-all;
            }
            
            .var-value {
                font-size: var(--text-sm);
                color: var(--text-primary);
                word-break: break-all;
            }
            
            .var-value.secret {
                color: var(--text-tertiary);
                font-style: italic;
            }
            
            .var-badges {
                display: flex;
                gap: var(--space-2);
            }
            
            .badge {
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                text-transform: uppercase;
            }
            
            .badge.secret {
                background: var(--warning-bg);
                color: var(--warning);
            }
            
            .badge.system {
                background: var(--info-bg);
                color: var(--info);
            }
            
            .var-actions {
                display: flex;
                gap: var(--space-1);
            }
            
            .action-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                border-radius: var(--radius-sm);
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            
            .action-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            
            .action-btn.delete:hover {
                color: var(--danger);
            }
            
            .empty-state {
                text-align: center;
                padding: var(--space-8);
                color: var(--text-tertiary);
            }
            
            .add-form {
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                margin-bottom: var(--space-4);
                border: 1px solid var(--border-subtle);
            }
            
            .form-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin-bottom: var(--space-3);
            }
            
            .form-row {
                display: grid;
                grid-template-columns: 1fr 2fr;
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }
            
            .form-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-bottom: var(--space-1);
                display: block;
            }
            
            .form-input {
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                box-sizing: border-box;
            }
            
            .form-input:focus {
                outline: none;
                border-color: var(--accent);
            }
            
            .form-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
            
            .checkbox-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .checkbox-row input {
                width: 16px;
                height: 16px;
            }
            
            .checkbox-row label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            
            .form-actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
                margin-top: var(--space-3);
            }
            
            .info-block {
                background: var(--info-bg);
                color: var(--info);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                margin-bottom: var(--space-4);
            }
            
            .info-block code {
                background: rgba(0,0,0,0.1);
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                font-family: var(--font-mono);
            }
            
            .add-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                border-radius: var(--radius-full);
                border: 1px dashed var(--border-medium);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: all var(--duration-fast);
                margin-bottom: var(--space-4);
            }
            
            .add-btn:hover {
                border-color: var(--accent);
                color: var(--accent);
                background: var(--accent-bg);
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        variables: { type: Array },
        loading: { type: Boolean },
        showAddForm: { type: Boolean },
    };

    constructor() {
        super();
        this.title = '';
        this.variables = [];
        this.loading = true;
        this.showAddForm = false;
    }

    async showModal() {
        this.title = this.i18n.t('variables_modal.modal_title');
        super.showModal();
        await this._loadVariables();
    }

    async _loadVariables() {
        this.loading = true;
        try {
            const res = await this.a2a.get('/api/v1/variables/');
            this.variables = res.items;
        } catch (error) {
            this.error(this.i18n.t('variables_modal.err_load', { message: error.message }));
            this.variables = [];
        }
        this.loading = false;
    }

    async _addVariable(e) {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);
        
        const key = formData.get('key').trim();
        const value = formData.get('value').trim();
        const secret = formData.get('secret') === 'on';
        
        if (!key || !value) {
            this.error(this.i18n.t('variables_modal.err_key_value'));
            return;
        }
        
        try {
            await this.a2a.post('/api/v1/variables/', { key, value, secret });
            this.success(this.i18n.t('variables_modal.var_created', { key }));
            this.showAddForm = false;
            form.reset();
            await this._loadVariables();
        } catch (error) {
            this.error(this.i18n.t('mcp_servers.err_with_message', { message: error.message }));
        }
    }

    async _deleteVariable(key) {
        const modal = document.createElement('confirm-modal');
        modal.title = this.i18n.t('variables_modal.delete_title');
        modal.message = this.i18n.t('variables_modal.delete_message', { key });
        modal.confirmText = this.i18n.t('context_menu.delete');
        modal.confirmVariant = 'danger';
        document.body.appendChild(modal);
        
        const confirmed = await modal.confirm();
        modal.remove();
        
        if (!confirmed) return;
        
        try {
            await this.a2a.delete(`/api/v1/variables/${key}`);
            this.success(this.i18n.t('variables_modal.var_deleted'));
            await this._loadVariables();
        } catch (error) {
            this.error(this.i18n.t('mcp_servers.err_with_message', { message: error.message }));
        }
    }

    _toggleAddForm() {
        this.showAddForm = !this.showAddForm;
    }

    renderBody() {
        if (this.loading) {
            return html`
                <div class="empty-state">
                    <div class="loading-spinner"></div>
                    <div>${this.i18n.t('variables_modal.loading')}</div>
                </div>
            `;
        }

        const userVars = this.variables.filter(v => !v.system);
        const systemVars = this.variables.filter(v => v.system);

        return html`
            <div class="info-block">
                ${this.i18n.t('variables_modal.info_block')}
            </div>
            
            ${this.showAddForm ? this._renderAddForm() : html`
                <button class="add-btn" @click=${this._toggleAddForm} title=${this.i18n.t('variables_modal.add_tooltip')}>
                    <platform-icon name="plus" size="16"></platform-icon>
                </button>
            `}
            
            ${userVars.length === 0 && !this.showAddForm ? html`
                <div class="empty-state">
                    <platform-icon name="key" size="48"></platform-icon>
                    <div>${this.i18n.t('variables_modal.empty_user')}</div>
                </div>
            ` : ''}
            
            ${userVars.length > 0 ? html`
                <div class="vars-list">
                    ${userVars.map(v => this._renderVarItem(v))}
                </div>
            ` : ''}
            
            ${systemVars.length > 0 ? html`
                <div style="margin-top: var(--space-4); font-size: var(--text-sm); color: var(--text-tertiary);">
                    ${this.i18n.t('variables_modal.system_vars_label')}
                </div>
                <div class="vars-list" style="margin-top: var(--space-2);">
                    ${systemVars.map(v => this._renderVarItem(v))}
                </div>
            ` : ''}
        `;
    }

    _renderAddForm() {
        return html`
            <form class="add-form" @submit=${this._addVariable}>
                <div class="form-title">${this.i18n.t('variables_modal.form_new')}</div>
                
                <div class="form-row">
                    <div>
                        <label class="form-label">${this.i18n.t('variables_modal.field_key')}</label>
                        <input 
                            type="text" 
                            name="key" 
                            class="form-input" 
                            placeholder="mcp_api_key" 
                            pattern="[a-zA-Z_][a-zA-Z0-9_]*"
                            required 
                        />
                        <div class="form-hint">${this.i18n.t('variables_modal.hint_key')}</div>
                    </div>
                    <div>
                        <label class="form-label">${this.i18n.t('variables_modal.field_value')}</label>
                        <input 
                            type="text" 
                            name="value" 
                            class="form-input" 
                            placeholder="sk-..." 
                            required 
                        />
                    </div>
                </div>
                
                <div class="checkbox-row">
                    <input type="checkbox" name="secret" id="secret-checkbox" />
                    <label for="secret-checkbox">${this.i18n.t('variables_modal.secret_label')}</label>
                </div>
                
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" @click=${this._toggleAddForm}>${this.i18n.t('editor.cancel')}</button>
                    <button type="submit" class="btn btn-primary">${this.i18n.t('variables_modal.add')}</button>
                </div>
            </form>
        `;
    }

    _renderVarItem(variable) {
        return html`
            <div class="var-item ${variable.system ? 'system' : ''}">
                <div class="var-key">@var:${variable.key}</div>
                <div class="var-value ${variable.secret ? 'secret' : ''}">
                    ${variable.value}
                </div>
                <div class="var-badges">
                    ${variable.secret ? html`<span class="badge secret">secret</span>` : ''}
                    ${variable.system ? html`<span class="badge system">system</span>` : ''}
                    ${!variable.system ? html`
                        <button 
                            class="action-btn delete" 
                            title=${this.i18n.t('variables_modal.title_delete')}
                            @click=${() => this._deleteVariable(variable.key)}
                        >
                            <platform-icon name="trash" size="14"></platform-icon>
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }
}

customElements.define('variables-modal', VariablesModal);
