/**
 * RAGResourceEditor - редактор RAG ресурса
 */
import { html } from 'lit';
import { BaseResourceEditor } from './base-resource-editor.js';

const RAG_SPLIT_STRATEGIES = [
    { value: 'fixed_tokens', label: 'Fixed tokens' },
    { value: 'semantic', label: 'Semantic' },
    { value: 'structure', label: 'Structure' },
    { value: 'token', label: 'Token' },
    { value: 'sentence', label: 'Sentence' },
    { value: 'code', label: 'Code' },
    { value: 'table', label: 'Table' },
    { value: 'fast', label: 'Fast' },
];

export class RAGResourceEditor extends BaseResourceEditor {
    getIconName() {
        return 'search';
    }

    getColor() {
        return '#3b82f6';
    }

    getTypeName() {
        return 'RAG Resource';
    }

    _onSplitStrategyChange(e) {
        const strategy = e.target.value;
        const prev = this.resourceConfig?.index_profile_config || {};
        const merged = {
            ...prev,
            split: {
                ...(prev.split || {}),
                strategy,
            },
        };
        this._onInputChange('index_profile_config', merged);
    }

    _onSearchOptionsBlur(e) {
        const raw = e.target.value.trim();
        if (!raw) {
            this._onInputChange('search_options', null);
            return;
        }
        try {
            const parsed = JSON.parse(raw);
            if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
                this._onInputChange('search_options', parsed);
            }
        } catch (_) {
            /* невалидный JSON — не перезаписываем конфиг */
        }
    }

    renderFields() {
        const namespace = this.resourceConfig?.namespace || '';
        const provider = this.resourceConfig?.provider || 'pgvector';
        const defaultTopK = this.resourceConfig?.default_top_k || 5;
        const splitStrategy =
            this.resourceConfig?.index_profile_config?.split?.strategy ?? 'fixed_tokens';
        const searchOptionsJson = this.resourceConfig?.search_options
            ? JSON.stringify(this.resourceConfig.search_options, null, 2)
            : '';

        return html`
            <div class="form-group">
                <label class="form-label">Namespace</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${namespace}
                    @input=${(e) => this._onInputChange('namespace', e.target.value)}
                    placeholder="company:docs"
                />
                <span class="form-hint">ID или scope namespace для RAG</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">Provider</label>
                <select 
                    class="form-select"
                    .value=${provider}
                    @change=${(e) => this._onInputChange('provider', e.target.value)}
                >
                    <option value="pgvector">pgvector</option>
                    <option value="qdrant">Qdrant</option>
                    <option value="pinecone">Pinecone</option>
                </select>
            </div>
            
            <div class="form-group">
                <label class="form-label">Default Top K</label>
                <input 
                    type="number" 
                    class="form-input"
                    .value=${defaultTopK}
                    min="1"
                    max="100"
                    @input=${(e) => this._onInputChange('default_top_k', parseInt(e.target.value) || 5)}
                />
                <span class="form-hint">Количество результатов по умолчанию</span>
            </div>

            <div class="form-group">
                <label class="form-label">Search options (JSON)</label>
                <textarea
                    class="form-input"
                    rows="6"
                    style="font-family: monospace; font-size: var(--text-sm);"
                    .value=${searchOptionsJson}
                    @blur=${this._onSearchOptionsBlur}
                    placeholder=${'{\n  "channels": { "semantic": true, "lexical": true },\n  "rerank": true\n}'}
                ></textarea>
                <span class="form-hint"
                    >Параметры поиска для tool search (channels, rrf_k, rerank и т.д.)</span
                >
            </div>

            <div class="form-group">
                <label class="form-label">Split strategy (add_document)</label>
                <select
                    class="form-select"
                    .value=${splitStrategy}
                    @change=${this._onSplitStrategyChange}
                >
                    ${RAG_SPLIT_STRATEGIES.map(
                        (o) => html`<option value=${o.value}>${o.label}</option>`,
                    )}
                </select>
                <span class="form-hint">Частичный index_profile_config для индексации текста из flow</span>
            </div>
        `;
    }
}

customElements.define('rag-resource-editor', RAGResourceEditor);
