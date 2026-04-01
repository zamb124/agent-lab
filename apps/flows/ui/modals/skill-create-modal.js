/**
 * SkillCreateModal - модальное окно создания нового скилла
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

export class SkillCreateModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            .form-group {
                margin-bottom: var(--space-4);
            }
            
            .form-label {
                display: block;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }
            
            .form-input {
                width: 100%;
                padding: var(--space-3);
                font-size: var(--text-sm);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-primary);
                outline: none;
                transition: all var(--duration-fast) var(--easing-default);
                box-sizing: border-box;
            }
            
            .form-input:focus {
                border-color: var(--accent);
                box-shadow: 0 0 0 3px var(--accent-subtle);
            }
            
            .form-input::placeholder {
                color: var(--text-tertiary);
            }
            
            .radio-group {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            
            .radio-option {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-subtle);
                border: 2px solid transparent;
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .radio-option:hover {
                background: var(--glass-solid-medium);
            }
            
            .radio-option.selected {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            
            .radio-input {
                margin-top: 2px;
                accent-color: var(--accent);
            }
            
            .radio-content {
                flex: 1;
            }
            
            .radio-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                margin-bottom: var(--space-1);
            }
            
            .radio-description {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        skillId: { type: String },
        skillName: { type: String },
        initType: { type: String },
        currentSkillId: { type: String },
    };

    constructor() {
        super();
        this.size = 'md';
        this.skillId = '';
        this.skillName = '';
        this.initType = 'empty';
        this.currentSkillId = 'base';
    }

    showModal(currentSkillId = 'base') {
        this.currentSkillId = currentSkillId;
        this.skillId = '';
        this.skillName = '';
        this.initType = 'empty';
        super.showModal();
    }

    _onIdChange(e) {
        this.skillId = e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_');
        if (!this.skillName) {
            this.skillName = this.skillId;
        }
    }

    _onNameChange(e) {
        this.skillName = e.target.value;
    }

    _selectInitType(type) {
        this.initType = type;
    }

    _onCreate() {
        if (!this.skillId.trim()) {
            this.error(this.i18n.t('skill_create.err_id_required'));
            return;
        }

        this.emit('skill-create', {
            skillId: this.skillId.trim(),
            name: this.skillName.trim() || this.skillId.trim(),
            initType: this.initType,
            copyFromSkillId: this.initType === 'copy' ? this.currentSkillId : null,
        });
        
        this.close();
    }

    renderHeader() {
        return this.i18n.t('skill_create.title');
    }

    renderBody() {
        const copyLabel = this.currentSkillId === 'base' 
            ? this.i18n.t('skill_create.copy_base')
            : this.i18n.t('skill_create.copy_named', { id: this.currentSkillId });

        return html`
            <div class="form-group">
                <label class="form-label">${this.i18n.t('skill_create.label_id')}</label>
                <input
                    type="text"
                    class="form-input"
                    .value=${this.skillId}
                    @input=${this._onIdChange}
                    placeholder="my_skill"
                />
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('skill_create.label_name')}</label>
                <input
                    type="text"
                    class="form-input"
                    .value=${this.skillName}
                    @input=${this._onNameChange}
                    placeholder="My Skill"
                />
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('skill_create.label_init')}</label>
                <div class="radio-group">
                    <div 
                        class="radio-option ${this.initType === 'empty' ? 'selected' : ''}"
                        @click=${() => this._selectInitType('empty')}
                    >
                        <input 
                            type="radio" 
                            class="radio-input"
                            name="initType" 
                            value="empty"
                            .checked=${this.initType === 'empty'}
                        />
                        <div class="radio-content">
                            <div class="radio-title">${this.i18n.t('skill_create.empty_title')}</div>
                            <div class="radio-description">
                                ${this.i18n.t('skill_create.empty_desc')}
                            </div>
                        </div>
                    </div>
                    
                    <div 
                        class="radio-option ${this.initType === 'copy' ? 'selected' : ''}"
                        @click=${() => this._selectInitType('copy')}
                    >
                        <input 
                            type="radio" 
                            class="radio-input"
                            name="initType" 
                            value="copy"
                            .checked=${this.initType === 'copy'}
                        />
                        <div class="radio-content">
                            <div class="radio-title">${copyLabel}</div>
                            <div class="radio-description">
                                ${this.i18n.t('skill_create.copy_desc')}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button variant="secondary" @click=${this.close}>
                ${this.i18n.t('editor.cancel')}
            </platform-button>
            <platform-button variant="primary" @click=${this._onCreate}>
                ${this.i18n.t('skill_create.create')}
            </platform-button>
        `;
    }
}

customElements.define('skill-create-modal', SkillCreateModal);

