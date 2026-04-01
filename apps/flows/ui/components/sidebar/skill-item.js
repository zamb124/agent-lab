/**
 * SkillItem - элемент skill в flow-card
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class SkillItem extends PlatformElement {
    static properties = {
        skill: { type: Object },
        flowId: { type: String, attribute: 'flow-id' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .skill-item {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-medium);
                border-radius: var(--radius-md);
                transition: all var(--duration-fast);
            }

            .skill-item:hover {
                background: var(--glass-solid-strong);
            }

            .skill-info {
                flex: 1;
                min-width: 0;
            }

            .skill-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }

            .skill-description {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: 2px;
                line-height: 1.4;
            }

            .skill-actions {
                display: flex;
                gap: 2px;
                opacity: 0;
                transition: opacity var(--duration-fast);
            }

            .skill-item:hover .skill-actions {
                opacity: 1;
            }

            .action-btn {
                width: 22px;
                height: 22px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-sm);
                color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: none;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .action-btn platform-icon {
                pointer-events: none;
            }

            .action-btn:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
            }

            .action-btn.chat:hover {
                color: var(--accent);
            }

            .action-btn.danger:hover {
                background: var(--error-bg);
                color: var(--error);
            }
        `
    ];

    constructor() {
        super();
        this.skill = null;
        this.flowId = '';
    }

    _emitAction(action, e) {
        e?.stopPropagation();
        this.emit('skill-action', {
            action,
            skillId: this.skill.id,
            flowId: this.flowId,
        });
    }

    render() {
        if (!this.skill) return '';

        return html`
            <div class="skill-item">
                <div class="skill-info">
                    <div class="skill-name">${this.skill.name || this.skill.id}</div>
                    ${this.skill.description ? html`
                        <div class="skill-description">${this.skill.description}</div>
                    ` : ''}
                </div>
                <div class="skill-actions">
                    <button 
                        class="action-btn chat" 
                        @click=${(e) => this._emitAction('chat', e)}
                        title=${this.i18n.t('flow_card.open_chat_title')}
                    >
                        <platform-icon name="chat" size="12"></platform-icon>
                    </button>
                    <button 
                        class="action-btn" 
                        @click=${(e) => this._emitAction('edit', e)}
                        title=${this.i18n.t('flow_card.edit_title')}
                    >
                        <platform-icon name="edit" size="12"></platform-icon>
                    </button>
                    <button 
                        class="action-btn danger" 
                        @click=${(e) => this._emitAction('delete-skill', e)}
                        title=${this.i18n.t('flow_card.delete_title')}
                    >
                        <platform-icon name="trash" size="12"></platform-icon>
                    </button>
                </div>
            </div>
        `;
    }
}

customElements.define('skill-item', SkillItem);
