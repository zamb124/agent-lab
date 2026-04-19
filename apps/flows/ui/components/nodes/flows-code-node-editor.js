/**
 * flows-code-node-editor — редактор code_node (Python).
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-code-editor.js';

export class FlowsCodeNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
    };

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onConfigChange(field, value) {
        const cfg = { ...(this.nodeConfig?.config || {}), [field]: value };
        this._emitPatch({ config: cfg });
    }

    render() {
        const cfg = this.nodeConfig?.config || {};
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${'code'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <div style="margin-bottom: var(--space-2)">
                        <label>${this.t('code_node_editor.field_code')}</label>
                        <flows-code-editor
                            language="python"
                            .value=${cfg.code || ''}
                            @change=${(e) => this._onConfigChange('code', e.detail?.value || '')}
                        ></flows-code-editor>
                    </div>
                    <div>
                        <label>${this.t('code_node_editor.field_parameters_schema')}</label>
                        <flows-code-editor
                            language="json"
                            .value=${JSON.stringify(cfg.parameters_schema || {}, null, 2)}
                            @change=${(e) => {
                                try {
                                    this._onConfigChange('parameters_schema', JSON.parse(e.detail?.value || '{}'));
                                } catch { /* invalid */ }
                            }}
                        ></flows-code-editor>
                    </div>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-code-node-editor', FlowsCodeNodeEditor);
