/**
 * AI Relationship Card - Карточка предложенной связи
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';

export class AIRelationshipCard extends PlatformElement {
    static properties = {
        suggestion: { type: Object },
        index: { type: Number },
        relationshipTypes: { type: Array },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        glassStyles,
        css`
            :host {
                display: block;
            }

            .card {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-3);
                transition: all var(--duration-fast) ease;
            }

            .card:hover {
                border-color: var(--glass-border-medium);
            }

            .card-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .type-icon {
                font-size: var(--text-base);
                line-height: 1;
            }

            .type-label {
                flex: 1;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            .confirm-btn {
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--accent-subtle);
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: var(--radius-sm);
                color: var(--accent);
                cursor: pointer;
                transition: all var(--duration-fast) ease;
                font-size: var(--text-xs);
            }

            .confirm-btn:hover {
                background: var(--accent);
                color: white;
            }

            .relationship-flow {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-sm);
            }

            .entity-box {
                flex: 1;
                padding: var(--space-2);
                background: var(--glass-tint-medium);
                border-radius: var(--radius-sm);
                text-align: center;
                overflow: hidden;
            }

            .entity-name {
                color: var(--text-primary);
                font-weight: var(--font-medium);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .entity-type {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: 2px;
            }

            .arrow {
                color: var(--text-tertiary);
                font-size: var(--text-lg);
                flex-shrink: 0;
            }

            :host-context([data-theme="light"]) .card {
                background: rgba(255, 255, 255, 0.8);
                border-color: rgba(15, 23, 42, 0.1);
            }

            :host-context([data-theme="light"]) .entity-box {
                background: rgba(255, 255, 255, 0.6);
            }
        `
    ];

    constructor() {
        super();
        this.suggestion = {};
        this.index = 0;
        this.relationshipTypes = [];
    }

    _getTypeConfig() {
        const typeId = this.suggestion.relationship_type;
        const types = Array.isArray(this.relationshipTypes) ? this.relationshipTypes : [];
        const relType = types.find(t => t.type_id === typeId);
        
        if (relType) {
            return {
                icon: relType.icon || '🔗',
                color: relType.color || '#9E9E9E',
                label: relType.name
            };
        }
        
        return { icon: '🔗', color: '#9E9E9E', label: typeId || 'Связь' };
    }

    _onConfirm() {
        this.emit('confirm', { index: this.index });
    }

    render() {
        const config = this._getTypeConfig();
        const source = this.suggestion.source_name || this.suggestion.source_entity_id || '?';
        const target = this.suggestion.target_name || this.suggestion.target_entity_id || '?';
        const sourceType = this.suggestion.source_type || '';
        const targetType = this.suggestion.target_type || '';

        return html`
            <div class="card">
                <div class="card-header">
                    <span class="type-icon">${config.icon}</span>
                    <span class="type-label">${config.label}</span>
                    <button class="confirm-btn" @click=${this._onConfirm} title="Подтвердить">
                        ✓
                    </button>
                </div>

                <div class="relationship-flow">
                    <div class="entity-box">
                        <div class="entity-name">${source}</div>
                        ${sourceType ? html`<div class="entity-type">${sourceType}</div>` : ''}
                    </div>
                    <span class="arrow">→</span>
                    <div class="entity-box">
                        <div class="entity-name">${target}</div>
                        ${targetType ? html`<div class="entity-type">${targetType}</div>` : ''}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('ai-relationship-card', AIRelationshipCard);
