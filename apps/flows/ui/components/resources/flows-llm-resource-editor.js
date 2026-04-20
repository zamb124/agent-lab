/**
 * flows-llm-resource-editor — ресурс типа llm.
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';
import '../editors/flows-llm-config-editor.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';

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
        const prevCfg = isPlainObject(this.resource?.config) ? this.resource.config : {};
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...prevCfg, ...config } } });
    }

    render() {
        const cfg = isPlainObject(this.resource?.config) ? this.resource.config : {};
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
                        @change=${(e) => this._emitConfig(isPlainObject(e.detail?.config) ? e.detail.config : {})}
                    ></flows-llm-config-editor>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-llm-resource-editor', FlowsLlmResourceEditor);
