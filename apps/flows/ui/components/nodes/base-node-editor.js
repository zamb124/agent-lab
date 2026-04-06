/**
 * BaseNodeEditor - базовый класс для редакторов нод
 * Использует shared form стили (DRY)
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '../editors/tag-input.js';
import '../editors/json-field-editor.js';
import '../editors/state-mapping-editor.js';
import '../editors/test-panel.js';
import { setFlowsNodeFileDragData } from '../../utils/file-signature.js';

export class BaseNodeEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        formStyles,
        buttonStyles,
        css`
            .panel-body {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            
            .panel-layout {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            
            :host([expanded]) .panel-layout {
                flex-direction: row;
                align-items: flex-start;
                gap: var(--space-6);
            }
            
            .panel-sidebar {
                display: none;
            }
            
            :host([expanded]) .panel-sidebar {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                width: 280px;
                flex-shrink: 0;
                padding-right: var(--space-6);
                border-right: 1px solid var(--border-subtle);
            }
            
            .panel-main {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }

            :host([expanded]) .panel-main {
                min-height: 0;
            }

            :host([expanded][data-editor-fullscreen]) .panel-sidebar,
            :host([expanded]:has(code-editor.fullscreen)) .panel-sidebar,
            :host([expanded]:has(json-field-editor.fullscreen)) .panel-sidebar {
                display: none;
            }

            :host([expanded][data-editor-fullscreen]) .panel-layout,
            :host([expanded]:has(code-editor.fullscreen)) .panel-layout,
            :host([expanded]:has(json-field-editor.fullscreen)) .panel-layout {
                gap: 0;
            }
            
            .sidebar-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            
            .sidebar-section-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            
            .code-mode-row {
                display: flex;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            
            .code-mode-btn {
                flex: 1;
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .code-mode-btn:hover {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
                border-color: var(--border-medium);
            }
            
            .code-mode-btn.active {
                color: var(--accent-text);
                background: var(--accent-bg);
                border-color: var(--accent);
                box-shadow: 0 0 0 3px var(--accent-glow);
            }

            /* Higher specificity than .form-input and :host-context(light) .form-input in form.styles */
            .form-input.node-id-input--locked {
                background: rgba(255, 255, 255, 0.04);
                background-image: none;
                color: var(--text-tertiary, rgba(255, 255, 255, 0.45));
                border-color: var(--border-subtle, rgba(255, 255, 255, 0.08));
                box-shadow: none;
                cursor: not-allowed;
                -webkit-backdrop-filter: none;
                backdrop-filter: none;
            }

            .form-input.node-id-input--locked:hover {
                border-color: var(--border-subtle, rgba(255, 255, 255, 0.08));
                box-shadow: none;
            }

            .form-input.node-id-input--locked:focus {
                outline: none;
                background: rgba(255, 255, 255, 0.04);
                background-image: none;
                border-color: var(--border-subtle, rgba(255, 255, 255, 0.1));
                box-shadow: none;
                color: var(--text-tertiary, rgba(255, 255, 255, 0.45));
            }

            :host-context([data-theme='light']) .form-input.node-id-input--locked {
                color: rgba(34, 34, 34, 0.42);
                background: rgba(34, 34, 34, 0.07);
                background-image: none;
                border-color: rgba(34, 34, 34, 0.12);
                box-shadow: inset 0 1px 0 rgba(34, 34, 34, 0.04);
            }

            :host-context([data-theme='light']) .form-input.node-id-input--locked:focus {
                color: rgba(34, 34, 34, 0.42);
                background: rgba(34, 34, 34, 0.07);
                background-image: none;
                border-color: rgba(34, 34, 34, 0.14);
                box-shadow: inset 0 1px 0 rgba(34, 34, 34, 0.04);
            }

            .node-attached-files-block {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin-top: var(--space-2);
                align-items: flex-start;
            }

            .node-attached-files-block--single {
                flex-direction: row;
                flex-wrap: nowrap;
                align-items: center;
            }

            .node-attached-files-block--single .node-file-chips {
                flex: 1 1 auto;
                min-width: 0;
                margin-top: 0;
            }

            .node-attach-icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                padding: 0;
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition:
                    color var(--duration-fast) var(--easing-default),
                    background var(--duration-fast) var(--easing-default),
                    border-color var(--duration-fast) var(--easing-default);
            }

            .node-attach-icon-btn:hover:not(:disabled) {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
                border-color: var(--border-medium);
            }

            .node-attach-icon-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .node-file-chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }

            .node-file-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                max-width: 100%;
                padding: 4px 8px;
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
                border: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
                cursor: grab;
            }

            .node-attached-files-block--single .node-file-chip {
                max-width: 100%;
                width: 100%;
                box-sizing: border-box;
            }

            .node-file-chip:active {
                cursor: grabbing;
            }

            .node-file-chip-drag {
                display: inline-flex;
                align-items: center;
                flex-shrink: 0;
                color: var(--text-tertiary);
                cursor: grab;
                line-height: 0;
                margin-right: 2px;
            }

            .node-file-chip-drag:active {
                cursor: grabbing;
            }

            .node-file-chip-name {
                min-width: 0;
                flex: 1 1 auto;
                max-width: 220px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .node-attached-files-block--single .node-file-chip-name {
                max-width: none;
            }

            .node-file-chip-remove {
                flex-shrink: 0;
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                padding: 0 2px;
                line-height: 1;
                font-size: var(--text-base);
            }

            .node-file-chip-remove:hover {
                color: var(--error);
            }

            .node-attach-input-hidden {
                position: absolute;
                width: 0;
                height: 0;
                opacity: 0;
                pointer-events: none;
            }
        `
    ];

    static properties = {
        nodeId: { type: String },
        nodeConfig: { type: Object },
        flowId: { type: String },
        skillId: { type: String },
        flowVariables: { type: Object },
        previewExecutionState: { type: Object },
        expanded: { type: Boolean },
        allowNodeIdRenameOnce: { type: Boolean },
        _nodeAttachUploading: { state: true },
    };

    constructor() {
        super();
        this.nodeId = '';
        this.nodeConfig = {};
        this.flowId = '';
        this.skillId = '';
        this.flowVariables = {};
        this.previewExecutionState = null;
        this.expanded = false;
        this.allowNodeIdRenameOnce = false;
        this._nodeAttachUploading = false;
        this._testStateSnapshot = { content: '', messages: [], variables: {} };
    }

    _getStateKeys() {
        return Object.keys(this._testStateSnapshot || {});
    }

    _renderTestPanel() {
        return html`
            <test-panel
                .inputState=${this._testStateSnapshot}
                .defaultInputState=${this._testStateSnapshot}
                ?expanded=${this.expanded}
                ?hide-input-state=${this.expanded}
                @validate=${this._onValidate}
                @execute=${this._onExecute}
            ></test-panel>
        `;
    }

    _updateConfig(field, value) {
        console.log('[BaseNodeEditor] _updateConfig called:', { 
            nodeId: this.nodeId, 
            field, 
            value,
            oldNodeConfig: this.nodeConfig
        });
        
        this.nodeConfig = {
            ...this.nodeConfig,
            [field]: value
        };
        
        console.log('[BaseNodeEditor] New nodeConfig:', this.nodeConfig);
        
        this.emit('config-change', { field, value, config: this.nodeConfig });
    }

    _onInputChange(field, value) {
        this._updateConfig(field, value);
    }

    _executePayloadNodeType() {
        return this.nodeConfig?.type || this._nodeType;
    }

    async _onValidate(e) {
        const nodeType = this._executePayloadNodeType();
        
        console.log('[BaseNodeEditor] _onValidate called', {
            nodeId: this.nodeId,
            nodeConfigNodeId: this.nodeConfig?.nodeId,
            nodeConfigType: this.nodeConfig?.type,
            _nodeType: this._nodeType,
            finalNodeType: nodeType,
            flowId: this.flowId,
            skillId: this.skillId
        });
        
        if (!nodeType) {
            this.error(this.i18n.t('base_node_editor.err_no_type'));
            return;
        }

        const state = e.detail.state;
        const testPanel = e.target;
        
        testPanel.setLoading(true);

        try {
            const result = await this.a2a.validateNode(nodeType, this.nodeConfig, state, this.flowId, this.skillId);
            
            testPanel.setResult(result);
            
            if (result.valid || result.success) {
                this.success(this.i18n.t('base_node_editor.validation_ok'));
            } else {
                this.error(result.error || this.i18n.t('base_node_editor.validation_failed'));
            }
        } catch (err) {
            console.error('[BaseNodeEditor] Validate error:', err);
            testPanel.setResult({ success: false, error: err.message });
            this.error(this.i18n.t('base_node_editor.validation_error', { message: err.message }));
        }
    }

    async _onExecute(e) {
        const nodeType = this._executePayloadNodeType();
        
        console.log('[BaseNodeEditor] _onExecute called', {
            nodeId: this.nodeId,
            nodeConfigNodeId: this.nodeConfig?.nodeId,
            nodeConfigType: this.nodeConfig?.type,
            _nodeType: this._nodeType,
            finalNodeType: nodeType,
            flowId: this.flowId,
            skillId: this.skillId,
            fullNodeConfig: this.nodeConfig
        });
        
        if (!nodeType) {
            this.error(this.i18n.t('base_node_editor.err_no_type'));
            console.error('[BaseNodeEditor] nodeConfig:', this.nodeConfig);
            return;
        }

        const state = e.detail.state;
        const testPanel = e.target;
        
        testPanel.setLoading(true);

        try {
            console.log('[BaseNodeEditor] Calling executeNode with:', {
                nodeType: nodeType,
                nodeConfig: this.nodeConfig,
                state,
                flowId: this.flowId,
                skillId: this.skillId
            });
            
            const result = await this.a2a.executeNode(nodeType, this.nodeConfig, state, this.flowId, this.skillId);
            
            testPanel.setResult(result);
            
            if (result.success) {
                this.success(this.i18n.t('base_node_editor.execute_ok'));
            } else {
                this.error(result.error || this.i18n.t('base_node_editor.execute_failed'));
            }
        } catch (err) {
            console.error('[BaseNodeEditor] Execute error:', err);
            testPanel.setResult({ success: false, error: err.message });
            this.error(this.i18n.t('base_node_editor.execute_error', { message: err.message }));
        }
    }

    _deleteNode() {
        this.emit('node-delete', { nodeId: this.nodeId });
    }

    /**
     * Обработчик изменения Node ID
     * Валидирует формат и эмитит событие для обновления
     */
    _onNodeIdChange(e) {
        if (!this.allowNodeIdRenameOnce) {
            e.target.value = this.nodeId;
            return;
        }

        const newId = e.target.value.trim();

        if (!newId) {
            this.error(this.i18n.t('base_node_editor.node_id_empty'));
            e.target.value = this.nodeId;
            return;
        }
        
        if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(newId)) {
            this.error(this.i18n.t('base_node_editor.node_id_format'));
            e.target.value = this.nodeId;
            return;
        }
        
        if (newId !== this.nodeId) {
            this.emit('node-id-changed', {
                oldId: this.nodeId,
                newId: newId
            });
        }
    }

    /**
     * Рендер поля для редактирования Node ID
     * Унифицированный компонент для всех типов нод
     */
    renderNodeIdField() {
        const hintKey = this.allowNodeIdRenameOnce
            ? 'base_node_editor.node_id_rename_once_hint'
            : 'base_node_editor.node_id_locked_hint';
        return html`
            <div class="form-group">
                <div class="form-label form-label-inline">
                    <span class="form-label-text form-label-inline-text">${this.i18n.t(
                        'node_modal.common.sidebar_node_id'
                    )}</span>
                    <platform-help-hint
                        label=${this.i18n.t('base_node_editor.node_id_help_aria')}
                        .text=${this.i18n.t(hintKey)}
                    ></platform-help-hint>
                </div>
                <input
                    type="text"
                    class="form-input${this.allowNodeIdRenameOnce ? '' : ' node-id-input--locked'}"
                    .value=${this.nodeId}
                    ?readonly=${!this.allowNodeIdRenameOnce}
                    @change=${this._onNodeIdChange}
                    placeholder=${this.i18n.t('base_node_editor.placeholder_node_id')}
                />
            </div>
        `;
    }

    renderDescription() {
        return '';
    }

    /**
     * Общие поля для sidebar в expanded режиме
     * Переопределяется в subclasses для добавления специфичных полей
     */
    renderCommonFields() {
        const config = this.nodeConfig;
        return html`
            <div class="sidebar-section">
                <div class="sidebar-section-title">${this.i18n.t('base_node_editor.section_main')}</div>
                ${this.renderNodeIdField()}
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">${this.i18n.t('llm_node.field_name')}</span>
                    </div>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${config.name || ''}
                        @change=${(e) => this._onInputChange('name', e.target.value)}
                        placeholder=${this.i18n.t('base_node_editor.placeholder_node_name')}
                    />
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">${this.i18n.t('llm_node.field_description')}</span>
                    </div>
                    <textarea 
                        class="form-input form-textarea"
                        rows="3"
                        .value=${config.description || ''}
                        @change=${(e) => this._onInputChange('description', e.target.value)}
                        placeholder=${this.i18n.t('base_node_editor.placeholder_node_description')}
                    ></textarea>
                </div>
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">${this.i18n.t('llm_node.field_tags')}</span>
                    </div>
                    <tag-input
                        .tags=${config.tags || []}
                        @change=${(e) => this._onInputChange('tags', e.detail.tags)}
                    ></tag-input>
                </div>
                ${this.renderNodeAttachedFilesSection()}
            </div>
            
            ${this.renderInputStateSection()}
        `;
    }

    renderNodeAttachedFilesSection() {
        const files = Array.isArray(this.nodeConfig?.files) ? this.nodeConfig.files : [];
        return html`
            <div class="form-group">
                <div class="form-label form-label-inline">
                    <span class="form-label-text form-label-inline-text">${this.i18n.t(
                        'base_node_editor.attached_files_label'
                    )}</span>
                    <platform-help-hint
                        label=${this.i18n.t('base_node_editor.attached_files_help_aria')}
                        .text=${this.i18n.t('base_node_editor.attached_files_hint')}
                    ></platform-help-hint>
                </div>
                <input
                    type="file"
                    class="node-attach-input-hidden"
                    id="node-attach-file-input"
                    multiple
                    @change=${this._onNodeAttachFileInput}
                />
                <div
                    class="node-attached-files-block${files.length === 1
                        ? ' node-attached-files-block--single'
                        : ''}"
                >
                    <button
                        type="button"
                        class="node-attach-icon-btn"
                        ?disabled=${this._nodeAttachUploading}
                        aria-label=${this.i18n.t('base_node_editor.attach_file')}
                        @click=${this._openNodeAttachFilePicker}
                    >
                        <platform-icon name="paperclip" size="18"></platform-icon>
                    </button>
                    ${files.length
                        ? html`
                              <div class="node-file-chips">
                                  ${files.map(
                                      (f, i) => html`
                                          <span
                                              class="node-file-chip"
                                              draggable="true"
                                              @dragstart=${(e) => this._onNodeFileDragStart(e, f)}
                                              title=${this.i18n.t('base_node_editor.file_chip_drag_hint')}
                                          >
                                              <span
                                                  class="node-file-chip-drag"
                                                  title=${this.i18n.t('base_node_editor.file_chip_drag_hint')}
                                              >
                                                  <platform-icon
                                                      name="drag-handle"
                                                      size="14"
                                                  ></platform-icon>
                                              </span>
                                              <span class="node-file-chip-name">${f.name || f.path || 'file'}</span>
                                              <button
                                                  type="button"
                                                  class="node-file-chip-remove"
                                                  @click=${() => this._removeAttachedFile(i)}
                                                  aria-label=${this.i18n.t(
                                                      'base_node_editor.remove_attached_file'
                                                  )}
                                              >
                                                  &times;
                                              </button>
                                          </span>
                                      `
                                  )}
                              </div>
                          `
                        : ''}
                </div>
            </div>
        `;
    }

    _openNodeAttachFilePicker() {
        this.shadowRoot?.getElementById('node-attach-file-input')?.click();
    }

    async _onNodeAttachFileInput(e) {
        const input = e.target;
        const list = Array.from(input.files || []);
        input.value = '';
        if (!list.length) {
            return;
        }
        const api = this.filesApi;
        if (!api) {
            this.error(this.i18n.t('base_node_editor.files_api_missing'));
            return;
        }
        this._nodeAttachUploading = true;
        const current = Array.isArray(this.nodeConfig.files) ? [...this.nodeConfig.files] : [];
        try {
            for (const file of list) {
                const rec = await api.uploadFile(file);
                const path = api.buildDownloadUrl(rec.file_id);
                current.push({
                    name: rec.original_name,
                    path,
                    mime_type: rec.content_type,
                    size: rec.file_size,
                    file_id: rec.file_id,
                });
            }
            this._updateConfig('files', current);
            this.success(this.i18n.t('base_node_editor.attached_files_upload_ok'));
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.error(this.i18n.t('base_node_editor.attached_files_upload_err', { message: msg }));
        } finally {
            this._nodeAttachUploading = false;
        }
    }

    _removeAttachedFile(index) {
        const current = Array.isArray(this.nodeConfig.files) ? [...this.nodeConfig.files] : [];
        current.splice(index, 1);
        this._updateConfig('files', current);
    }

    _onNodeFileDragStart(e, file) {
        setFlowsNodeFileDragData(e.dataTransfer, file);
    }

    /**
     * Секция Input State для sidebar при expanded режиме
     */
    renderInputStateSection() {
        return html`
            <div class="sidebar-section">
                <div class="sidebar-section-title">${this.i18n.t('base_node_editor.input_state_section_title')}</div>
                <div class="form-group">
                    <json-field-editor
                        id="sidebar-input-state"
                        .value=${JSON.stringify(this._testStateSnapshot, null, 2)}
                        min-height="150"
                        placeholder='{"content": "", "messages": []}'
                        @change=${this._onInputStateChange}
                    ></json-field-editor>
                    <button 
                        type="button" 
                        class="form-hint" 
                        style="cursor: pointer; border: none; background: none; text-decoration: underline;"
                        @click=${this._onResetInputState}
                    >↺ ${this.i18n.t('base_node_editor.reset_input_state')}</button>
                </div>
            </div>
        `;
    }

    _onInputStateChange(e) {
        const testPanel = this.shadowRoot?.querySelector('test-panel');
        if (testPanel && e.target.isValid()) {
            testPanel.setInputState(e.target.getParsedValue());
        }
    }

    _onResetInputState() {
        const editor = this.shadowRoot?.querySelector('#sidebar-input-state');
        const testPanel = this.shadowRoot?.querySelector('test-panel');
        const snapshot = structuredClone(this._testStateSnapshot);
        if (editor) {
            editor.setValue(snapshot);
        }
        if (testPanel) {
            testPanel.resetInputState(snapshot);
        }
    }

    renderFields() {
        return html`<p>${this.i18n.t('base_node_editor.override_render_fields')}</p>`;
    }

    /**
     * Рендер секции input/output маппингов с табами
     * Унифицированный компонент для всех типов нод
     */
    renderMappingSection(options = {}) {
        const { showInput = true, showOutput = true } = options;
        const config = this.nodeConfig;
        
        if (showInput && showOutput) {
            return html`
                <div class="form-group">
                    <state-mapping-editor
                        mode="both"
                        .inputMappings=${config.input_mapping || {}}
                        .outputMappings=${config.output_mapping || {}}
                        .stateVariables=${this._getStateKeys()}
                        @input-change=${(e) => this._onInputChange('input_mapping', e.detail.value)}
                        @output-change=${(e) => this._onInputChange('output_mapping', e.detail.value)}
                    ></state-mapping-editor>
                </div>
            `;
        }
        
        if (showInput) {
            return html`
                <div class="form-group">
                    <state-mapping-editor
                        mode="input"
                        .mappings=${config.input_mapping || {}}
                        .stateVariables=${this._getStateKeys()}
                        @change=${(e) => this._onInputChange('input_mapping', e.detail.value)}
                    ></state-mapping-editor>
                </div>
            `;
        }
        
        if (showOutput) {
            return html`
                <div class="form-group">
                    <state-mapping-editor
                        mode="output"
                        .mappings=${config.output_mapping || {}}
                        @change=${(e) => this._onInputChange('output_mapping', e.detail.value)}
                    ></state-mapping-editor>
                </div>
            `;
        }
        
        return '';
    }

    renderActions() {
        return '';
    }

    renderResourcesSection() {
        const nodeResources = this.nodeConfig?.resources || [];
        
        if (nodeResources.length === 0) {
            return html`
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">${this.i18n.t('base_node_editor.field_resources')}</span>
                    </div>
                    <div class="form-hint" style="padding: var(--space-3); border: 1px dashed var(--border-subtle); border-radius: var(--radius-md); text-align: center;">
                        ${this.i18n.t('base_node_editor.resources_drop_hint')}
                    </div>
                </div>
            `;
        }
        
        return html`
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">${this.i18n.t('base_node_editor.field_resources')}</span>
                </div>
                <div class="resources-list" style="display: flex; flex-direction: column; gap: var(--space-2);">
                    ${nodeResources.map(res => this._renderResourceBadge(res))}
                </div>
            </div>
        `;
    }

    _renderResourceBadge(resource) {
        const colors = {
            'code': '#8b5cf6',
            'rag': '#3b82f6',
            'files': '#f59e0b',
            'prompt': '#10b981',
            'llm': '#ec4899',
            'secret': '#ef4444',
            'http': '#06b6d4',
            'cache': '#14b8a6',
        };
        const icons = {
            'code': 'code',
            'rag': 'search',
            'files': 'folder',
            'prompt': 'chat',
            'llm': 'bot',
            'secret': 'key',
            'http': 'globe',
            'cache': 'database',
        };
        
        const color = colors[resource.type] || '#6b7280';
        const icon = icons[resource.type] || 'box';
        const bgColor = color + '20';
        
        return html`
            <div class="resource-badge" style="
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                background: ${bgColor};
                border: 1px solid ${color}40;
                border-radius: var(--radius-md);
            ">
                <platform-icon name="${icon}" size="14" style="color: ${color};"></platform-icon>
                <span style="font-size: var(--text-sm); flex: 1;">${resource.resource_id || resource.resourceId}</span>
                <button 
                    class="remove-resource-btn"
                    style="background: none; border: none; padding: 2px; cursor: pointer; color: var(--text-tertiary);"
                    @click=${() => this._removeResource(resource.resource_id || resource.resourceId)}
                    title=${this.i18n.t('base_node_editor.remove_resource')}
                >
                    <platform-icon name="x" size="12"></platform-icon>
                </button>
            </div>
        `;
    }

    _removeResource(resourceId) {
        const nodeResources = this.nodeConfig?.resources || [];
        const updated = nodeResources.filter(r => (r.resource_id || r.resourceId) !== resourceId);
        this._updateConfig('resources', updated);
    }

    firstUpdated(changedProperties) {
        super.firstUpdated(changedProperties);
        if (this.previewExecutionState) {
            this._testStateSnapshot = structuredClone(this.previewExecutionState);
        }
    }

    updated(changedProperties) {
        super.updated?.(changedProperties);
        if (changedProperties.has('previewExecutionState')) {
            if (this.previewExecutionState) {
                this._testStateSnapshot = structuredClone(this.previewExecutionState);
            } else {
                this._testStateSnapshot = { content: '', messages: [], variables: {} };
            }
        }
        if (changedProperties.has('expanded')) {
            if (this.expanded) {
                this.setAttribute('expanded', '');
            } else {
                this.removeAttribute('expanded');
            }
        }
    }

    render() {
        if (this.expanded) {
            return html`
                <div class="panel-body">
                    ${this.renderDescription()}
                    <div class="panel-layout">
                        <div class="panel-sidebar">
                            ${this.renderCommonFields()}
                        </div>
                        <div class="panel-main">
                            ${this.renderFields()}
                            ${this.renderActions()}
                        </div>
                    </div>
                </div>
            `;
        }
        
        return html`
            <div class="panel-body">
                ${this.renderDescription()}
                ${this.renderNodeAttachedFilesSection()}
                ${this.renderFields()}
                ${this.renderActions()}
            </div>
        `;
    }
}

customElements.define('base-node-editor', BaseNodeEditor);
