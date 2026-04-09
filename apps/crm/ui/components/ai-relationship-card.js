/**
 * Карточка предложенной связи (AI).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import '@platform/lib/components/platform-icon.js';

export class AIRelationshipCard extends PlatformElement {
    static properties = {
        suggestion: { type: Object },
        index: { type: Number },
        relationshipTypes: { type: Array },
        draftNote: { type: Object },
        draftEntities: { type: Array },
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
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
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
                border: 1px solid var(--crm-selected-stroke);
                border-radius: var(--radius-sm);
                color: var(--accent);
                cursor: pointer;
                transition: all var(--duration-fast) ease;
                font-size: var(--text-xs);
            }

            .confirm-btn:hover {
                background: var(--accent);
                color: var(--platform-btn-primary-text);
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
                background: var(--crm-surface-muted);
                border-color: var(--crm-stroke);
            }

            :host-context([data-theme="light"]) .entity-box {
                background: var(--crm-surface-tint);
            }
        `
    ];

    constructor() {
        super();
        this.suggestion = {};
        this.index = 0;
        this.relationshipTypes = [];
        this.draftNote = null;
        this.draftEntities = [];
    }

    _resolveDraftEndpoint(draftEntityId) {
        if (typeof draftEntityId !== 'string' || draftEntityId.trim().length === 0) {
            throw new Error('draftEntityId is required');
        }
        const note = this.draftNote;
        if (note && note.draft_entity_id === draftEntityId) {
            return {
                name:
                    typeof note.name === 'string' && note.name.trim().length > 0
                        ? note.name
                        : this.i18n.t('ai_relationship.note_default_name'),
                typeLabel: typeof note.entity_type === 'string' ? note.entity_type : 'note',
            };
        }
        const rows = Array.isArray(this.draftEntities) ? this.draftEntities : [];
        const row = rows.find((e) => e && e.draft_entity_id === draftEntityId);
        if (!row) {
            throw new Error(`Draft entity not found: draft_entity_id=${draftEntityId}`);
        }
        const name = typeof row.name === 'string' && row.name.trim().length > 0 ? row.name : '?';
        const typeLabel = typeof row.entity_type === 'string' ? row.entity_type : '';
        return { name, typeLabel };
    }

    _getTypeConfig() {
        const typeId = this.suggestion.relationship_type;
        const types = Array.isArray(this.relationshipTypes) ? this.relationshipTypes : [];
        const relType = types.find(t => t.type_id === typeId);
        
        if (relType) {
            return {
                icon: relType.icon || 'link',
                color: relType.color || 'var(--text-tertiary)',
                label: relType.name
            };
        }
        
        return {
            icon: 'link',
            color: 'var(--text-tertiary)',
            label: typeId || this.i18n.t('ai_relationship.relationship_fallback'),
        };
    }

    _resolveIconName(iconName) {
        if (typeof iconName === 'string' && /^[a-z0-9-]+$/i.test(iconName)) {
            return iconName;
        }
        return 'link';
    }

    _onConfirm() {
        this.emit('confirm', { index: this.index });
    }

    render() {
        const config = this._getTypeConfig();
        const src = this._resolveDraftEndpoint(this.suggestion.source_draft_entity_id);
        const tgt = this._resolveDraftEndpoint(this.suggestion.target_draft_entity_id);
        const source = src.name;
        const target = tgt.name;
        const sourceType = src.typeLabel;
        const targetType = tgt.typeLabel;

        return html`
            <div class="card">
                <div class="card-header">
                    <span class="type-icon">
                        <platform-icon name="${this._resolveIconName(config.icon)}" size="16"></platform-icon>
                    </span>
                    <span class="type-label">${config.label}</span>
                    <button
                        class="confirm-btn"
                        @click=${this._onConfirm}
                        title=${this.i18n.t('confirm', {}, 'common')}
                    >
                        <platform-icon name="check" size="12"></platform-icon>
                    </button>
                </div>

                <div class="relationship-flow">
                    <div class="entity-box">
                        <div class="entity-name">${source}</div>
                        ${sourceType ? html`<div class="entity-type">${sourceType}</div>` : ''}
                    </div>
                    <span class="arrow"><platform-icon name="arrow-right" size="14"></platform-icon></span>
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
