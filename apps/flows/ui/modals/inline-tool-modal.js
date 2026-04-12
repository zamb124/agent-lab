/**
 * Модалка редактирования tool в llm_node (code, flow, llm_node, …) из канвы / редактора.
 * Inline-код в LLM: сохраняется как type code. Редактор кода — code-node-editor. Также flow, llm_node, external_api, remote_flow, mcp.
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { FlowsStore } from '../store/flows.store.js';
import '../components/nodes/index.js';
import { isValidLlmParametersSchema } from '../utils/flow-parameters-schema.js';

export class InlineToolModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            :host {
                --modal-max-width: 900px;
            }
            
            .modal-content-wrapper {
                position: relative;
                min-height: 400px;
            }

            .modal.fullscreen .modal-content-wrapper {
                min-height: 0;
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
                min-width: 0;
                overflow: hidden;
            }

            .action-row {
                display: flex;
                gap: var(--space-3);
                padding-top: var(--space-2);
            }
            
        `
    ];

    static properties = {
        toolConfig: { type: Object },
        toolType: { type: String },
        mode: { type: String },
        flowVariables: { type: Object },
        flowId: { type: String },
        skillId: { type: String },
        previewExecutionState: { type: Object },
    };

    constructor() {
        super();
        this.toolConfig = {};
        this.toolType = 'code';
        this.mode = 'create';
        this.flowVariables = {};
        this.flowId = '';
        this.skillId = 'base';
        this.previewExecutionState = null;
        this._updateModalTitle();
    }

    connectedCallback() {
        super.connectedCallback();
        this._updateModalTitle();
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('toolType') || changedProperties.has('mode')) {
            this._updateModalTitle();
        }
    }

    _updateModalTitle() {
        const typeKey = `inline_tool_modal.types.${this.toolType}`;
        let label = this.i18n.t(typeKey);
        if (label === typeKey) {
            label = this.i18n.t('inline_tool_modal.type_fallback');
        }
        this.title = this.mode === 'create'
            ? this.i18n.t('inline_tool_modal.title_create', { label })
            : this.i18n.t('inline_tool_modal.title_edit', { label });
    }

    _onConfigChanged(e) {
        this.toolConfig = { ...this.toolConfig, ...e.detail.config };
    }

    _onSave() {
        const editor = this.shadowRoot.querySelector('[data-editor]');
        if (!editor) {
            this.error(this.i18n.t('inline_tool_modal.err_editor_missing'));
            return;
        }

        if (typeof editor.flushEmbeddedJsonEditors === 'function') {
            editor.flushEmbeddedJsonEditors();
        }

        const config = editor.nodeConfig;

        if (this.toolType === 'code') {
            const ps = config.parameters_schema;
            if (ps !== undefined && ps !== null && !isValidLlmParametersSchema(ps)) {
                this.error(this.i18n.t('inline_tool_modal.err_parameters_schema_invalid'));
                return;
            }
        }

        if (this.toolType === 'code' && (!config.code || !config.code.trim())) {
            this.error(this.i18n.t('inline_tool_modal.err_code_tool'));
            return;
        }
        
        if (this.toolType === 'llm_node' && (!config.prompt || !config.prompt.trim())) {
            this.error(this.i18n.t('inline_tool_modal.err_prompt_llm'));
            return;
        }
        
        if (!config.name || !config.name.trim()) {
            this.error(this.i18n.t('inline_tool_modal.err_name_required'));
            return;
        }
        
        // Генерируем tool_id если его нет
        const toolId = this.toolConfig.tool_id || this._generateToolId(config.name);
        
        const persistedType = this.toolType === 'code' ? 'code' : this.toolType;
        const finalConfig = {
            ...config,
            tool_id: toolId,
            type: persistedType,
        };
        
        this.emit('tool-saved', { toolId, config: finalConfig });
        this.close();
    }

    _generateToolId(name) {
        return name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, '');
    }

    /**
     * Тот же expanded, что у панели свойств при развороте: двухколоночный sidebar + основная зона.
     * В модалке включается вместе с «на весь экран» GlassModal.
     */
    _editorExpanded() {
        return this._isFullscreen;
    }

    _shellNodeId() {
        const tid = this.toolConfig?.tool_id;
        if (tid == null) {
            return '';
        }
        const s = String(tid).trim();
        return s;
    }

    _graphNodesFromCurrentFlow() {
        const raw = FlowsStore.state.editor?.flowConfig?.nodes;
        if (!raw || typeof raw !== 'object') {
            return [];
        }
        return Object.keys(raw).map((id) => ({
            id,
            name: raw[id]?.name || id,
            type: raw[id]?.type || '',
        }));
    }

    _renderEditor() {
        const config = this.toolConfig;
        const expanded = this._editorExpanded();
        const nodeId = this._shellNodeId();
        const graphNodes = this._graphNodesFromCurrentFlow();

        switch (this.toolType) {
            case 'code':
                return html`
                    <code-node-editor
                        data-editor
                        .nodeConfig=${config}
                        .nodeId=${nodeId}
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                        .flowVariables=${this.flowVariables}
                        .previewExecutionState=${this.previewExecutionState}
                        ?expanded=${expanded}
                        @config-change=${this._onConfigChanged}
                    ></code-node-editor>
                `;

            case 'llm_node':
            case 'flow':
                return html`
                    <llm-node-editor
                        data-editor
                        .nodeConfig=${config}
                        .nodeId=${nodeId}
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                        .flowVariables=${this.flowVariables}
                        .previewExecutionState=${this.previewExecutionState}
                        .graphNodes=${graphNodes}
                        ?expanded=${expanded}
                        @config-change=${this._onConfigChanged}
                    ></llm-node-editor>
                `;
            
            case 'external_api':
                return html`
                    <external-api-editor
                        data-editor
                        .nodeConfig=${config}
                        .nodeId=${nodeId}
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                        .flowVariables=${this.flowVariables}
                        .previewExecutionState=${this.previewExecutionState}
                        ?expanded=${expanded}
                        @config-change=${this._onConfigChanged}
                    ></external-api-editor>
                `;
            
            case 'remote_flow':
                return html`
                    <remote-flow-editor
                        data-editor
                        .nodeConfig=${config}
                        .nodeId=${nodeId}
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                        .flowVariables=${this.flowVariables}
                        .previewExecutionState=${this.previewExecutionState}
                        ?expanded=${expanded}
                        @config-change=${this._onConfigChanged}
                    ></remote-flow-editor>
                `;
            
            case 'mcp':
                return html`
                    <mcp-node-editor
                        data-editor
                        .nodeConfig=${config}
                        .nodeId=${nodeId}
                        .flowId=${this.flowId}
                        .skillId=${this.skillId}
                        .flowVariables=${this.flowVariables}
                        .previewExecutionState=${this.previewExecutionState}
                        ?expanded=${expanded}
                        @config-change=${this._onConfigChanged}
                    ></mcp-node-editor>
                `;
            
            default:
                return html`<div>${this.i18n.t('inline_tool_modal.err_unknown_type', { type: this.toolType })}</div>`;
        }
    }

    renderBody() {
        return html`
            <div class="modal-content-wrapper">
                ${this._renderEditor()}
            </div>
        `;
    }

    renderSaveHeaderButton() {
        const title =
            this.mode === 'create'
                ? this.i18n.t('inline_tool_modal.create')
                : this.i18n.t('inline_tool_modal.save');
        return this._renderHeaderSaveIcon({
            onClick: () => this._onSave(),
            disabled: false,
            title,
        });
    }

    renderFooter() {
        return html`
            <div class="action-row">
                <button type="button" class="btn btn-secondary" @click=${this.close}>
                    ${this.i18n.t('editor.cancel')}
                </button>
            </div>
        `;
    }
}

customElements.define('inline-tool-modal', InlineToolModal);

