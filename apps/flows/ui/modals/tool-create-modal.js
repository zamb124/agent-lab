/**
 * ToolCreateModal - модалка выбора создания Tool ноды
 * Показывается при перетаскивании Tool на canvas
 * Позволяет выбрать "Новый tool" или "Существующий tool"
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

export class ToolCreateModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            :host {
                --modal-max-width: 500px;
            }
            
            .options-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-4);
                padding: var(--space-4);
            }
            
            .option-card {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                padding: var(--space-6);
                background: var(--glass-solid-subtle);
                border: 2px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .option-card:hover {
                border-color: var(--accent);
                transform: translateY(-2px);
                box-shadow: var(--glass-shadow-medium);
            }
            
            .option-card:active {
                transform: translateY(0);
            }
            
            .option-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 60px;
                height: 60px;
                border-radius: var(--radius-lg);
                background: var(--glass-tint-medium);
                color: var(--accent);
            }
            
            .option-card.existing .option-icon {
                color: var(--accent-secondary);
            }
            
            .option-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            
            .option-description {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                text-align: center;
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        position: { type: Object },
    };

    constructor() {
        super();
        this.size = 'sm';
        this.position = { x: 0, y: 0 };
    }

    connectedCallback() {
        super.connectedCallback();
        this.title = this.i18n.t('tool_create.title');
    }

    renderHeader() {
        return this.title;
    }

    _onNewTool() {
        this.emit('create-new-tool', { position: this.position });
        this.close();
    }

    _onExistingTool() {
        this.emit('select-existing-tool', { position: this.position });
        this.close();
    }

    renderBody() {
        return html`
            <div class="options-grid">
                <div class="option-card new" @click=${this._onNewTool}>
                    <div class="option-icon">
                        <platform-icon name="plus" size="28"></platform-icon>
                    </div>
                    <span class="option-title">${this.i18n.t('tool_create.option_new_title')}</span>
                    <span class="option-description">${this.i18n.t('tool_create.option_new_desc')}</span>
                </div>
                
                <div class="option-card existing" @click=${this._onExistingTool}>
                    <div class="option-icon">
                        <platform-icon name="folder" size="28"></platform-icon>
                    </div>
                    <span class="option-title">${this.i18n.t('tool_create.option_existing_title')}</span>
                    <span class="option-description">${this.i18n.t('tool_create.option_existing_desc')}</span>
                </div>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <button type="button" class="btn btn-secondary" @click=${this.close}>
                ${this.i18n.t('editor.cancel')}
            </button>
        `;
    }
}

customElements.define('tool-create-modal', ToolCreateModal);
