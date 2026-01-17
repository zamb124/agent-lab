/**
 * CodeResourceEditor - редактор code ресурса
 */
import { html } from 'lit';
import { BaseResourceEditor } from './base-resource-editor.js';
import '../editors/code-editor.js';
import '../../modals/code-docs-modal.js';

export class CodeResourceEditor extends BaseResourceEditor {
    getIconName() {
        return 'code';
    }

    getColor() {
        return '#8b5cf6';
    }

    getTypeName() {
        return 'Code Resource';
    }

    _onCodeChange(e) {
        this._onInputChange('code', e.detail.value);
        if (e.detail.language) {
            this._onInputChange('language', e.detail.language);
        }
    }

    _onLanguageChange(e) {
        this._onInputChange('language', e.detail.language);
    }

    _onOpenDocs(e) {
        const modal = document.querySelector('code-docs-modal') || document.createElement('code-docs-modal');
        if (!modal.parentElement) {
            document.body.appendChild(modal);
        }
        modal.showModal({
            language: e.detail.language || this.resourceConfig?.language || 'python',
            nodeType: 'code',
            perspective: 'editor',
        });
    }

    renderFields() {
        const language = this.resourceConfig?.language || 'python';
        const code = this.resourceConfig?.code || '';

        return html`
            <div class="form-group">
                <code-editor
                    .value=${code}
                    .language=${language}
                    node-type="code"
                    min-height="300"
                    @change=${this._onCodeChange}
                    @language-change=${this._onLanguageChange}
                    @open-docs=${this._onOpenDocs}
                ></code-editor>
                <span class="form-hint">Inline код с функциями и классами</span>
            </div>
        `;
    }
}

customElements.define('code-resource-editor', CodeResourceEditor);
