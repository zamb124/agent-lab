/**
 * CodeNodeEditor - редактор для code типа
 * Inline Python/JavaScript код с функцией execute(args, state)
 */
import { html } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '../editors/code-editor.js';
import '../../modals/code-docs-modal.js';

export class CodeNodeEditor extends BaseNodeEditor {
    constructor() {
        super();
        this._nodeType = 'code';
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
            language: e.detail.language || this.nodeConfig?.language || 'python',
            nodeType: 'code',
            perspective: 'editor',
        });
    }

    renderFields() {
        const config = this.nodeConfig;
        const showNodeIdField = !this.expanded;
        const language = config.language || 'python';
        
        return html`
            ${showNodeIdField ? this.renderNodeIdField() : ''}
                
                <div class="form-group">
                <code-editor
                            .value=${config.code || ''}
                    .language=${language}
                    node-type="code"
                            min-height="250"
                    @change=${this._onCodeChange}
                    @language-change=${this._onLanguageChange}
                    @open-docs=${this._onOpenDocs}
                ></code-editor>
                </div>
                
                ${this.renderMappingSection()}
                
                ${this._renderTestPanel()}
        `;
    }
}

customElements.define('code-node-editor', CodeNodeEditor);
