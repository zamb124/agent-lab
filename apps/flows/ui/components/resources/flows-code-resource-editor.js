/**
 * flows-code-resource-editor — ресурс code (Python).
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';
import '../editors/flows-code-editor.js';

export class FlowsCodeResourceEditor extends PlatformElement {
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
                .resourceType=${'code'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <div style="padding:0 var(--space-3)">
                        <label style="font-size:var(--text-sm);color:var(--text-secondary)">${this.t('code_resource_editor.field_code')}</label>
                        <flows-code-editor
                            language="python"
                            .value=${cfg.code || ''}
                            @change=${(e) => this._emitConfig({ code: e.detail?.value || '' })}
                        ></flows-code-editor>
                    </div>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-code-resource-editor', FlowsCodeResourceEditor);
