/**
 * flows-base-node-editor — общая обёртка редакторов нод.
 *
 * Два режима рендера, выбираются атрибутом `expanded`:
 *
 * 1. compact: Header (имя) → … → «Запустить» в шапке `flows-floating-panel`
 *    (поиск панели — обход DOM с переходом ShadowRoot→host; иначе fallback).
 * 2. модалка «Инструмент» в LLM: `.embedded-tool-run-host` в шапке `flows-embedded-tool-config-modal`.
 * 3. expanded: .panel-main — fallback для Run без floating-panel и без этой модалки.
 * Запуск: `useOp('flows/code_execute')`, UI — `flows-node-run-control` (imperative mount).
 *
 * Эмитит наружу:
 *   - change { nodeId, patch } — patch с top-level полями NodeConfig
 *     (name/description/tags/incoming_policy/files/resources). Type-specific
 *     патчи приходят через slot='settings' (дочерний редактор сам диспатчит
 *     change на хосте).
 *   - rename-node { oldId, newId }
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import '../editors/flows-state-mapping-editor.js';
import '../editors/flows-tag-input.js';
import '../editors/flows-json-field-editor.js';
import '../flows-node-run-control.js';
import {
    nextCodeExecuteClientId,
    setCodeExecuteRequestClientId,
} from '../../_helpers/flows-code-execute-run-gate.js';
import { asObject, asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import { formatExecuteViewModel } from '../../_helpers/flows-execute-preview.js';

export class FlowsBaseNodeEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        expanded: { type: Boolean, reflect: true },
        /** Редактирование вложенного tool: без смены node id */
        embedded: { type: Boolean, reflect: true },
        _editingId: { state: true },
        _draftId: { state: true },
        _stateDraft: { state: true },
        _mappingTab: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                color: var(--text-primary);
                height: 100%;
                min-height: 0;
                box-sizing: border-box;
            }
            :host(:not([expanded])) {
                padding: var(--space-3);
                overflow: auto;
            }

            /* Compact layout: stacked */
            .compact {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }

            /* Expanded layout: master-detail */
            .panel-layout {
                display: grid;
                grid-template-columns: 320px 1fr;
                gap: 0;
                height: 100%;
                min-height: 0;
            }
            .panel-sidebar {
                overflow: auto;
                padding: var(--space-4);
                border-right: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                min-width: 0;
            }
            .panel-main {
                overflow: auto;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                min-width: 0;
            }

            /* Sections */
            .section {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .section-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }
            /* header */
            .header {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
            }
            .header-row {
                display: flex; align-items: center; gap: var(--space-2);
                flex-wrap: wrap;
            }
            .header-run-fallback:empty { display: none; }
            .panel-run-fallback:empty { display: none; }
            .panel-run-fallback:not(:empty) {
                display: flex;
                justify-content: flex-end;
                align-items: center;
                padding-bottom: var(--space-2);
                margin-bottom: var(--space-2);
                border-bottom: 1px solid var(--border-subtle);
            }
            input.name {
                flex: 1; min-width: 0;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-primary); font: inherit;
                font-weight: var(--font-semibold);
            }

            /* form fields */
            .field { display: flex; flex-direction: column; gap: var(--space-1); }
            .field-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                font-weight: var(--font-medium);
            }
            input.text, select.policy, input.id-edit {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-primary); font: inherit;
                width: 100%;
                box-sizing: border-box;
            }
            input.id-edit, input.text.id-readonly {
                font-family: var(--font-mono, monospace);
                font-size: var(--text-sm);
            }
            input.text.id-readonly {
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
            }
            textarea.desc {
                width: 100%; box-sizing: border-box;
                padding: var(--space-2);
                resize: vertical; min-height: 60px;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-primary); font: inherit;
            }

            .id-row {
                display: flex; align-items: center; gap: var(--space-2);
            }
            .id-row input { flex: 1; min-width: 0; }
            .icon-btn {
                background: none; border: none; padding: 4px;
                display: inline-flex; align-items: center;
                color: var(--text-tertiary); cursor: pointer;
                border-radius: var(--radius-md);
            }
            .icon-btn:hover { color: var(--accent); background: var(--glass-solid-medium); }

            /* File and resource lists */
            .item-list {
                display: flex; flex-direction: column; gap: var(--space-1);
            }
            .item-row {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-1) var(--space-2);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                font-size: var(--text-sm);
            }
            .item-row .grow {
                flex: 1; min-width: 0;
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            }
            .item-row .meta {
                color: var(--text-tertiary); font-size: var(--text-xs);
            }
            .item-row .remove {
                background: none; border: none; padding: 0; cursor: pointer;
                color: var(--text-tertiary);
                display: inline-flex; align-items: center;
            }
            .item-row .remove:hover { color: var(--error); }
            .empty {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-1) var(--space-2);
            }

            .file-list {
                display: flex; flex-direction: column; gap: var(--space-1);
            }
            .file-row {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
            }
            .file-row .file-icon { flex-shrink: 0; }
            .file-row .file-info {
                flex: 1; min-width: 0;
                display: flex; flex-direction: column; gap: 2px;
            }
            .file-row .file-name {
                font-size: var(--text-sm); color: var(--text-primary);
                font-weight: var(--font-medium);
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            }
            .file-row .file-meta {
                font-size: var(--text-xs); color: var(--text-tertiary);
            }
            .file-row .file-remove {
                background: none; border: none; padding: var(--space-1); cursor: pointer;
                color: var(--text-tertiary);
                display: inline-flex; align-items: center; justify-content: center;
                border-radius: var(--radius-sm);
                flex-shrink: 0;
            }
            .file-row .file-remove:hover { color: var(--error); background: var(--glass-solid-strong); }

            .files-attach {
                display: flex; align-items: center; gap: var(--space-2);
            }
            .files-attach .attach-btn {
                width: 36px; height: 36px;
                display: inline-flex; align-items: center; justify-content: center;
                background: var(--glass-solid-medium);
                border: 1px dashed var(--glass-border-medium);
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                cursor: pointer;
            }
            .files-attach .attach-btn:hover { color: var(--accent); border-color: var(--accent); }
            input[type="file"] { display: none; }

            .add-row select {
                width: 100%;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-primary); font: inherit;
            }

            .mapping-tabs {
                display: flex; gap: var(--space-1); margin-bottom: var(--space-2);
            }
            .mapping-tab {
                padding: 4px 12px;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                cursor: pointer;
            }
            .mapping-tab[active] {
                background: var(--accent-subtle);
                color: var(--accent);
                border-color: var(--accent-subtle);
            }

            .reset-link {
                background: none; border: none; padding: 0;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                cursor: pointer;
                text-decoration: underline;
                align-self: flex-start;
            }
            .reset-link:hover { color: var(--accent); }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
        this.nodeType = '';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.expanded = false;
        this.embedded = false;
        this._editingId = false;
        this._draftId = '';
        this._mappingTab = 'input';
        this._stateDraft = null;
        this._fileUpload = this.useOp('flows/file_upload');
        this._nodeExecute = this.useOp('flows/code_execute');
        this._codeExecuteClientId = nextCodeExecuteClientId();
        this._resources = this.useResource('flows/resources', { autoload: true });
        this._nodeRunControlEl = null;
        this._onNodeRunFired = () => { void this._runNodeTest(); };
        this._onNodeRunOpenFullEvent = (e) => { this._onOpenExecuteFull(e); };
    }

    connectedCallback() {
        super.connectedCallback();
        queueMicrotask(() => this._placeNodeRunControl());
        requestAnimationFrame(() => this._placeNodeRunControl());
    }

    disconnectedCallback() {
        if (this._nodeRunControlEl) {
            this._nodeRunControlEl.removeEventListener('run', this._onNodeRunFired);
            this._nodeRunControlEl.removeEventListener('open-full', this._onNodeRunOpenFullEvent);
            this._nodeRunControlEl.remove();
            this._nodeRunControlEl = null;
        }
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        this._placeNodeRunControl();
    }

    _ensureNodeRunControl() {
        if (this._nodeRunControlEl) {
            return this._nodeRunControlEl;
        }
        const el = document.createElement('flows-node-run-control');
        el.requestClientId = this._codeExecuteClientId;
        el.addEventListener('run', this._onNodeRunFired);
        el.addEventListener('open-full', this._onNodeRunOpenFullEvent);
        this._nodeRunControlEl = el;
        return el;
    }

    _syncNodeRunControlProps() {
        const el = this._nodeRunControlEl;
        if (!el) {
            return;
        }
        el.requestClientId = this._codeExecuteClientId;
        el.viewModel = this._executeViewModel();
        el.busy = this._nodeExecute.busy;
    }

    /**
     * `closest` не везде поднимается сквозь границы вложенных shadow root; до flows-floating-panel
     * идём вручную: parent, либо ShadowRoot -> host.
     */
    _findFlowsFloatingPanel() {
        let n = this;
        for (let d = 0; d < 128; d += 1) {
            if (!n) {
                return null;
            }
            if (n.nodeName === 'FLOWS-FLOATING-PANEL') {
                return n;
            }
            const p = n.parentNode;
            if (p instanceof ShadowRoot) {
                n = p.host;
            } else {
                n = p;
            }
        }
        return null;
    }

    _floatingPanelHeaderRunHost(panel) {
        const root = panel.shadowRoot;
        if (!root) {
            return null;
        }
        return root.querySelector('.header-actions-host');
    }

    /**
     * Редактор вложенного tool (модалка с canvas): play в шапке модалки, не в теле редактора.
     */
    _findEmbeddedToolConfigModal() {
        let n = this;
        for (let d = 0; d < 128; d += 1) {
            if (!n) {
                return null;
            }
            if (n.nodeName === 'FLOWS-EMBEDDED-TOOL-CONFIG-MODAL') {
                return n;
            }
            const p = n.parentNode;
            if (p instanceof ShadowRoot) {
                n = p.host;
            } else {
                n = p;
            }
        }
        return null;
    }

    _embeddedToolModalHeaderRunHost(modal) {
        const root = modal.shadowRoot;
        if (!root) {
            return null;
        }
        return root.querySelector('.embedded-tool-run-host');
    }

    _placeNodeRunControl() {
        if (!this.nodeConfig) {
            return;
        }
        if (!this.isConnected) {
            return;
        }
        const el = this._ensureNodeRunControl();
        this._syncNodeRunControlProps();
        const panel = this._findFlowsFloatingPanel();
        const embeddedModal = this._findEmbeddedToolConfigModal();
        const hostFromPanel = panel ? this._floatingPanelHeaderRunHost(panel) : null;
        const hostFromEmbedded = embeddedModal ? this._embeddedToolModalHeaderRunHost(embeddedModal) : null;
        let target = null;
        if (hostFromPanel) {
            target = hostFromPanel;
        } else if (hostFromEmbedded) {
            target = hostFromEmbedded;
        } else if (this.expanded) {
            target = this.renderRoot?.querySelector?.('[data-node-run-fallback="expanded"]') ?? null;
        } else {
            target = this.renderRoot?.querySelector?.('[data-node-run-fallback="compact"]') ?? null;
        }
        if (target && el.parentElement !== target) {
            target.appendChild(el);
        }
    }

    _executeViewModel() {
        return formatExecuteViewModel({
            opError: this._nodeExecute.error,
            lastResult: this._nodeExecute.lastResult,
        });
    }

    async _runNodeTest() {
        let state;
        try {
            state = JSON.parse(this._stateValue());
        } catch {
            this.toast('flows:test_panel.toast_state_invalid', { type: 'error' });
            return;
        }
        if (state === null || typeof state !== 'object' || Array.isArray(state)) {
            this.toast('flows:test_panel.toast_state_invalid', { type: 'error' });
            return;
        }
        const skill = typeof this.skillId === 'string' && this.skillId.length > 0 ? this.skillId : 'base';
        setCodeExecuteRequestClientId(this._codeExecuteClientId);
        await this._nodeExecute.run({
            node_type: this.nodeType,
            node_config: asObject(this.nodeConfig),
            state,
            flow_id: this.flowId,
            skill_id: skill,
        });
    }

    _onOpenExecuteFull(e) {
        const d = e.detail;
        if (!d || typeof d.value !== 'object' || d.value === null) {
            throw new Error('flows-base-node-editor: open-full event requires detail.value object');
        }
        this.openModal('flows.raw_json', { value: d.value });
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onName(e) { this._emitPatch({ name: e.target.value }); }
    _onDescription(e) { this._emitPatch({ description: e.target.value }); }
    _onTags(e) {
        const tags = Array.isArray(e.detail?.tags) ? e.detail.tags : [];
        this._emitPatch({ tags });
    }
    _onPolicy(e) {
        const v = e.target.value === 'all' ? 'all' : 'any';
        this._emitPatch({ incoming_policy: v });
    }
    _onMapping(field, e) {
        const mapping = e.detail?.mapping;
        this._emitPatch({ [field]: isPlainObject(mapping) ? mapping : {} });
    }

    _startRenameId() {
        if (this.embedded) {
            return;
        }
        this._editingId = true;
        this._draftId = this.nodeId;
    }
    _commitRenameId() {
        const draft = asString(this._draftId).trim();
        this._editingId = false;
        if (!draft || draft === this.nodeId) return;
        if (!/^[a-zA-Z0-9_]+$/.test(draft)) {
            this.toast('flows:base_node_editor.rename_invalid', { type: 'error' });
            return;
        }
        this.emit('rename-node', { oldId: this.nodeId, newId: draft });
    }
    _cancelRenameId() { this._editingId = false; }

    async _onUploadFile(e) {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        const input = e.target;
        const result = await this._fileUpload.run({ file });
        if (!result || typeof result.file_id !== 'string') {
            throw new Error('flows-base-node-editor: file_upload op must return result.file_id');
        }
        const name = typeof result.original_name === 'string' && result.original_name !== ''
            ? result.original_name
            : file.name;
        const mimeType = typeof result.content_type === 'string' && result.content_type !== ''
            ? result.content_type
            : file.type;
        const size = typeof result.file_size === 'number' ? result.file_size : file.size;
        const files = Array.isArray(this.nodeConfig?.files) ? this.nodeConfig.files : [];
        const next = [...files, {
            file_id: result.file_id,
            name,
            mime_type: mimeType,
            size,
        }];
        this._emitPatch({ files: next });
        input.value = '';
    }

    _formatFileSize(bytes) {
        if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes < 0) return '';
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
        return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    }

    _onRemoveFile(idx) {
        const files = Array.isArray(this.nodeConfig?.files) ? this.nodeConfig.files : [];
        this._emitPatch({ files: files.filter((_, i) => i !== idx) });
    }

    _onAddResource(e) {
        const resourceId = e.target.value;
        e.target.value = '';
        if (!resourceId) return;
        const resources = this.nodeConfig?.resources && typeof this.nodeConfig.resources === 'object'
            ? this.nodeConfig.resources
            : {};
        if (resources[resourceId]) return;
        const next = { ...resources, [resourceId]: { resource_id: resourceId } };
        this._emitPatch({ resources: next });
    }

    _onRemoveResource(key) {
        const resources = this.nodeConfig?.resources && typeof this.nodeConfig.resources === 'object'
            ? this.nodeConfig.resources
            : {};
        const next = { ...resources };
        delete next[key];
        this._emitPatch({ resources: next });
    }

    _stateValue() {
        if (typeof this._stateDraft === 'string') return this._stateDraft;
        const preview = this.previewExecutionState;
        if (!preview) return '{}';
        return JSON.stringify(preview, null, 2);
    }

    _onStateChange(e) {
        const v = e.detail?.value;
        if (typeof v === 'string') this._stateDraft = v;
    }

    _onStateReset() {
        this._stateDraft = null;
        this.requestUpdate();
    }

    _renderHeader() {
        const cfg = this.nodeConfig;
        const name = typeof cfg?.name === 'string' ? cfg.name : '';
        return html`
            <div class="header">
                <div class="header-row">
                    <input
                        class="name" type="text"
                        placeholder=${this.t('base_node_editor.name')}
                        .value=${name}
                        @input=${this._onName}
                    />
                </div>
                <div class="header-run-fallback" data-node-run-fallback="compact"></div>
            </div>
        `;
    }

    _renderBasic() {
        const cfg = this.nodeConfig;
        const description = typeof cfg?.description === 'string' ? cfg.description : '';
        const tags = Array.isArray(cfg?.tags) ? cfg.tags : [];
        const policy = cfg?.incoming_policy === 'all' ? 'all' : 'any';
        const files = Array.isArray(cfg?.files) ? cfg.files : [];
        return html`
            <div class="section">
                <div class="section-title">${this.t('base_node_editor.section_basic')}</div>
                <div class="field">
                    <span class="field-label">${this.t('base_node_editor.node_id')}</span>
                    ${this.embedded ? html`
                        <div class="id-row">
                            <input class="text id-readonly" type="text" readonly .value=${this.nodeId} />
                        </div>
                    ` : this._editingId ? html`
                        <div class="id-row">
                            <input
                                class="id-edit" type="text"
                                .value=${this._draftId}
                                @input=${(e) => { this._draftId = e.target.value; }}
                                @keydown=${(e) => {
                                    if (e.key === 'Enter') this._commitRenameId();
                                    if (e.key === 'Escape') this._cancelRenameId();
                                }}
                            />
                            <glass-button size="sm" variant="primary" @click=${this._commitRenameId}>${this.t('base_node_editor.rename_save')}</glass-button>
                            <glass-button size="sm" variant="ghost" @click=${this._cancelRenameId}>${this.t('base_node_editor.rename_cancel')}</glass-button>
                        </div>
                    ` : html`
                        <div class="id-row">
                            <input class="text id-readonly" type="text" readonly .value=${this.nodeId} />
                            <button class="icon-btn" type="button" title=${this.t('base_node_editor.rename_id')} @click=${this._startRenameId}>
                                <platform-icon name="edit" size="14"></platform-icon>
                            </button>
                        </div>
                    `}
                </div>
                <div class="field">
                    <span class="field-label">${this.t('base_node_editor.name')}</span>
                    <input
                        class="text" type="text"
                        placeholder=${this.t('base_node_editor.name')}
                        .value=${typeof cfg?.name === 'string' ? cfg.name : ''}
                        @input=${this._onName}
                    />
                </div>
                <div class="field">
                    <span class="field-label">${this.t('base_node_editor.description')}</span>
                    <textarea
                        class="desc"
                        placeholder=${this.t('base_node_editor.description_hint')}
                        .value=${description}
                        @input=${this._onDescription}
                    ></textarea>
                </div>
                <div class="field">
                    <span class="field-label">${this.t('base_node_editor.tags')}</span>
                    <flows-tag-input
                        .tags=${tags}
                        placeholder=${this.t('tag_input.placeholder')}
                        @change=${this._onTags}
                    ></flows-tag-input>
                </div>
                <div class="field">
                    <span class="field-label">${this.t('base_node_editor.files_section')}</span>
                    ${files.length === 0
                        ? html`<div class="empty">${this.t('base_node_editor.files_empty')}</div>`
                        : html`<div class="file-list">
                            ${files.map((f, i) => {
                                const fname = typeof f.name === 'string' && f.name !== '' ? f.name : f.file_id;
                                const fmime = typeof f.mime_type === 'string' ? f.mime_type : '';
                                const fsize = this._formatFileSize(f.size);
                                return html`
                                    <div class="file-row">
                                        <platform-icon
                                            class="file-icon"
                                            file-icon
                                            name=${resolveFileIconKey(fname, fmime)}
                                            size="28"
                                        ></platform-icon>
                                        <div class="file-info">
                                            <span class="file-name" title=${fname}>${fname}</span>
                                            ${fsize
                                                ? html`<span class="file-meta">${fsize}</span>`
                                                : ''}
                                        </div>
                                        <button class="file-remove" type="button" title=${this.t('base_node_editor.files_remove')} @click=${() => this._onRemoveFile(i)}>
                                            <platform-icon name="trash" size="14"></platform-icon>
                                        </button>
                                    </div>
                                `;
                            })}
                        </div>`}
                    <div class="files-attach">
                        <label class="attach-btn" title=${this.t('base_node_editor.files_section')}>
                            <platform-icon name="paperclip" size="18"></platform-icon>
                            <input type="file" @change=${this._onUploadFile} ?disabled=${this._fileUpload.busy} />
                        </label>
                    </div>
                </div>
                <div class="field">
                    <span class="field-label">${this.t('base_node_editor.incoming_policy')}</span>
                    <select class="policy" .value=${policy} @change=${this._onPolicy}>
                        <option value="any" ?selected=${policy === 'any'}>${this.t('base_node_editor.incoming_policy_any')}</option>
                        <option value="all" ?selected=${policy === 'all'}>${this.t('base_node_editor.incoming_policy_all')}</option>
                    </select>
                </div>
            </div>
        `;
    }

    _renderResources() {
        const cfg = this.nodeConfig;
        const resources = cfg?.resources && typeof cfg.resources === 'object' ? cfg.resources : {};
        const allResources = Array.isArray(this._resources.items) ? this._resources.items : [];
        const availableResources = allResources.filter((r) => r && !resources[r.resource_id]);
        return html`
            <div class="section">
                <div class="section-title">${this.t('base_node_editor.section_resources')}</div>
                ${Object.keys(resources).length === 0
                    ? html`<div class="empty">${this.t('base_node_editor.resources_empty')}</div>`
                    : html`<div class="item-list">
                        ${Object.entries(resources).map(([key, ref]) => {
                            const def = allResources.find((r) => r && r.resource_id === (ref && typeof ref.resource_id === 'string' ? ref.resource_id : key));
                            return html`
                                <div class="item-row">
                                    <span class="grow">${def ? def.name : key}</span>
                                    <span class="meta">${def ? def.type : ''}</span>
                                    <button class="remove" type="button" title=${this.t('base_node_editor.resources_remove')} @click=${() => this._onRemoveResource(key)}>
                                        <platform-icon name="trash" size="14"></platform-icon>
                                    </button>
                                </div>
                            `;
                        })}
                    </div>`}
                <div class="add-row">
                    <select @change=${this._onAddResource}>
                        <option value="">${this.t('base_node_editor.resources_add_pick')}</option>
                        ${availableResources.map((r) => html`
                            <option value=${r.resource_id}>${r.name} · ${r.type}</option>
                        `)}
                    </select>
                </div>
            </div>
        `;
    }

    _renderInputState() {
        const value = this._stateValue();
        return html`
            <div class="section">
                <div class="section-title">${this.t('base_node_editor.section_input_state')}</div>
                <flows-json-field-editor
                    .value=${value}
                    @change=${this._onStateChange}
                ></flows-json-field-editor>
                <button class="reset-link" type="button" @click=${this._onStateReset}>
                    ${this.t('base_node_editor.input_state_reset')}
                </button>
            </div>
        `;
    }

    _renderMapping() {
        const cfg = asObject(this.nodeConfig);
        const tab = this._mappingTab;
        const isMcp = this.nodeType === 'mcp';
        let rawMapping;
        let field;
        if (tab === 'input') {
            rawMapping = cfg.input_mapping;
            field = 'input_mapping';
        } else if (isMcp) {
            rawMapping = cfg.state_mapping;
            field = 'state_mapping';
        } else {
            rawMapping = cfg.output_mapping;
            field = 'output_mapping';
        }
        const mapping = isPlainObject(rawMapping) ? rawMapping : {};
        const syncKey = `${String(this.flowId ?? '')}--${String(this.nodeId ?? '')}--imap--${isMcp ? 'mcp-' : ''}${tab}`;
        return html`
            <div class="section">
                <div class="section-title">${this.t('base_node_editor.section_mapping')}</div>
                <div class="mapping-tabs">
                    <button class="mapping-tab" type="button" ?active=${tab === 'input'}
                        @click=${() => { this._mappingTab = 'input'; }}>
                        ${this.t('base_node_editor.tab_input')}
                    </button>
                    <button class="mapping-tab" type="button" ?active=${tab === 'output'}
                        @click=${() => { this._mappingTab = 'output'; }}>
                        ${this.t('base_node_editor.tab_output')}
                    </button>
                </div>
                <flows-state-mapping-editor
                    syncKey=${syncKey}
                    kind=${tab === 'input' ? 'input' : 'output'}
                    .mapping=${mapping}
                    @change=${(e) => this._onMapping(field, e)}
                ></flows-state-mapping-editor>
            </div>
        `;
    }

    _renderSettingsSlot() {
        return html`
            <div class="section">
                <slot name="settings"></slot>
            </div>
        `;
    }

    render() {
        if (!this.nodeConfig) return html`<div>${this.t('property_panel.select_node')}</div>`;
        if (this.expanded) {
            return html`
                <div class="panel-layout">
                    <div class="panel-sidebar">
                        ${this._renderBasic()}
                        ${this._renderResources()}
                        ${this._renderInputState()}
                    </div>
                    <div class="panel-main">
                        <div class="panel-run-fallback" data-node-run-fallback="expanded"></div>
                        ${this._renderSettingsSlot()}
                        ${this._renderMapping()}
                    </div>
                </div>
            `;
        }
        return html`
            <div class="compact">
                ${this._renderHeader()}
                ${this._renderBasic()}
                ${this._renderResources()}
                ${this._renderSettingsSlot()}
                ${this._renderMapping()}
                ${this._renderInputState()}
            </div>
        `;
    }
}

customElements.define('flows-base-node-editor', FlowsBaseNodeEditor);
