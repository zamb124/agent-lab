/**
 * flows-mcp-node-editor — редактор MCP-ноды.
 *
 * Поля по `MCPNode` (apps/flows/src/runtime/nodes.py):
 *   - server_id, tool_name, headers; input_mapping и state_mapping — в `flows-base-node-editor` (МАППИНГ Вход/Выход).
 *
 * `cached_tools` в API — полные `mcp:server:tool_id`; в конфиге `tool_name` — короткое имя.
 * Схема аргументов и драфт `input_mapping` — из GET /flows/api/v1/tools/{tool_id} (`flows/tools`).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-node-editor.js';
import '../editors/flows-json-field-editor.js';
import '../editors/flows-args-schema-form.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';
import {
    fullMcpToolId,
    mcpInputMappingDraftFromToolRecord,
    shortMcpNameFromCacheEntry,
} from '../../_helpers/flows-mcp-tool-registry.js';

export class FlowsMcpNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        expanded: { type: Boolean, reflect: true },
        embedded: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                height: 100%;
                min-height: 0;
            }
            details {
                margin-bottom: var(--space-3);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            summary { cursor: pointer; font-size: var(--text-sm); font-weight: var(--font-semibold); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-2); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input, select {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
            .row { display: flex; align-items: center; gap: var(--space-2); }
            .row > select, .row > input { flex: 1; }
            .mcp-control-row {
                display: grid;
                grid-template-columns: minmax(180px, 0.55fr) minmax(260px, 1fr) auto;
                align-items: end;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
            .mcp-control-row platform-field {
                min-width: 0;
            }
            .mcp-sync-button {
                min-height: 40px;
                white-space: nowrap;
            }
            .mcp-hint { font-size: var(--text-xs); color: var(--text-tertiary); margin: 0 0 var(--space-2) 0; line-height: 1.4; }
            @media (max-width: 900px) {
                .mcp-control-row {
                    grid-template-columns: minmax(0, 1fr);
                    align-items: stretch;
                }
                .mcp-sync-button {
                    justify-self: start;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = 'mcp';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.expanded = false;
        this.embedded = false;
        this._servers = this.useResource('flows/mcp_servers', { autoload: true });
        this._tools = this.useResource('flows/tools', { autoload: false });
        this._sync = this.useOp('flows/mcp_server_sync');
        this._mcpGetPending = null;
        this._draftGenFullId = null;
        this._prevInputMappingKeyCount = 0;
        this.useEvent('flows/tools/item_loaded', (ev) => {
            if (!ev || !isPlainObject(ev.payload) || !isPlainObject(ev.payload.item)) {
                return;
            }
            const loadedId = ev.payload.item.tool_id;
            if (typeof loadedId !== 'string' || loadedId.length === 0) {
                return;
            }
            const b = this._mcpFieldBundle();
            if (b.serverId.length === 0 || b.toolName.length === 0) {
                return;
            }
            if (loadedId !== fullMcpToolId(b.serverId, b.toolName)) {
                return;
            }
            this._applyMcpToolFetchAndDraft();
        });
    }

    updated() {
        super.updated();
        this._mcpFlattenLegacyNested();
        this._applyMcpToolFetchAndDraft();
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    /**
     * Рантайм и API ожидают server_id / tool_name на корне ноды.
     * Ранее дроп писал их во вложенный `config` — смотрим оба варианта.
     */
    _mcpFieldBundle() {
        const o = asObject(this.nodeConfig);
        const nest = isPlainObject(o.config) ? o.config : null;
        let serverId = '';
        if (typeof o.server_id === 'string' && o.server_id.length > 0) {
            serverId = o.server_id;
        } else if (typeof o.mcp_server_id === 'string' && o.mcp_server_id.length > 0) {
            serverId = o.mcp_server_id;
        } else if (nest && typeof nest.server_id === 'string' && nest.server_id.length > 0) {
            serverId = nest.server_id;
        } else if (nest && typeof nest.mcp_server_id === 'string' && nest.mcp_server_id.length > 0) {
            serverId = nest.mcp_server_id;
        }
        let toolName = '';
        if (typeof o.tool_name === 'string' && o.tool_name.length > 0) {
            toolName = o.tool_name;
        } else if (typeof o.mcp_tool_name === 'string' && o.mcp_tool_name.length > 0) {
            toolName = o.mcp_tool_name;
        } else if (nest && typeof nest.tool_name === 'string' && nest.tool_name.length > 0) {
            toolName = nest.tool_name;
        } else if (nest && typeof nest.mcp_tool_name === 'string' && nest.mcp_tool_name.length > 0) {
            toolName = nest.mcp_tool_name;
        }
        let headers;
        if (isPlainObject(o.headers)) {
            headers = o.headers;
        } else if (nest && isPlainObject(nest.headers)) {
            headers = nest.headers;
        } else {
            headers = {};
        }
        let stateMapping;
        if (isPlainObject(o.state_mapping)) {
            stateMapping = o.state_mapping;
        } else if (nest && isPlainObject(nest.state_mapping)) {
            stateMapping = nest.state_mapping;
        } else {
            stateMapping = {};
        }
        let inputMapping;
        if (isPlainObject(o.input_mapping)) {
            inputMapping = o.input_mapping;
        } else if (nest && isPlainObject(nest.input_mapping)) {
            inputMapping = nest.input_mapping;
        } else {
            inputMapping = undefined;
        }
        return {
            serverId,
            toolName,
            headers,
            stateMapping,
            inputMapping,
        };
    }

    _mergedNodeForBase() {
        const o = asObject(this.nodeConfig);
        const b = this._mcpFieldBundle();
        return {
            ...o,
            server_id: b.serverId,
            tool_name: b.toolName,
            headers: b.headers,
            state_mapping: b.stateMapping,
            input_mapping: b.inputMapping,
        };
    }

    /**
     * Прямой ключ в byId (как в fetch) или совпадение item.tool_id — на случай
     * различий строки id в store и fullMcpToolId с ноды.
     */
    _findToolRecordInStore(wantId) {
        if (typeof wantId !== 'string' || wantId.length === 0) {
            return null;
        }
        const byId = isPlainObject(this._tools.byId) ? this._tools.byId : {};
        if (isPlainObject(byId[wantId])) {
            return byId[wantId];
        }
        const keys = Object.keys(byId);
        for (let i = 0; i < keys.length; i += 1) {
            const it = byId[keys[i]];
            if (isPlainObject(it) && it.tool_id === wantId) {
                return it;
            }
        }
        return null;
    }

    _mcpFlattenLegacyNested() {
        const o = asObject(this.nodeConfig);
        if (typeof o.server_id === 'string' && o.server_id.length > 0) {
            return;
        }
        const nest = isPlainObject(o.config) ? o.config : null;
        if (!nest) {
            return;
        }
        if (typeof nest.server_id !== 'string' || nest.server_id.length === 0) {
            return;
        }
        if (typeof nest.tool_name !== 'string' || nest.tool_name.length === 0) {
            return;
        }
        const b = this._mcpFieldBundle();
        this._emitPatch({
            server_id: b.serverId,
            tool_name: b.toolName,
            headers: b.headers,
            state_mapping: b.stateMapping,
            input_mapping: b.inputMapping,
            config: {},
        });
    }

    _applyMcpToolFetchAndDraft() {
        const b = this._mcpFieldBundle();
        const im = b.inputMapping;
        const imKeyCount = isPlainObject(im) ? Object.keys(im).length : 0;
        if (this._prevInputMappingKeyCount > 0 && imKeyCount === 0) {
            this._draftGenFullId = null;
        }
        this._prevInputMappingKeyCount = imKeyCount;
        const serverId = b.serverId;
        const toolName = b.toolName;
        if (serverId.length === 0 || toolName.length === 0) {
            this._mcpGetPending = null;
            return;
        }
        const fullId = fullMcpToolId(serverId, toolName);
        const item = this._findToolRecordInStore(fullId);
        if (item === null) {
            if (this._mcpGetPending !== fullId) {
                this._mcpGetPending = fullId;
                void this._tools.get(fullId);
            }
            return;
        }
        this._mcpGetPending = null;
        const mappingEmpty = imKeyCount === 0;
        if (!mappingEmpty) {
            this._draftGenFullId = null;
            return;
        }
        if (this._draftGenFullId === fullId) {
            return;
        }
        const draft = mcpInputMappingDraftFromToolRecord(item);
        if (Object.keys(draft).length === 0) {
            this._draftGenFullId = fullId;
            return;
        }
        this._draftGenFullId = fullId;
        queueMicrotask(() => {
            this._emitPatch({ input_mapping: draft });
        });
    }

    _onServer(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-mcp-node-editor: server_id change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-mcp-node-editor: server_id detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-mcp-node-editor: server_id string required');
        }
        this._draftGenFullId = null;
        this._emitPatch({ server_id: v, tool_name: '' });
    }

    _onTool(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-mcp-node-editor: tool_name change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-mcp-node-editor: tool_name detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-mcp-node-editor: tool_name string required');
        }
        this._draftGenFullId = null;
        this._emitPatch({ tool_name: v });
    }

    _onHeaders(parsed) {
        this._emitPatch({ headers: parsed && typeof parsed === 'object' ? parsed : {} });
    }

    async _onSync(serverId) {
        if (!serverId) return;
        await this._sync.run({ server_id: serverId });
    }

    _findServer(servers, id) {
        const found = servers.find((s) => s && s.server_id === id);
        return found ? found : null;
    }

    _toolOptions(server, serverId) {
        if (!server || !Array.isArray(server.cached_tools)) {
            return [];
        }
        const byId = isPlainObject(this._tools.byId) ? this._tools.byId : {};
        return server.cached_tools.map((entry) => {
            if (typeof entry === 'string') {
                if (!entry.startsWith('mcp:')) {
                    throw new Error('flows-mcp-node-editor: cached_tools entry must be mcp:… id');
                }
                const short = shortMcpNameFromCacheEntry(entry, serverId);
                if (short === null) {
                    return null;
                }
                const rec = isPlainObject(byId[entry]) ? byId[entry] : null;
                const label = rec && typeof rec.title === 'string' && rec.title.length > 0
                    ? rec.title
                    : short;
                return { value: short, label, fullId: entry };
            }
            if (isPlainObject(entry) && typeof entry.name === 'string' && entry.name.length > 0) {
                const fullId = fullMcpToolId(serverId, entry.name);
                const rec = isPlainObject(byId[fullId]) ? byId[fullId] : null;
                const label = (rec && typeof rec.title === 'string' && rec.title.length > 0)
                    ? rec.title
                    : (typeof entry.title === 'string' && entry.title.length > 0 ? entry.title : entry.name);
                return { value: entry.name, label, fullId };
            }
            throw new Error('flows-mcp-node-editor: unsupported cached_tools entry shape');
        }).filter((x) => x !== null);
    }

    _toolSchema(tool) {
        if (!tool || typeof tool !== 'object') return null;
        if (tool.args_schema && typeof tool.args_schema === 'object' && Object.keys(tool.args_schema).length > 0) {
            return tool.args_schema;
        }
        if (tool.parameters_schema && typeof tool.parameters_schema === 'object'
            && tool.parameters_schema.properties && typeof tool.parameters_schema.properties === 'object') {
            return tool.parameters_schema.properties;
        }
        return null;
    }

    _resolveLoadedToolRecord(serverId, toolName) {
        if (typeof serverId !== 'string' || serverId.length === 0) {
            return null;
        }
        if (typeof toolName !== 'string' || toolName.length === 0) {
            return null;
        }
        const rec = this._findToolRecordInStore(fullMcpToolId(serverId, toolName));
        return isPlainObject(rec) ? rec : null;
    }

    render() {
        const b = this._mcpFieldBundle();
        const serverId = b.serverId;
        const toolName = b.toolName;
        const servers = Array.isArray(this._servers.items) ? this._servers.items : [];
        const server = this._findServer(servers, serverId);
        const toolOptions = this._toolOptions(server, serverId);
        const loaded = this._resolveLoadedToolRecord(serverId, toolName);
        const schema = this._toolSchema(loaded);
        const headersJson = JSON.stringify(b.headers, null, 2);
        const serverValues = [
            { value: '', label: '—' },
            ...servers.map((s) => ({ value: s.server_id, label: s.name })),
        ];
        const toolValues = [
            { value: '', label: '—' },
            ...toolOptions.map((o) => ({ value: o.value, label: o.label })),
        ];
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this._mergedNodeForBase()}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'mcp'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
                @change=${(e) => this.emit('change', e.detail)}
                @delete-node=${(e) => this.emit('delete-node', e.detail)}
                @duplicate-node=${(e) => this.emit('duplicate-node', e.detail)}
            >
                <div slot="settings">
                    <p class="mcp-hint">${this.t('mcp_node_editor.input_mapping_hint')}</p>
                    <div class="mcp-control-row">
                        <platform-field
                            mode="edit"
                            type="enum"
                            .label=${this.t('mcp_node_editor.server_id')}
                            .value=${serverId}
                            .config=${{ values: serverValues }}
                            @change=${this._onServer}
                        ></platform-field>
                        <platform-field
                            mode="edit"
                            type="enum"
                            .label=${this.t('mcp_node_editor.tool_name')}
                            .value=${toolName}
                            .config=${{ values: toolValues }}
                            @change=${this._onTool}
                        ></platform-field>
                        <glass-button
                            class="mcp-sync-button"
                            size="sm"
                            variant="ghost"
                            ?disabled=${!serverId || this._sync.busy}
                            @click=${() => this._onSync(serverId)}
                        >
                            <platform-icon name="refresh"></platform-icon>
                            ${this.t('mcp_node_editor.sync_server')}
                        </glass-button>
                    </div>
                    ${schema ? html`
                        <details>
                            <summary>${this.t('mcp_node_editor.args_preview')}</summary>
                            <flows-args-schema-form
                                .schema=${schema}
                                .values=${{}}
                                ?readonly=${true}
                            ></flows-args-schema-form>
                        </details>
                    ` : ''}
                    <details>
                        <summary>${this.t('mcp_node_editor.headers')}</summary>
                        <flows-json-field-editor
                            .value=${headersJson}
                            @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._onHeaders(e.detail.parsed); }}
                        ></flows-json-field-editor>
                    </details>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-mcp-node-editor', FlowsMcpNodeEditor);
