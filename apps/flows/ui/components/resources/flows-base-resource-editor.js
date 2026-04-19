/**
 * flows-base-resource-editor — общая обёртка для редакторов ресурсов.
 *
 * Поля точно по `ResourceDefinition` (apps/flows/src/models/resource.py):
 *   - resource_id (read-only)
 *   - type (badge)
 *   - name
 *   - description
 *   - tags (через flows-tag-input)
 *
 * Slot 'settings' — type-specific поля (`config: dict`).
 *
 * Эмитит наружу `change { resourceId, patch }` — patch содержит изменённые
 * top-level поля ресурса (name, description, tags) или config (от слота).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '../editors/flows-tag-input.js';

export class FlowsBaseResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
        resourceType: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; padding: var(--space-3); color: var(--text-primary); }
            .header {
                display: flex; flex-direction: column; gap: var(--space-2);
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                margin-bottom: var(--space-3);
            }
            .row {
                display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap;
            }
            input.name {
                flex: 1; min-width: 0;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                font-weight: var(--font-semibold);
            }
            .badge {
                padding: 2px 8px; font-size: var(--text-xs);
                border-radius: var(--radius-full);
                background: var(--accent-subtle); color: var(--accent);
                white-space: nowrap;
            }
            .id {
                padding: 2px 8px; font-size: var(--text-xs);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
                font-family: var(--font-mono, monospace);
            }
            .field { display: flex; flex-direction: column; gap: var(--space-1); }
            .field label { font-size: var(--text-sm); color: var(--text-secondary); }
            textarea {
                width: 100%; box-sizing: border-box;
                padding: var(--space-2); resize: vertical; min-height: 60px;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
        `,
    ];

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
        this.resourceType = '';
    }

    _emitPatch(patch) {
        this.emit('change', { resourceId: this.resourceId, patch });
    }

    _onName(e) {
        this._emitPatch({ name: e.target.value });
    }

    _onDescription(e) {
        this._emitPatch({ description: e.target.value });
    }

    _onTags(e) {
        const tags = Array.isArray(e.detail?.tags) ? e.detail.tags : [];
        this._emitPatch({ tags });
    }

    render() {
        if (!this.resource) return html`<div>${this.t('property_panel.select_resource')}</div>`;
        const name = typeof this.resource.name === 'string' ? this.resource.name : this.resourceId;
        const description = typeof this.resource.description === 'string' ? this.resource.description : '';
        const tags = Array.isArray(this.resource.tags) ? this.resource.tags : [];
        const type = this.resourceType || this.resource.type || '';
        return html`
            <div class="header">
                <div class="row">
                    <input class="name" type="text" .value=${name} @input=${this._onName} />
                    <span class="badge">${type}</span>
                </div>
                <div class="row">
                    <span class="id">${this.resourceId}</span>
                </div>
                <div class="field">
                    <label>${this.t('base_resource_editor.field_description')}</label>
                    <textarea .value=${description} @input=${this._onDescription}></textarea>
                </div>
                <div class="field">
                    <label>${this.t('base_resource_editor.tags')}</label>
                    <flows-tag-input
                        .tags=${tags}
                        placeholder=${this.t('tag_input.placeholder')}
                        @change=${this._onTags}
                    ></flows-tag-input>
                </div>
            </div>
            <slot name="settings"></slot>
        `;
    }
}

customElements.define('flows-base-resource-editor', FlowsBaseResourceEditor);
