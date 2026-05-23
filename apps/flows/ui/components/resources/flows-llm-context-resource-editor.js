/**
 * flows-llm-context-resource-editor — ресурс типа llm_context.
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/llm/llm-context-editor.js';
import './flows-base-resource-editor.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';

export class FlowsLlmContextResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
    };

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
        this.compactHeader = false;
    }

    _emitConfig(config) {
        this.emit('change', { resourceId: this.resourceId, patch: { config } });
    }

    render() {
        const cfg = isPlainObject(this.resource?.config) ? this.resource.config : {};
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'llm_context'}
                .compactHeader=${this.compactHeader}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <platform-llm-context-editor
                        .config=${cfg}
                        @change=${(e) => this._emitConfig(isPlainObject(e.detail?.config) ? e.detail.config : {})}
                    ></platform-llm-context-editor>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-llm-context-resource-editor', FlowsLlmContextResourceEditor);
