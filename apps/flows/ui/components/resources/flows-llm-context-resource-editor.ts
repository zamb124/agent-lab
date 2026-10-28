/**
 * flows-llm-context-resource-editor — ресурс типа llm_context.
 */

import type { OpController } from '@platform/lib/base/use-resource.js';
import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/llm/llm-context-editor.js';
import './flows-base-resource-editor.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';
import type {PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsLlmContextResourceEditor extends PlatformElement {
    static override properties: PropertyDeclarations = {
        resourceId: { type: String },
        resource: { type: Object },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
    }
    declare resourceId: string;
    declare resource: Record<string, any> | null;
    declare compactHeader: boolean;
;
    private _llmContextParent: OpController;
    private _parentLoaded: boolean;

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
        this.compactHeader = false;
        this._llmContextParent = this.useOp('flows/llm_context_resolve_parent');
        this._parentLoaded = false;
    }

    override connectedCallback(): void {
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

    _emitConfig(config: any) {
        this.emit('change', { resourceId: this.resourceId, patch: { config } });
    }

    _parentResolved() {
        const result = this._llmContextParent.lastResult;
        if (!isPlainObject(result) || !isPlainObject((result as any).resolved)) {
            return {};
        }
        return (result as any).resolved;
    }

    _parentProfiles() {
        const result = this._llmContextParent.lastResult;
        return Array.isArray((result as Record<string, any>)?.profiles) ? (result as Record<string, any>).profiles : [];
    }

    _parentBudgets() {
        const result = this._llmContextParent.lastResult;
        return Array.isArray((result as Record<string, any>)?.budgets) ? (result as Record<string, any>).budgets : [];
    }

    override render(): TemplateResult {
        const cfg = isPlainObject(this.resource?.config) ? (this.resource as Record<string, any>).config : {};
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'llm_context'}
                .compactHeader=${this.compactHeader}
                @change=${(e: CustomEvent) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <platform-llm-context-editor
                        .config=${cfg}
                        .resolved=${this._parentResolved()}
                        .profiles=${this._parentProfiles()}
                        .budgets=${this._parentBudgets()}
                        @change=${(e: CustomEvent) => this._emitConfig(e.detail.config)}
                    ></platform-llm-context-editor>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-llm-context-resource-editor', FlowsLlmContextResourceEditor);
