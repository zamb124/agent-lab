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
        this._llmContextParent = this.useOp('flows/llm_context_resolve_parent');
        this._parentLoaded = false;
    }

    connectedCallback() {
        super.connectedCallback();
        if (!this._parentLoaded) {
            this._parentLoaded = true;
            void this._llmContextParent.run({
                llm_context_resource_key: null,
                flow_resources: {},
                node_resources: {},
            });
        }
    }

    _emitConfig(config) {
        this.emit('change', { resourceId: this.resourceId, patch: { config } });
    }

    _parentResolved() {
        const result = this._llmContextParent.lastResult;
        if (!isPlainObject(result) || !isPlainObject(result.resolved)) {
            return {};
        }
        return result.resolved;
    }

    _parentProfiles() {
        const result = this._llmContextParent.lastResult;
        return Array.isArray(result?.profiles) ? result.profiles : [];
    }

    _parentBudgets() {
        const result = this._llmContextParent.lastResult;
        return Array.isArray(result?.budgets) ? result.budgets : [];
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
                        .resolved=${this._parentResolved()}
                        .profiles=${this._parentProfiles()}
                        .budgets=${this._parentBudgets()}
                        @change=${(e) => this._emitConfig(e.detail.config)}
                    ></platform-llm-context-editor>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-llm-context-resource-editor', FlowsLlmContextResourceEditor);
