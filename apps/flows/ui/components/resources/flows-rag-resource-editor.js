/**
 * flows-rag-resource-editor — ресурс rag (RAG namespace).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';

export class FlowsRagResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
    };

    static styles = [
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); padding: 0 var(--space-3); }
            .field input {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
        `,
    ];

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
                .resourceType=${'rag'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <div class="field">
                        <label>${this.t('rag_resource_editor.field_namespace')}</label>
                        <input
                            type="text"
                            .value=${cfg.namespace || ''}
                            @input=${(e) => this._emitConfig({ namespace: e.target.value })}
                        />
                    </div>
                    <div class="field">
                        <label>${this.t('rag_resource_editor.field_top_k')}</label>
                        <input
                            type="number" min="1" step="1"
                            .value=${String(cfg.top_k || 5)}
                            @input=${(e) => this._emitConfig({ top_k: parseInt(e.target.value || '5', 10) })}
                        />
                    </div>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-rag-resource-editor', FlowsRagResourceEditor);
