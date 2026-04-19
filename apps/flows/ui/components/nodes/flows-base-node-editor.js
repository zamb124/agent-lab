/**
 * flows-base-node-editor — общая обёртка редакторов нод.
 *
 * Раздел «Идентификация»:
 *   - node_id (read-only с переименованием через `flows/editor/node_id_changed`)
 *   - name, description, tags, incoming_policy
 *   - attached files (`node.files`)
 *   - attached resources (`node.resources`)
 *
 * Табы под идентификацией: Settings | Input | Output | Test.
 * Settings — slot 'settings' для type-specific редактора.
 * Input/Output — `<flows-state-mapping-editor>`.
 * Test — `<flows-test-panel>` с кнопкой Validate.
 *
 * Действия в шапке: Duplicate, Delete, Validate.
 *
 * Эмитит наружу `change { nodeId, patch }` — patch уже содержит изменённые
 * top-level поля `NodeConfig` (name, description, tags, incoming_policy,
 * files, resources). Type-specific патчи приходят через slot 'settings'.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import '../editors/flows-state-mapping-editor.js';
import '../editors/flows-test-panel.js';
import '../editors/flows-tag-input.js';

const TABS = ['settings', 'input', 'output', 'test'];

export class FlowsBaseNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        _tab: { state: true },
        _editingId: { state: true },
        _draftId: { state: true },
        _validateMessage: { state: true },
        _validateOk: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; padding: var(--space-3); color: var(--text-primary); }
            .header {
                display: flex; flex-direction: column; gap: var(--space-2);
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                margin-bottom: var(--space-3);
            }
            .row {
                display: flex; align-items: center; gap: var(--space-2);
                flex-wrap: wrap;
            }
            .badge {
                padding: 2px 8px; font-size: var(--text-xs);
                border-radius: var(--radius-full);
                background: var(--accent-subtle); color: var(--accent);
                white-space: nowrap;
            }
            .id {
                display: inline-flex; align-items: center; gap: 4px;
                padding: 2px 8px; font-size: var(--text-xs);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
                font-family: var(--font-mono, monospace);
            }
            .id button {
                background: none; border: none; padding: 0; margin: 0;
                color: var(--text-tertiary); cursor: pointer;
                display: inline-flex;
            }
            .id button:hover { color: var(--accent); }
            .actions { margin-left: auto; display: flex; gap: var(--space-1); }
            input.name {
                flex: 1; min-width: 0;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                font-weight: var(--font-semibold);
            }
            input.id-edit, input.text {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            input.id-edit { font-family: var(--font-mono, monospace); width: 240px; }
            textarea.desc {
                width: 100%; box-sizing: border-box;
                padding: var(--space-2); resize: vertical; min-height: 60px;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            .field { display: flex; flex-direction: column; gap: var(--space-1); }
            .field label { font-size: var(--text-sm); color: var(--text-secondary); }
            .grid {
                display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2);
            }
            select.policy {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            .files-list, .resources-list {
                display: flex; flex-direction: column; gap: var(--space-1);
            }
            .item-row {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-1) var(--space-2);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                font-size: var(--text-sm);
            }
            .item-row .grow { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .item-row .meta { color: var(--text-tertiary); font-size: var(--text-xs); }
            .item-row button {
                background: none; border: none; padding: 0; cursor: pointer;
                color: var(--text-tertiary);
            }
            .item-row button:hover { color: var(--error); }
            .empty {
                font-size: var(--text-xs); color: var(--text-tertiary);
                padding: var(--space-1) var(--space-2);
            }
            .add-row { display: flex; gap: var(--space-2); align-items: center; }
            .add-row select, .add-row input {
                flex: 1;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            .tabs {
                display: flex; gap: var(--space-1);
                border-bottom: 1px solid var(--border-subtle);
                margin-bottom: var(--space-3);
            }
            .tab {
                padding: var(--space-2) var(--space-3); cursor: pointer;
                border-bottom: 2px solid transparent;
                color: var(--text-secondary); font-size: var(--text-sm);
            }
            .tab[active] { border-color: var(--accent); color: var(--accent); }
            .validate-msg {
                padding: var(--space-2);
                border-radius: var(--radius-sm);
                font-size: var(--text-sm);
                margin-top: var(--space-2);
            }
            .validate-msg[ok] { background: var(--success-bg); color: var(--success); }
            .validate-msg[err] { background: var(--error-bg); color: var(--error); }
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
        this._tab = 'settings';
        this._editingId = false;
        this._draftId = '';
        this._validateMessage = '';
        this._validateOk = false;
        this._fileUpload = this.useOp('flows/file_upload');
        this._validate = this.useOp('flows/flow_validate');
        this._resources = this.useResource('flows/resources', { autoload: true });
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onName(e) {
        this._emitPatch({ name: e.target.value });
    }

    _onDescription(e) {
        this._emitPatch({ description: e.target.value });
    }

    _onTags(e) {
        const tags = Array.isArray(e.detail?.tags) ? e.detail.tags : [];
        this._emitPatch({ tags });
    }

    _onPolicy(e) {
        const v = e.target.value === 'all' ? 'all' : 'any';
        this._emitPatch({ incoming_policy: v });
    }

    _onMapping(field, e) {
        this._emitPatch({ [field]: e.detail?.mapping || {} });
    }

    _startRenameId() {
        this._editingId = true;
        this._draftId = this.nodeId;
    }

    _commitRenameId() {
        const draft = (this._draftId || '').trim();
        this._editingId = false;
        if (!draft || draft === this.nodeId) return;
        if (!/^[a-zA-Z0-9_]+$/.test(draft)) {
            this.toast('flows:base_node_editor.rename_invalid', { type: 'error' });
            return;
        }
        this.emit('rename-node', { oldId: this.nodeId, newId: draft });
    }

    _cancelRenameId() {
        this._editingId = false;
    }

    _onDuplicate() {
        this.emit('duplicate-node', { nodeId: this.nodeId });
    }

    _onDelete() {
        this.emit('delete-node', { nodeId: this.nodeId });
    }

    async _onValidate() {
        const result = await this._validate.run({ flow_id: this.flowId });
        const errors = result && Array.isArray(result.errors) ? result.errors : [];
        const myErrors = errors.filter((er) => er && er.node_id === this.nodeId);
        if (myErrors.length === 0) {
            this._validateOk = true;
            this._validateMessage = this.t('base_node_editor.validate_ok');
        } else {
            this._validateOk = false;
            this._validateMessage = myErrors.map((er) => er.message || JSON.stringify(er)).join('; ');
        }
    }

    async _onUploadFile(e) {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        const result = await this._fileUpload.run({ file });
        if (!result || typeof result.file_id !== 'string') return;
        const files = Array.isArray(this.nodeConfig?.files) ? this.nodeConfig.files : [];
        const next = [...files, {
            file_id: result.file_id,
            name: result.name || file.name,
            mime_type: result.mime_type || file.type,
        }];
        this._emitPatch({ files: next });
        e.target.value = '';
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

    _renderIdentification() {
        const cfg = this.nodeConfig;
        const name = typeof cfg?.name === 'string' ? cfg.name : '';
        const description = typeof cfg?.description === 'string' ? cfg.description : '';
        const tags = Array.isArray(cfg?.tags) ? cfg.tags : [];
        const policy = cfg?.incoming_policy === 'all' ? 'all' : 'any';
        const files = Array.isArray(cfg?.files) ? cfg.files : [];
        const resources = cfg?.resources && typeof cfg.resources === 'object' ? cfg.resources : {};
        const allResources = Array.isArray(this._resources.items) ? this._resources.items : [];
        const availableResources = allResources.filter((r) => r && !resources[r.resource_id]);
        return html`
            <div class="header">
                <div class="row">
                    <input
                        class="name" type="text"
                        placeholder=${this.t('base_node_editor.name')}
                        .value=${name}
                        @input=${this._onName}
                    />
                    <span class="badge">${this.nodeType}</span>
                    <div class="actions">
                        <glass-button size="sm" variant="ghost" @click=${this._onValidate} title=${this.t('base_node_editor.action_validate')}>
                            <platform-icon name="check"></platform-icon>
                        </glass-button>
                        <glass-button size="sm" variant="ghost" @click=${this._onDuplicate} title=${this.t('base_node_editor.action_duplicate')}>
                            <platform-icon name="copy"></platform-icon>
                        </glass-button>
                        <glass-button size="sm" variant="ghost" @click=${this._onDelete} title=${this.t('base_node_editor.action_delete')}>
                            <platform-icon name="trash"></platform-icon>
                        </glass-button>
                    </div>
                </div>
                <div class="row">
                    ${this._editingId ? html`
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
                    ` : html`
                        <span class="id">
                            ${this.nodeId}
                            <button title=${this.t('base_node_editor.rename_id')} @click=${this._startRenameId}>
                                <platform-icon name="edit" size="xs"></platform-icon>
                            </button>
                        </span>
                    `}
                </div>
                <div class="field">
                    <label>${this.t('base_node_editor.description')}</label>
                    <textarea
                        class="desc"
                        placeholder=${this.t('base_node_editor.description_hint')}
                        .value=${description}
                        @input=${this._onDescription}
                    ></textarea>
                </div>
                <div class="grid">
                    <div class="field">
                        <label>${this.t('base_node_editor.tags')}</label>
                        <flows-tag-input
                            .tags=${tags}
                            placeholder=${this.t('tag_input.placeholder')}
                            @change=${this._onTags}
                        ></flows-tag-input>
                    </div>
                    <div class="field">
                        <label>${this.t('base_node_editor.incoming_policy')}</label>
                        <select class="policy" .value=${policy} @change=${this._onPolicy}>
                            <option value="any" ?selected=${policy === 'any'}>${this.t('base_node_editor.incoming_policy_any')}</option>
                            <option value="all" ?selected=${policy === 'all'}>${this.t('base_node_editor.incoming_policy_all')}</option>
                        </select>
                    </div>
                </div>
                <div class="field">
                    <label>${this.t('base_node_editor.files_section')}</label>
                    ${files.length === 0
                        ? html`<div class="empty">${this.t('base_node_editor.files_empty')}</div>`
                        : html`<div class="files-list">
                            ${files.map((f, i) => html`
                                <div class="item-row">
                                    <span class="grow">${f.name || f.file_id}</span>
                                    <span class="meta">${f.mime_type || ''}</span>
                                    <button title=${this.t('base_node_editor.files_remove')} @click=${() => this._onRemoveFile(i)}>
                                        <platform-icon name="trash" size="xs"></platform-icon>
                                    </button>
                                </div>
                            `)}
                        </div>`}
                    <label class="add-row">
                        <input type="file" @change=${this._onUploadFile} ?disabled=${this._fileUpload.busy} />
                    </label>
                </div>
                <div class="field">
                    <label>${this.t('base_node_editor.resources_section')}</label>
                    ${Object.keys(resources).length === 0
                        ? html`<div class="empty">${this.t('base_node_editor.resources_empty')}</div>`
                        : html`<div class="resources-list">
                            ${Object.entries(resources).map(([key, ref]) => {
                                const def = allResources.find((r) => r && r.resource_id === (ref?.resource_id || key));
                                return html`
                                    <div class="item-row">
                                        <span class="grow">${def ? def.name : key}</span>
                                        <span class="meta">${def ? def.type : ''}</span>
                                        <button title=${this.t('base_node_editor.resources_remove')} @click=${() => this._onRemoveResource(key)}>
                                            <platform-icon name="trash" size="xs"></platform-icon>
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
                ${this._validateMessage ? html`
                    <div class="validate-msg" ?ok=${this._validateOk} ?err=${!this._validateOk}>
                        ${this._validateMessage}
                    </div>
                ` : ''}
            </div>
        `;
    }

    _renderTab() {
        if (this._tab === 'settings') {
            return html`<slot name="settings"></slot>`;
        }
        if (this._tab === 'input') {
            return html`
                <flows-state-mapping-editor
                    .mapping=${this.nodeConfig?.input_mapping || {}}
                    @change=${(e) => this._onMapping('input_mapping', e)}
                ></flows-state-mapping-editor>
            `;
        }
        if (this._tab === 'output') {
            return html`
                <flows-state-mapping-editor
                    .mapping=${this.nodeConfig?.output_mapping || {}}
                    @change=${(e) => this._onMapping('output_mapping', e)}
                ></flows-state-mapping-editor>
            `;
        }
        return html`
            <flows-test-panel
                .nodeType=${this.nodeType}
                .nodeConfig=${this.nodeConfig || {}}
                .flowId=${this.flowId}
                .skillId=${this.skillId || 'base'}
                .previewExecutionState=${this.previewExecutionState}
            ></flows-test-panel>
        `;
    }

    render() {
        if (!this.nodeConfig) return html`<div>${this.t('property_panel.select_node')}</div>`;
        return html`
            ${this._renderIdentification()}
            <div class="tabs">
                ${TABS.map((t) => html`
                    <div class="tab" ?active=${this._tab === t} @click=${() => { this._tab = t; }}>
                        ${this.t(`base_node_editor.tab_${t}`)}
                    </div>
                `)}
            </div>
            <div class="body">${this._renderTab()}</div>
        `;
    }
}

customElements.define('flows-base-node-editor', FlowsBaseNodeEditor);
