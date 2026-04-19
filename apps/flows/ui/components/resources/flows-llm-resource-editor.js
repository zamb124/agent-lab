/**
 * flows-llm-resource-editor — ресурс типа llm.
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';
import '../editors/flows-llm-config-editor.js';

export class FlowsLlmResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
    };

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
    }

    _emitConfig(config) {
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...(this.resource?.config || {}), ...config } } });
    }

    render() {
        const cfg = this.resource?.config || {};
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'llm'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <flows-llm-config-editor
                        .config=${cfg}
                        @change=${(e) => this._emitConfig(e.detail?.config || {})}
                    ></flows-llm-config-editor>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-llm-resource-editor', FlowsLlmResourceEditor);
