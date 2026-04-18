import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/platform-icon.js';

export class NoteDeleteModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            :host .fullscreen-btn {
                display: none !important;
            }

            .confirm-header-leading {
                display: flex;
                align-items: center;
                gap: var(--space-3, 12px);
                flex: 1;
                min-width: 0;
            }

            .modal-icon {
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg, 12px);
                background: var(--glass-tint-medium, rgba(255, 255, 255, 0.08));
                color: var(--error, #f43f5e);
            }

            .confirm-title-block {
                flex: 1;
                min-width: 0;
            }

            .confirm-title-block .modal-title {
                white-space: normal;
                overflow: visible;
                text-overflow: unset;
                font-size: var(--text-lg, 18px);
                line-height: 1.3;
            }

            .modal-subtitle {
                margin-top: var(--space-1, 4px);
                font-size: var(--text-sm, 14px);
                color: var(--text-tertiary, rgba(255, 255, 255, 0.45));
                line-height: 1.4;
            }

            .modal-message {
                font-size: var(--text-base, 16px);
                color: var(--text-secondary, rgba(255, 255, 255, 0.65));
                line-height: 1.5;
                margin-bottom: var(--space-4, 16px);
            }

            .related-entities-section {
                margin-bottom: var(--space-4, 16px);
            }

            .related-entities-title {
                font-size: var(--text-sm, 14px);
                font-weight: 500;
                color: var(--text-secondary, rgba(255, 255, 255, 0.65));
                margin-bottom: var(--space-3, 12px);
            }

            .related-entities-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: var(--space-3, 12px);
                max-height: 300px;
                overflow-y: auto;
            }

            .entity-card {
                display: flex;
                align-items: center;
                gap: var(--space-3, 12px);
                padding: var(--space-3, 12px);
                background: var(--glass-tint-subtle, rgba(15, 23, 42, 0.02));
                border: 1px solid var(--border-subtle, rgba(15, 23, 42, 0.06));
                border-radius: var(--radius-lg, 12px);
            }

            .entity-icon {
                flex-shrink: 0;
                width: 36px;
                height: 36px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md, 12px);
                background: var(--glass-tint-medium, rgba(255, 255, 255, 0.08));
                color: var(--accent);
            }

            .entity-info {
                flex: 1;
                min-width: 0;
            }

            .entity-name {
                font-size: var(--text-sm, 14px);
                font-weight: 500;
                color: var(--text-primary, rgba(15, 23, 42, 0.95));
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .entity-type {
                font-size: var(--text-xs, 12px);
                color: var(--text-tertiary, rgba(15, 23, 42, 0.45));
            }

            .no-related-entities {
                font-size: var(--text-sm, 14px);
                color: var(--text-tertiary, rgba(15, 23, 42, 0.45));
                font-style: italic;
            }

            .confirm-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3, 12px);
                justify-content: flex-end;
                width: 100%;
            }

            .modal-actions .confirm-actions {
                margin: 0;
            }
        `,
    ];

    static properties = {
        ...PlatformModal.properties,
        title: { type: String },
        subtitle: { type: String },
        message: { type: String },
        confirmText: { type: String },
        cancelText: { type: String },
        relatedEntities: { type: Array },
        entityTypes: { type: Array },
    };

    constructor() {
        super();
        this.size = 'md';
        this.title = 'Удалить заметку';
        this.subtitle = '';
        this.message = 'Вы уверены, что хотите удалить эту заметку?';
        this.confirmText = 'Удалить';
        this.cancelText = 'Отмена';
        this.relatedEntities = [];
        /** @type {((v: boolean | undefined) => void) | null} */
        this._resolvePromise = null;
    }

    async confirm(options = {}) {
        Object.assign(this, options);
        this.showModal();
        return new Promise((resolve) => {
            this._resolvePromise = resolve;
        });
    }

    _settle(value) {
        if (!this._resolvePromise) {
            return;
        }
        const fn = this._resolvePromise;
        this._resolvePromise = null;
        fn(value);
    }

    close() {
        if (this.open && this._resolvePromise) {
            this.emit('cancel');
            this._settle(false);
        }
        super.close();
    }

    _onConfirm() {
        if (!this._resolvePromise) {
            super.close();
            return;
        }
        this.emit('confirm');
        this._settle(true);
        super.close();
    }

    _onCancel() {
        if (!this._resolvePromise) {
            super.close();
            return;
        }
        this.emit('cancel');
        this._settle(false);
        super.close();
    }

    _getEntityTypeConfig(entity) {
        const typeId = entity?.entity_subtype || entity?.entity_type;
        const entityType = Array.isArray(this.entityTypes) ? this.entityTypes.find(t => t.type_id === typeId) : null;
        if (entityType) {
            return {
                icon: this._resolveIconName(entityType.icon),
                color: entityType.color || 'var(--text-tertiary)',
                label: entityType.name || typeId,
            };
        }
        return { icon: 'folder', color: 'var(--text-tertiary)', label: entity?.entity_type || '' };
    }

    _resolveIconName(iconName) {
        if (iconName === 'file') {
            return 'folder';
        }
        if (typeof iconName === 'string' && /^[a-z0-9-]+$/i.test(iconName)) {
            return iconName;
        }
        return 'folder';
    }

    _hexToRgba(hex, alpha) {
        if (!hex || hex.startsWith('var(')) {
            return `rgba(148, 163, 184, ${alpha})`;
        }
        const clean = hex.replace('#', '');
        const r = parseInt(clean.substring(0, 2), 16);
        const g = parseInt(clean.substring(2, 4), 16);
        const b = parseInt(clean.substring(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    render() {
        const modalClasses = [
            'modal',
            this.size,
            this._isFullscreen ? 'fullscreen' : '',
            this._isDragging ? 'dragging' : '',
            this.open && this._panelEnterActive ? 'panel-enter-active' : '',
        ]
            .filter(Boolean)
            .join(' ');

        const hasRelatedEntities = Array.isArray(this.relatedEntities) && this.relatedEntities.length > 0;

        return html`
            <div class="modal-svg-hidden" aria-hidden="true">
                <svg width="0" height="0">
                    <defs>
                        <filter id="liquidGlassFilter" x="-10%" y="-10%" width="120%" height="120%">
                            <feTurbulence
                                type="fractalNoise"
                                baseFrequency="0.012 0.012"
                                numOctaves="3"
                                seed="15"
                                result="noise"
                            />
                            <feDisplacementMap
                                in="SourceGraphic"
                                in2="noise"
                                scale="6"
                                xChannelSelector="R"
                                yChannelSelector="G"
                            />
                        </filter>
                    </defs>
                </svg>
            </div>

            <div class="modal-overlay" @click=${this._handleOverlayClick}>
                <div class="modal-scrim" aria-hidden="true" @click=${() => this.close()}></div>
                <div
                    class="${modalClasses}"
                    style="${this._getModalStyle()}"
                    @animationend=${this._handlePanelEnterAnimationEnd}
                    @click=${(e) => e.stopPropagation()}
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="note-delete-modal-title"
                >
                    <div class="modal-header confirm-modal-header" @mousedown=${this._handleMouseDown}>
                        <div class="confirm-header-leading">
                            <div class="modal-icon">
                                <platform-icon name="notification-error" size="24"></platform-icon>
                            </div>
                            <div class="confirm-title-block">
                                <h2 class="modal-title confirm-title" id="note-delete-modal-title">${this.title}</h2>
                                ${this.subtitle
                                    ? html`<div class="modal-subtitle">${this.subtitle}</div>`
                                    : ''}
                            </div>
                        </div>
                        <div class="header-buttons">
                            <button class="header-btn" @click=${() => this.close()} title="Закрыть" type="button">
                                <platform-icon name="close" size="16"></platform-icon>
                            </button>
                        </div>
                    </div>

                    <div class="modal-content">
                        <div class="modal-message">${this.message}</div>

                        ${hasRelatedEntities ? html`
                            <div class="related-entities-section">
                                <div class="related-entities-title">Связанные сущности, которые будут удалены:</div>
                                <div class="related-entities-grid">
                                    ${this.relatedEntities.map((entity) => {
                                        const typeConfig = this._getEntityTypeConfig(entity);
                                        const bgColor = this._hexToRgba(typeConfig.color, 0.15);
                                        return html`
                                            <div class="entity-card">
                                                <div class="entity-icon" style="background: ${bgColor}; color: ${typeConfig.color};">
                                                    <platform-icon name="${typeConfig.icon}" size="18"></platform-icon>
                                                </div>
                                                <div class="entity-info">
                                                    <div class="entity-name" title="${entity.name || entity.entity_id}">${entity.name || entity.entity_id}</div>
                                                    <div class="entity-type">${typeConfig.label}</div>
                                                </div>
                                            </div>
                                        `;
                                    })}
                                </div>
                            </div>
                        ` : html`
                            <div class="related-entities-section">
                                <div class="no-related-entities">Нет связанных сущностей</div>
                            </div>
                        `}
                    </div>

                    <div class="modal-actions">
                        <div class="confirm-actions">
                            <button
                                type="button"
                                class="btn btn-secondary"
                                @click=${this._onCancel}
                            >
                                ${this.cancelText}
                            </button>
                            <button type="button" class="btn btn-danger" @click=${this._onConfirm}>
                                ${this.confirmText}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('note-delete-modal', NoteDeleteModal);

function getOrCreateNoteDeleteModal() {
    let el = document.querySelector('note-delete-modal');
    if (!el) {
        el = document.createElement('note-delete-modal');
        document.body.appendChild(el);
    }
    return el;
}

export async function showNoteDeleteModal(options = {}) {
    const modal = getOrCreateNoteDeleteModal();
    return modal.confirm(options);
}
