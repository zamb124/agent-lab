/**
 * flows-resource-property-panel — слот для активного редактора ресурса.
 *
 * Читает selectedResourceId из useOp('flows/editor'). Save → useOp('flows/resource_update')
 * с debounce 400ms. Кнопка Delete вызывает useResource('flows/resources').remove(id).
 *
 * Роутинг строго по `resource.type` (ResourceType enum):
 *   llm | secret | code | http | files | prompt | rag | cache.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import '../resources/flows-base-resource-editor.js';
import '../resources/flows-llm-resource-editor.js';
import '../resources/flows-secret-resource-editor.js';
import '../resources/flows-code-resource-editor.js';
import '../resources/flows-http-resource-editor.js';
import '../resources/flows-files-resource-editor.js';
import '../resources/flows-prompt-resource-editor.js';
import '../resources/flows-rag-resource-editor.js';
import '../resources/flows-cache-resource-editor.js';
import { asObject, asString, isPlainObject } from '../../_helpers/flows-resolvers.js';

const SAVE_DEBOUNCE_MS = 400;

export class FlowsResourcePropertyPanel extends PlatformElement {
    static properties = {
        flowId: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .toolbar {
                display: flex; justify-content: flex-end; gap: var(--space-1);
                padding: var(--space-2) var(--space-3) 0 var(--space-3);
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this._editor = this.useOp('flows/editor');
        this._resources = this.useResource('flows/resources');
        this._update = this.useOp('flows/resource_update');
        this._pending = new Map();
        this._timers = new Map();
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        for (const timer of this._timers.values()) clearTimeout(timer);
        this._timers.clear();
        this._pending.clear();
    }

    _scheduleSave(resourceId, body) {
        this._pending.set(resourceId, body);
        const existing = this._timers.get(resourceId);
        if (existing) clearTimeout(existing);
        const timer = setTimeout(() => {
            const payload = this._pending.get(resourceId);
            this._pending.delete(resourceId);
            this._timers.delete(resourceId);
            if (!payload) return;
            void this._update.run({ resource_id: resourceId, body: payload });
        }, SAVE_DEBOUNCE_MS);
        this._timers.set(resourceId, timer);
    }

    _onChange(e) {
        const { resourceId, patch } = isPlainObject(e.detail) ? e.detail : {};
        if (!resourceId || !patch || typeof patch !== 'object') return;
        const items = Array.isArray(this._resources.items) ? this._resources.items : [];
        const item = items.find((r) => r && r.resource_id === resourceId);
        if (!item) return;
        const body = { ...item, ...patch };
        this._scheduleSave(resourceId, body);
    }

    async _onDelete(resourceId) {
        if (!resourceId) return;
        await this._resources.remove(resourceId);
        this._editor.selectResource({ resourceId: null });
    }

    _renderEditor(resource) {
        const id = resource.resource_id;
        const onChange = (e) => this._onChange(e);
        switch (resource.type) {
            case 'llm':
                return html`<flows-llm-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${onChange}></flows-llm-resource-editor>`;
            case 'secret':
                return html`<flows-secret-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${onChange}></flows-secret-resource-editor>`;
            case 'code':
                return html`<flows-code-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${onChange}></flows-code-resource-editor>`;
            case 'http':
                return html`<flows-http-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${onChange}></flows-http-resource-editor>`;
            case 'files':
                return html`<flows-files-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${onChange}></flows-files-resource-editor>`;
            case 'prompt':
                return html`<flows-prompt-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${onChange}></flows-prompt-resource-editor>`;
            case 'rag':
                return html`<flows-rag-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${onChange}></flows-rag-resource-editor>`;
            case 'cache':
                return html`<flows-cache-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${onChange}></flows-cache-resource-editor>`;
            default:
                return html`<flows-base-resource-editor .resourceId=${id} .resource=${resource}
                    .resourceType=${asString(resource.type)} @change=${onChange}></flows-base-resource-editor>`;
        }
    }

    render() {
        const state = asObject(this._editor.state);
        const resourceId = state.selectedResourceId;
        if (!resourceId) {
            return html`<div style="padding: var(--space-3); color: var(--text-tertiary)">${this.t('property_panel.select_resource')}</div>`;
        }
        const items = Array.isArray(this._resources.items) ? this._resources.items : [];
        const resource = items.find((r) => r && r.resource_id === resourceId);
        if (!resource) return html`<div></div>`;
        return html`
            <div class="toolbar">
                <glass-button size="sm" variant="ghost" @click=${() => this._onDelete(resourceId)} title=${this.t('property_panel.action_delete_resource')}>
                    <platform-icon name="trash"></platform-icon>
                </glass-button>
            </div>
            ${this._renderEditor(resource)}
        `;
    }
}

customElements.define('flows-resource-property-panel', FlowsResourcePropertyPanel);
