/**
 * CodeNodeEditor - редактор для code типа
 * Inline Python/JavaScript код с функцией execute(args, state)
 */
import { html, css } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';
import '../editors/code-editor.js';
import '../editors/json-field-editor.js';
import '../../modals/code-docs-modal.js';

const DEFAULT_PARAMETERS_SCHEMA = () =>
    JSON.stringify({ type: 'object', properties: {}, required: [] }, null, 2);

export class CodeNodeEditor extends BaseNodeEditor {
    static styles = [BaseNodeEditor.styles];

    static properties = {
        ...BaseNodeEditor.properties,
        _codeMainPane: { type: String, state: true },
    };

    constructor() {
        super();
        this._nodeType = 'code';
        this._codeMainPane = 'code';
    }

    _onCodeChange(e) {
        // Слот schema-body — лёгкие потомки code-editor; их change всплывает сюда и не должен писать в code.
        if (e.target !== e.currentTarget) {
            return;
        }
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

    _onParametersSchemaEditorChange(e) {
        const target = e.target;
        if (!target.isValid()) {
            return;
        }
        this._onInputChange('parameters_schema', target.getParsedValue());
    }

    _setCodeMainPane(pane) {
        this._codeMainPane = pane;
    }

    _onCodeSchemaPaneChange(e) {
        const pane = e.detail?.pane;
        if (pane === 'code' || pane === 'schema') {
            this._setCodeMainPane(pane);
        }
    }

    /**
     * Подтягивает актуальный текст из CodeMirror в nodeConfig перед сохранением модалки/формы,
     * иначе последние правки схемы могут не попасть в config-change.
     */
    flushEmbeddedJsonEditors() {
        const root = this.shadowRoot;
        if (!root) {
            return;
        }
        const psEd = root.getElementById('code-parameters-schema-editor');
        if (psEd && typeof psEd.isValid === 'function' && psEd.isValid()) {
            this._onInputChange('parameters_schema', psEd.getParsedValue());
        }
    }

    _parametersSchemaEditorValue() {
        const ps = this.nodeConfig.parameters_schema;
        if (ps && typeof ps === 'object') {
            return JSON.stringify(ps, null, 2);
        }
        return DEFAULT_PARAMETERS_SCHEMA();
    }

    _renderCodeSchemaShell(language) {
        const config = this.nodeConfig;
        return html`
            <code-editor
                code-schema-mode
                ?parent-layout-wide=${this.expanded}
                .activeSchemaPane=${this._codeMainPane}
                @code-schema-pane-change=${this._onCodeSchemaPaneChange}
                .value=${config.code || ''}
                .language=${language}
                node-type="code"
                min-height="250"
                ?accept-node-file-drop=${language === 'python'}
                @change=${this._onCodeChange}
                @language-change=${this._onLanguageChange}
                @open-docs=${this._onOpenDocs}
            >
                <div slot="schema-body">
                    <json-field-editor
                        id="code-parameters-schema-editor"
                        bounded
                        .value=${this._parametersSchemaEditorValue()}
                        min-height="250"
                        hint=${this.i18n.t('code_node_editor.parameters_schema_hint')}
                        @change=${this._onParametersSchemaEditorChange}
                    ></json-field-editor>
                </div>
            </code-editor>
        `;
    }

    renderFields() {
        const config = this.nodeConfig;
        const showNodeIdField = !this.expanded;
        const language = config.language || 'python';

        return html`
            ${showNodeIdField ? this.renderNodeIdField() : ''}
            <div class="form-group">
                ${language === 'python'
                    ? html`<span class="form-label-hint">${this.i18n.t(
                          'code_editor.node_file_drop_hint',
                      )}</span>`
                    : ''}
                ${this._renderCodeSchemaShell(language)}
            </div>
            ${this.renderMappingSection()}
            ${this._renderTestPanel()}
        `;
    }
}

customElements.define('code-node-editor', CodeNodeEditor);
