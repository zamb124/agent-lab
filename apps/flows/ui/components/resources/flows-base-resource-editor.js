/**
 * flows-base-resource-editor — общая обёртка для редакторов ресурсов.
 *
 * Хранит общие поля (resource_id readonly, name, description, type badge)
 * и slot 'settings' для type-specific полей. Save → emit('change', { patch }).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class FlowsBaseResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
        resourceType: { type: String },
        _name: { state: true },
        _description: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; padding: var(--space-3); color: var(--text-primary); }
            .header {
                display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3);
            }
            .header input {
                flex: 1; padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            .badge {
                padding: 2px 8px; font-size: var(--text-xs);
                border-radius: var(--radius-sm);
                background: var(--accent-subtle); color: var(--accent);
            }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .field textarea {
                padding: var(--space-2); min-height: 64px; resize: vertical;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
        `,
    ];

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
        this.resourceType = '';
        this._name = '';
        this._description = '';
        this._hydrated = false;
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.resource) {
            this._name = this.resource.name || this.resourceId;
            this._description = this.resource.description || '';
            this.resourceType = this.resource.type || this.resourceType;
            this._hydrated = true;
        }
    }

    _emitPatch(patch) {
        this.emit('change', { resourceId: this.resourceId, patch });
    }

    _onName(e) {
        this._name = e.target.value;
        this._emitPatch({ name: this._name });
    }

    _onDescription(e) {
        this._description = e.target.value;
        this._emitPatch({ description: this._description });
    }

    render() {
        if (!this.resource) return html`<div>${this.t('property_panel.select_resource')}</div>`;
        return html`
            <div class="header">
                <input type="text" .value=${this._name} @input=${this._onName} />
                <span class="badge">${this.resourceType}</span>
            </div>
            <div class="field">
                <label>${this.t('base_resource_editor.field_description')}</label>
                <textarea .value=${this._description} @input=${this._onDescription}></textarea>
            </div>
            <slot name="settings"></slot>
        `;
    }
}

customElements.define('flows-base-resource-editor', FlowsBaseResourceEditor);
