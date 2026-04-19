/**
 * flows-resource-property-panel — слот для активного редактора ресурса.
 *
 * Читает selectedResourceId из useOp('flows/editor'). Save → useOp('flows/resource_update').
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '../resources/flows-base-resource-editor.js';
import '../resources/flows-llm-resource-editor.js';
import '../resources/flows-secret-resource-editor.js';
import '../resources/flows-code-resource-editor.js';
import '../resources/flows-http-resource-editor.js';
import '../resources/flows-files-resource-editor.js';
import '../resources/flows-prompt-resource-editor.js';
import '../resources/flows-rag-resource-editor.js';
import '../resources/flows-cache-resource-editor.js';

export class FlowsResourcePropertyPanel extends PlatformElement {
    static properties = {
        flowId: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`:host { display: block; }`,
    ];

    constructor() {
        super();
        this.flowId = '';
        this._editor = this.useOp('flows/editor');
        this._resources = this.useResource('flows/resources');
        this._update = this.useOp('flows/resource_update');
    }

    async _onChange(e) {
        const { resourceId, patch } = e.detail || {};
        if (!resourceId || !patch) return;
        const item = (this._resources.items || []).find((r) => r && r.resource_id === resourceId);
        if (!item) return;
        const body = { ...item, ...patch };
        await this._update.run({ resource_id: resourceId, body });
    }

    _renderEditor(resource) {
        const id = resource.resource_id;
        switch (resource.type) {
            case 'llm':
                return html`<flows-llm-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${this._onChange}></flows-llm-resource-editor>`;
            case 'secret':
                return html`<flows-secret-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${this._onChange}></flows-secret-resource-editor>`;
            case 'code':
                return html`<flows-code-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${this._onChange}></flows-code-resource-editor>`;
            case 'http':
                return html`<flows-http-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${this._onChange}></flows-http-resource-editor>`;
            case 'files':
                return html`<flows-files-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${this._onChange}></flows-files-resource-editor>`;
            case 'prompt':
                return html`<flows-prompt-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${this._onChange}></flows-prompt-resource-editor>`;
            case 'rag':
                return html`<flows-rag-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${this._onChange}></flows-rag-resource-editor>`;
            case 'cache':
                return html`<flows-cache-resource-editor .resourceId=${id} .resource=${resource}
                    @change=${this._onChange}></flows-cache-resource-editor>`;
            default:
                return html`<flows-base-resource-editor .resourceId=${id} .resource=${resource}
                    .resourceType=${resource.type || ''} @change=${this._onChange}></flows-base-resource-editor>`;
        }
    }

    render() {
        const state = this._editor.state || {};
        const resourceId = state.selectedResourceId;
        if (!resourceId) {
            return html`<div style="padding: var(--space-3); color: var(--text-tertiary)">${this.t('property_panel.select_resource')}</div>`;
        }
        const resource = (this._resources.items || []).find((r) => r && r.resource_id === resourceId);
        if (!resource) return html`<div></div>`;
        return this._renderEditor(resource);
    }
}

customElements.define('flows-resource-property-panel', FlowsResourcePropertyPanel);
