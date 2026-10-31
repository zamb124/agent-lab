/**
 * flows-llm-resource-editor — ресурс типа llm.
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';
import '../editors/flows-llm-config-editor.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';
import type {PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsLlmResourceEditor extends PlatformElement {
    static override properties: PropertyDeclarations = {
        resourceId: { type: String },
        resource: { type: Object },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
    }
    declare resourceId: string;
    declare resource: Record<string, unknown> | null;
    declare compactHeader: boolean;
;

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
    }

    _emitConfig(config: any) {
        const resource = this.resource;
        const stored = resource === null ? undefined : resource.config;
        const prevCfg = isPlainObject(stored) ? stored : {};
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...prevCfg, ...config } } });
    }

    override render(): TemplateResult {
        const cfg = isPlainObject(this.resource?.config) ? this.resource.config! : {};
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'llm'}
                .compactHeader=${this.compactHeader}
                @change=${(e: CustomEvent) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <flows-llm-config-editor
                        .config=${cfg}
                        @change=${(e: CustomEvent) => this._emitConfig(isPlainObject(e.detail?.config) ? e.detail.config : {})}
                    ></flows-llm-config-editor>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-llm-resource-editor', FlowsLlmResourceEditor);
