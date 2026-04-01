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
                <label class="form-label">${this.i18n.t('resource_editor.rag.label_namespace')}</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${namespace}
                    @input=${(e) => this._onInputChange('namespace', e.target.value)}
                    placeholder=${this.i18n.t('resource_editor.rag.placeholder_namespace')}
                />
                <span class="form-hint">${this.i18n.t('resource_editor.rag.hint_namespace')}</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.rag.label_provider')}</label>
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
                <label class="form-label">${this.i18n.t('resource_editor.rag.label_default_top_k')}</label>
                <input 
                    type="number" 
                    class="form-input"
                    .value=${defaultTopK}
                    min="1"
                    max="100"
                    @input=${(e) => this._onInputChange('default_top_k', parseInt(e.target.value) || 5)}
                />
                <span class="form-hint">${this.i18n.t('resource_editor.rag.hint_default_top_k')}</span>
            </div>
        `;
    }
}

customElements.define('rag-resource-editor', RAGResourceEditor);
