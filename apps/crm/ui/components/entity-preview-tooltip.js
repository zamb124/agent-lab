/**
 * Entity Preview Tooltip - Popup с информацией о сущности при наведении
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import '@platform/lib/components/platform-icon.js';

export class EntityPreviewTooltip extends PlatformElement {
    static properties = {
        entity: { type: Object },
        entityType: { type: Object },
        x: { type: Number },
        y: { type: Number },
        visible: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        glassStyles,
        css`
            :host {
                position: absolute;
                z-index: 9999;
                pointer-events: none;
                opacity: 0;
                transform: translateY(4px);
                transition: opacity var(--duration-fast) ease,
                            transform var(--duration-fast) ease;
            }

            :host([visible]) {
                opacity: 1;
                transform: translateY(0);
                pointer-events: auto;
            }

            .tooltip {
                min-width: 200px;
                max-width: 320px;
                background: var(--crm-surface);
                backdrop-filter: blur(var(--glass-blur-strong));
                border: 1px solid var(--crm-stroke-strong);
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-strong);
                overflow: hidden;
            }

            .header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3);
                border-bottom: 1px solid var(--crm-stroke);
            }

            .type-icon {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: var(--text-xl);
                border-radius: var(--radius-md);
            }

            .header-info {
                flex: 1;
                min-width: 0;
            }

            .entity-name {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .entity-type {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                margin-top: 2px;
            }

            .body {
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .attribute {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                font-size: var(--text-sm);
            }

            .attribute-label {
                color: var(--text-tertiary);
                min-width: 80px;
                flex-shrink: 0;
            }

            .attribute-value {
                color: var(--text-primary);
                word-break: break-word;
            }

            .description {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.4;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }

            .footer {
                padding: var(--space-2) var(--space-3);
                border-top: 1px solid var(--crm-stroke);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            :host-context([data-theme="light"]) .tooltip {
                box-shadow: var(--glass-shadow-medium);
            }
        `
    ];

    constructor() {
        super();
        this.entity = null;
        this.entityType = null;
        this.x = 0;
        this.y = 0;
        this.visible = false;
    }

    updated(changedProps) {
        super.updated(changedProps);
        
        if (changedProps.has('x') || changedProps.has('y') || changedProps.has('visible')) {
            requestAnimationFrame(() => this._updatePosition());
        }
    }

    _updatePosition() {
        if (!this.visible) {
            this.style.left = '-9999px';
            this.style.top = '-9999px';
            return;
        }

        const parent = this.parentElement || this.getRootNode()?.host;
        const parentRect = parent?.getBoundingClientRect();
        const containerWidth = parentRect?.width || window.innerWidth;
        const containerHeight = parentRect?.height || window.innerHeight;
        
        const tooltipWidth = 280;
        const tooltipHeight = 180;
        const padding = 12;

        let left = this.x - tooltipWidth / 2;
        let top = this.y + 8;

        if (left + tooltipWidth + padding > containerWidth) {
            left = containerWidth - tooltipWidth - padding;
        }
        if (left < padding) {
            left = padding;
        }

        if (top + tooltipHeight + padding > containerHeight) {
            top = this.y - tooltipHeight - 8;
        }
        if (top < padding) {
            top = padding;
        }

        this.style.left = `${left}px`;
        this.style.top = `${top}px`;
    }

    _getTypeConfig() {
        if (this.entityType) {
            return {
                icon: this.entityType.icon || 'file',
                color: this.entityType.color || 'var(--text-tertiary)',
                label: this.entityType.name || this.entity?.entity_type || 'Сущность',
            };
        }
        return { icon: 'file', color: 'var(--text-tertiary)', label: this.entity?.entity_type || 'Сущность' };
    }

    _resolveIconName(iconName) {
        if (typeof iconName === 'string' && /^[a-z0-9-]+$/i.test(iconName)) {
            return iconName;
        }
        return 'file';
    }

    _getDisplayAttributes() {
        if (!this.entity?.attributes) return [];

        const attrs = this.entity.attributes;
        const result = [];
        const maxAttrs = 4;

        const priorityKeys = ['email', 'phone', 'company', 'position', 'role', 'address', 'website'];
        
        for (const key of priorityKeys) {
            if (result.length >= maxAttrs) break;
            if (attrs[key]) {
                result.push({ key: this._formatLabel(key), value: attrs[key] });
            }
        }

        for (const [key, value] of Object.entries(attrs)) {
            if (result.length >= maxAttrs) break;
            if (!priorityKeys.includes(key) && value && typeof value !== 'object') {
                result.push({ key: this._formatLabel(key), value: String(value) });
            }
        }

        return result;
    }

    _formatLabel(key) {
        const labels = {
            email: 'Email',
            phone: 'Телефон',
            company: 'Компания',
            position: 'Должность',
            role: 'Роль',
            address: 'Адрес',
            website: 'Сайт',
        };
        return labels[key] || key.charAt(0).toUpperCase() + key.slice(1);
    }

    _formatDate(dateStr) {
        if (!dateStr) return null;
        const date = new Date(dateStr);
        return date.toLocaleDateString('ru-RU', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
        });
    }

    render() {
        if (!this.entity) return html``;

        const typeConfig = this._getTypeConfig();
        const attributes = this._getDisplayAttributes();

        return html`
            <div class="tooltip">
                <div class="header">
                    <div 
                        class="type-icon" 
                        style="background: ${typeConfig.color}20; color: ${typeConfig.color}"
                    >
                        <platform-icon name="${this._resolveIconName(typeConfig.icon)}" size="18"></platform-icon>
                    </div>
                    <div class="header-info">
                        <div class="entity-name">${this.entity.name}</div>
                        <div class="entity-type">${typeConfig.label}</div>
                    </div>
                </div>

                ${this.entity.description || attributes.length > 0 ? html`
                    <div class="body">
                        ${this.entity.description ? html`
                            <div class="description">${this.entity.description}</div>
                        ` : ''}

                        ${attributes.map(attr => html`
                            <div class="attribute">
                                <span class="attribute-label">${attr.key}:</span>
                                <span class="attribute-value">${attr.value}</span>
                            </div>
                        `)}
                    </div>
                ` : ''}

                ${this.entity.created_at ? html`
                    <div class="footer">
                        Создано: ${this._formatDate(this.entity.created_at)}
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('entity-preview-tooltip', EntityPreviewTooltip);
