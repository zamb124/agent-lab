/**
 * CacheResourceEditor - редактор cache ресурса
 */
import { html } from 'lit';
import { BaseResourceEditor } from './base-resource-editor.js';

export class CacheResourceEditor extends BaseResourceEditor {
    getIconName() {
        return 'database';
    }

    getColor() {
        return '#14b8a6';
    }

    getTypeName() {
        return 'Cache Resource';
    }

    renderFields() {
        const namespace = this.resourceConfig?.namespace || '';
        const ttl = this.resourceConfig?.ttl || 3600;

        return html`
            <div class="form-group">
                <label class="form-label">Namespace</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${namespace}
                    @input=${(e) => this._onInputChange('namespace', e.target.value)}
                    placeholder="agent:cache"
                />
                <span class="form-hint">Cache namespace prefix</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">TTL (seconds)</label>
                <input 
                    type="number" 
                    class="form-input"
                    .value=${ttl}
                    min="1"
                    @input=${(e) => this._onInputChange('ttl', parseInt(e.target.value) || 3600)}
                />
                <span class="form-hint">Время жизни записей в секундах</span>
            </div>
        `;
    }
}

customElements.define('cache-resource-editor', CacheResourceEditor);
