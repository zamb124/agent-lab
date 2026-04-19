/**
 * flows-rag-resource-editor — ресурс rag.
 *
 * Поля точно по `RAGResourceConfig` (наследует RagResourceBindParams):
 *   - namespace (str, required)
 *   - provider (str, default 'pgvector')
 *   - default_top_k (int, default 5)
 *   - search_options (dict)
 *   - index_profile_config (dict)
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';
import '../editors/flows-json-field-editor.js';

const PROVIDERS = Object.freeze(['pgvector', 'qdrant', 'pinecone']);

export class FlowsRagResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        css`
            .body { padding: 0 var(--space-3); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-2); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input, select {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); }
            details {
                margin-top: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            summary { cursor: pointer; font-size: var(--text-sm); font-weight: var(--font-semibold); }
        `,
    ];

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
    }

    _emitConfig(patch) {
        const base = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...base, ...patch } } });
    }

    render() {
        const cfg = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        const namespace = typeof cfg.namespace === 'string' ? cfg.namespace : '';
        const provider = PROVIDERS.includes(cfg.provider) ? cfg.provider : 'pgvector';
        const topK = typeof cfg.default_top_k === 'number' ? cfg.default_top_k : 5;
        const searchOpts = cfg.search_options && typeof cfg.search_options === 'object'
            ? JSON.stringify(cfg.search_options, null, 2) : '{}';
        const indexProfile = cfg.index_profile_config && typeof cfg.index_profile_config === 'object'
            ? JSON.stringify(cfg.index_profile_config, null, 2) : '{}';
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'rag'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings" class="body">
                    <div class="field">
                        <label>${this.t('rag_resource_editor.namespace')}</label>
                        <input type="text" .value=${namespace}
                            @input=${(e) => this._emitConfig({ namespace: e.target.value })} />
                    </div>
                    <div class="grid">
                        <div class="field">
                            <label>${this.t('rag_resource_editor.provider')}</label>
                            <select .value=${provider}
                                @change=${(e) => this._emitConfig({ provider: e.target.value })}>
                                ${PROVIDERS.map((p) => html`<option value=${p} ?selected=${p === provider}>${this.t(`rag_resource_editor.provider_${p}`)}</option>`)}
                            </select>
                        </div>
                        <div class="field">
                            <label>${this.t('rag_resource_editor.default_top_k')}</label>
                            <input type="number" min="1" step="1" .value=${String(topK)}
                                @input=${(e) => this._emitConfig({ default_top_k: parseInt(e.target.value, 10) || 5 })} />
                        </div>
                    </div>
                    <details>
                        <summary>${this.t('rag_resource_editor.search_options')}</summary>
                        <flows-json-field-editor
                            .value=${searchOpts}
                            @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._emitConfig({ search_options: e.detail.parsed }); }}
                        ></flows-json-field-editor>
                    </details>
                    <details>
                        <summary>${this.t('rag_resource_editor.index_profile_config')}</summary>
                        <flows-json-field-editor
                            .value=${indexProfile}
                            @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._emitConfig({ index_profile_config: e.detail.parsed }); }}
                        ></flows-json-field-editor>
                    </details>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-rag-resource-editor', FlowsRagResourceEditor);
