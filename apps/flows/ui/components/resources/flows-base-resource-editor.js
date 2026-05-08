/**
 * flows-base-resource-editor — общая обёртка для редакторов ресурсов.
 *
 * Поля точно по `ResourceDefinition` (apps/flows/src/models/resource.py):
 *   - resource_id (read-only)
 *   - type (badge)
 *   - name
 *   - description
 *   - tags (platform-field type=array)
 *
 * Slot 'settings' — type-specific поля (`config: dict`).
 *
 * Эмитит наружу `change { resourceId, patch }` — patch содержит изменённые
 * top-level поля ресурса (name, description, tags) или config (от слота).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';

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
            platform-field.name-field {
                flex: 1;
                min-width: 0;
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
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-base-resource-editor: name change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-base-resource-editor: name detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-base-resource-editor: name detail.value string');
        }
        this._emitPatch({ name: v });
    }

    _onDescription(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-base-resource-editor: description change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-base-resource-editor: description detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-base-resource-editor: description detail.value string');
        }
        this._emitPatch({ description: v });
    }

    _onTags(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-base-resource-editor: tags change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-base-resource-editor: tags detail.value');
        }
        const tags = d.value;
        if (!Array.isArray(tags)) {
            throw new Error('flows-base-resource-editor: tags must be array');
        }
        this._emitPatch({ tags });
    }

    render() {
        if (!this.resource) return html`<div>${this.t('property_panel.select_resource')}</div>`;
        const name = typeof this.resource.name === 'string' ? this.resource.name : this.resourceId;
        const description = typeof this.resource.description === 'string' ? this.resource.description : '';
        const tags = Array.isArray(this.resource.tags) ? this.resource.tags : [];
        let type;
        if (typeof this.resourceType === 'string' && this.resourceType.length > 0) {
            type = this.resourceType;
        } else if (this.resource && typeof this.resource.type === 'string') {
            type = this.resource.type;
        } else {
            type = '';
        }
        return html`
            <div class="header">
                <div class="row">
                    <platform-field
                        class="name-field"
                        mode="edit"
                        type="string"
                        .value=${name}
                        @change=${this._onName}
                    ></platform-field>
                    <span class="badge">${type}</span>
                </div>
                <div class="row">
                    <span class="id">${this.resourceId}</span>
                </div>
                <platform-field
                    mode="edit"
                    type="text"
                    .label=${this.t('base_resource_editor.field_description')}
                    .value=${description}
                    @change=${this._onDescription}
                ></platform-field>
                <platform-field
                    type="array"
                    mode="edit"
                    .label=${this.t('base_resource_editor.tags')}
                    .placeholder=${this.t('tag_input.placeholder')}
                    .value=${tags}
                    .config=${{ preserve_case: true }}
                    @change=${this._onTags}
                ></platform-field>
            </div>
            <slot name="settings"></slot>
        `;
    }
}

customElements.define('flows-base-resource-editor', FlowsBaseResourceEditor);
