/**
 * RAGResourceEditor - редактор RAG ресурса
 */
import { html } from 'lit';
import { BaseResourceEditor } from './base-resource-editor.js';

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

    renderFields() {
        const namespace = this.resourceConfig?.namespace || '';
        const provider = this.resourceConfig?.provider || 'pgvector';
        const defaultTopK = this.resourceConfig?.default_top_k || 5;

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
        `;
    }
}

customElements.define('rag-resource-editor', RAGResourceEditor);
