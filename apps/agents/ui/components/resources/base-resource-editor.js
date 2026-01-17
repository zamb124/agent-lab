/**
 * BaseResourceEditor - базовый класс для редакторов ресурсов
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

export class BaseResourceEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        formStyles,
        buttonStyles,
        css`
            .panel-body {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            
            .resource-header {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
            }
            
            .resource-icon {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            
            .resource-meta {
                flex: 1;
            }
            
            .resource-type {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            
            .resource-name {
                font-size: var(--text-base);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
        `
    ];

    static properties = {
        resourceId: { type: String },
        resourceConfig: { type: Object },
        resourceType: { type: String },
    };

    constructor() {
        super();
        this.resourceId = '';
        this.resourceConfig = {};
        this.resourceType = '';
    }

    _updateConfig(field, value) {
        this.resourceConfig = {
            ...this.resourceConfig,
            [field]: value
        };
        
        this.emit('config-change', { field, value, config: this.resourceConfig });
    }

    _onInputChange(field, value) {
        this._updateConfig(field, value);
    }

    _deleteResource() {
        this.emit('resource-delete', { resourceId: this.resourceId });
    }

    getIconName() {
        return 'box';
    }

    getColor() {
        return '#6b7280';
    }

    getTypeName() {
        return 'Resource';
    }

    renderHeader() {
        const color = this.getColor();
        const bgColor = color + '20';
        
        return html`
            <div class="resource-header">
                <div class="resource-icon" style="background: ${bgColor}; color: ${color};">
                    <platform-icon name="${this.getIconName()}" size="20"></platform-icon>
                </div>
                <div class="resource-meta">
                    <div class="resource-type">${this.getTypeName()}</div>
                    <div class="resource-name">${this.resourceId}</div>
                </div>
            </div>
        `;
    }

    renderFields() {
        return html`<p>Override renderFields() in subclass</p>`;
    }

    render() {
        return html`
            <div class="panel-body">
                ${this.renderFields()}
            </div>
        `;
    }
}

customElements.define('base-resource-editor', BaseResourceEditor);
