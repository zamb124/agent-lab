/**
 * flows-mcp-node-editor — редактор MCP-ноды.
 *
 * Поля по `MCPNode` (apps/flows/src/runtime/nodes.py):
 *   - server_id, tool_name, headers; input_mapping и state_mapping — в `flows-base-node-editor` (МАППИНГ Вход/Выход).
 *
 * Выбор tool — тот же `flows.tool_picker` (`pickMode: mcp_only`), что и при дропе MCP на canvas.
 * `cached_tools` в API — полные `mcp:server:tool_id`; в конфиге `tool_name` — короткое имя.
 * Схема аргументов и драфт `input_mapping` — из GET /flows/api/v1/tools/{tool_id} (`flows/tools`).
 */

import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-http-headers-editor.js';
import '../editors/flows-parameters-schema-form.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';
import {
    fullMcpToolId,
    mcpInputMappingDraftFromToolRecord,
    parseMcpToolIdToNodeConfig,
} from '../../_helpers/flows-mcp-tool-registry.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsMcpNodeEditor extends PlatformElement {
    static override properties: PropertyDeclarations = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        dataflowNode: { type: Object },
        embedded: { type: Boolean, reflect: true },
    }
    declare nodeId: string;
    declare flowId: string;
    declare branchId: string;
    declare nodeConfig: Record<string, any> | null;
    declare nodeType: any;
    declare flowVariables: Record<string, any> | null;
    declare graphNodes: any[] | null;
    declare previewExecutionState: Record<string, any> | null;
    declare dataflowNode: Record<string, any> | null;
    declare embedded: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        glassStyles,
        css`
            :host {
                display: block;
                height: 100%;
                min-height: 0;
            }
            details {
                margin-bottom: var(--space-3);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
            }
            summary { cursor: pointer; font-size: var(--text-sm); font-weight: var(--font-semibold); }
            .mcp-control-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
            .mcp-selection {
                flex: 1 1 220px;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--bg-elevated);
            }
            .mcp-selection-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .mcp-selection-value {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: var(--font-medium);
                word-break: break-word;
            }
            .mcp-selection-value[data-empty='true'] {
                color: var(--text-tertiary);
                font-weight: var(--font-normal);
            }
            .mcp-selection-meta {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                font-family: var(--font-mono);
            }
            .mcp-actions {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
            }
            .mcp-sync-button {
                min-height: 40px;
                white-space: nowrap;
            }
            .mcp-hint { font-size: var(--text-xs); color: var(--text-tertiary); margin: 0 0 var(--space-2) 0; line-height: 1.4; }
        `,
    ];
    private _servers: ResourceController;
    private _tools: ResourceController;
    private _sync: OpController;
    private _mcpGetPending: any;
    private _draftGenFullId: any;
    private _prevInputMappingKeyCount: number;

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
        this.dataflowNode = null;
        this.embedded = false;
        this._servers = this.useResource('flows/mcp_servers', { autoload: true });
        this._tools = this.useResource('flows/tools', { autoload: false });
        this._sync = this.useOp('flows/mcp_server_sync');
        this._mcpGetPending = null;
        this._draftGenFullId = null;
        this._prevInputMappingKeyCount = 0;
        this.useEvent('flows/tools/item_loaded', (ev) => {
            if (!ev || !isPlainObject(ev.payload) || !isPlainObject((ev as any).payload.item)) {
                return;
            }
            const loadedId = (ev as any).payload.item.tool_id;
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

    override updated(changed: any) {
        super.updated(changed);
        this._mcpFlattenLegacyNested();
        this._applyMcpToolFetchAndDraft();
    }

    _emitPatch(patch: any) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    /**
     * Рантайм и API ожидают server_id / tool_name на корне ноды.
     * Ранее дроп писал их во вложенный `config` — смотрим оба варианта.
     */
    _mcpFieldBundle() {
        const o = asObject(this.nodeConfig);
        const nest = isPlainObject((o as any).config) ? (o as any).config : null;
        let serverId = '';
        if (typeof (o as any).server_id === 'string' && (o as any).server_id.length > 0) {
            serverId = (o as any).server_id;
        } else if (typeof (o as any).mcp_server_id === 'string' && (o as any).mcp_server_id.length > 0) {
            serverId = (o as any).mcp_server_id;
        } else if (nest && typeof nest.server_id === 'string' && nest.server_id.length > 0) {
            serverId = nest.server_id;
        } else if (nest && typeof nest.mcp_server_id === 'string' && nest.mcp_server_id.length > 0) {
            serverId = nest.mcp_server_id;
        }
        let toolName = '';
        if (typeof (o as any).tool_name === 'string' && (o as any).tool_name.length > 0) {
            toolName = (o as any).tool_name;
        } else if (typeof (o as any).mcp_tool_name === 'string' && (o as any).mcp_tool_name.length > 0) {
            toolName = (o as any).mcp_tool_name;
        } else if (nest && typeof nest.tool_name === 'string' && nest.tool_name.length > 0) {
            toolName = nest.tool_name;
        } else if (nest && typeof nest.mcp_tool_name === 'string' && nest.mcp_tool_name.length > 0) {
            toolName = nest.mcp_tool_name;
        }
        let headers;
        if (isPlainObject((o as any).headers)) {
            headers = (o as any).headers;
        } else if (nest && isPlainObject(nest.headers)) {
            headers = nest.headers;
        } else {
            headers = {};
        }
        let stateMapping;
        if (isPlainObject((o as any).state_mapping)) {
            stateMapping = (o as any).state_mapping;
        } else if (nest && isPlainObject(nest.state_mapping)) {
            stateMapping = nest.state_mapping;
        } else {
            stateMapping = {};
        }
        let inputMapping;
        if (isPlainObject((o as any).input_mapping)) {
            inputMapping = (o as any).input_mapping;
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
            ...(o as Record<string, any>),
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
    _findToolRecordInStore(wantId: any) {
        if (typeof wantId !== 'string' || wantId.length === 0) {
            return null;
        }
        const byId = isPlainObject(this._tools.byId) ? this._tools.byId : {};
        if (isPlainObject(byId[wantId])) {
            return byId[wantId];
        }
        const keys = Object.keys(byId);
        for (let i = 0; i < keys.length; i += 1) {
            const key = keys[i];
            if (key === undefined) {
                throw new Error('flows-mcp-node-editor: tool key missing');
            }
            const it = byId[key];
            if (isPlainObject(it) && it.tool_id === wantId) {
                return it;
            }
        }
        return null;
    }

    _mcpFlattenLegacyNested() {
        const o = asObject(this.nodeConfig);
        if (typeof (o as any).server_id === 'string' && (o as any).server_id.length > 0) {
            return;
        }
        const nest = isPlainObject((o as any).config) ? (o as any).config : null;
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

    _onHeaders(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d)) {
            throw new Error('flows-mcp-node-editor: headers change detail.value');
        }
        const headers = d.value;
        if (!headers || typeof headers !== 'object' || Array.isArray(headers)) {
            throw new Error('flows-mcp-node-editor: headers must be an object');
        }
        this._emitPatch({ headers });
    }

    async _onSync(serverId: any) {
        if (!serverId) return;
        await this._sync.run({ server_id: serverId });
    }

    _findServer(servers: any, id: string) {
        const found = servers.find((s: any) => s && s.server_id === id);
        return found ? found : null;
    }

    _onPickTool() {
        this.openModal('flows.tool_picker', {
            pickMode: 'mcp_only',
            onPick: (detail: any) => {
                if (!detail || typeof detail !== 'object') {
                    return;
                }
                if (detail.kind !== 'tool') {
                    return;
                }
                const toolId = detail.tool_id;
                if (typeof toolId !== 'string' || toolId.length === 0) {
                    return;
                }
                const parsed = parseMcpToolIdToNodeConfig(toolId);
                this._draftGenFullId = null;
                this._emitPatch({
                    server_id: parsed.server_id,
                    tool_name: parsed.tool_name,
                });
            },
        });
    }

    _toolSchema(tool: any) {
        if (!tool || typeof tool !== 'object') return null;
        if (tool.parameters_schema && typeof tool.parameters_schema === 'object'
            && tool.parameters_schema.properties && typeof tool.parameters_schema.properties === 'object') {
            return tool.parameters_schema.properties;
        }
        return null;
    }

    _resolveLoadedToolRecord(serverId: any, toolName: any) {
        if (typeof serverId !== 'string' || serverId.length === 0) {
            return null;
        }
        if (typeof toolName !== 'string' || toolName.length === 0) {
            return null;
        }
        const rec = this._findToolRecordInStore(fullMcpToolId(serverId, toolName));
        return isPlainObject(rec) ? rec : null;
    }

    _selectionLabel(server: any, serverId: any, toolName: any, loaded: any) {
        if (serverId.length === 0 || toolName.length === 0) {
            return this.t('mcp_node_editor.tool_not_selected');
        }
        const toolTitle = loaded && typeof loaded.title === 'string' && loaded.title.length > 0
            ? loaded.title
            : toolName;
        const serverLabel = server && typeof server.name === 'string' && server.name.length > 0
            ? server.name
            : serverId;
        return `${serverLabel} · ${toolTitle}`;
    }

    override render(): TemplateResult {
        const b = this._mcpFieldBundle();
        const serverId = b.serverId;
        const toolName = b.toolName;
        const servers = Array.isArray(this._servers.items) ? this._servers.items : [];
        const server = this._findServer(servers, serverId);
        const loaded = this._resolveLoadedToolRecord(serverId, toolName);
        const schema = this._toolSchema(loaded);
        const headers =
            b.headers && typeof b.headers === 'object' && !Array.isArray(b.headers)
                ? b.headers
                : {};
        const hasSelection = serverId.length > 0 && toolName.length > 0;
        const selectionLabel = this._selectionLabel(server, serverId, toolName, loaded);
        const fullId = hasSelection ? fullMcpToolId(serverId, toolName) : '';
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
                .dataflowNode=${this.dataflowNode}
                ?embedded=${this.embedded}
                @change=${(e: CustomEvent) => this.emit('change', e.detail)}
                @delete-node=${(e: CustomEvent) => this.emit('delete-node', e.detail)}
                @duplicate-node=${(e: CustomEvent) => this.emit('duplicate-node', e.detail)}
            >
                <div slot="settings">
                    <p class="mcp-hint">${this.t('mcp_node_editor.input_mapping_hint')}</p>
                    <div class="mcp-control-row">
                        <div class="mcp-selection">
                            <span class="mcp-selection-label">${this.t('mcp_node_editor.selected_tool')}</span>
                            <span class="mcp-selection-value" data-empty=${hasSelection ? 'false' : 'true'}>
                                ${selectionLabel}
                            </span>
                            ${fullId.length > 0
                                ? html`<span class="mcp-selection-meta">${fullId}</span>`
                                : ''}
                        </div>
                        <div class="mcp-actions">
                            <platform-button
                                variant="secondary"
                                density="compact"
                                @click=${() => this._onPickTool()}
                            >
                                <platform-icon name="plus"></platform-icon>
                                ${this.t('mcp_node_editor.pick_tool')}
                            </platform-button>
                            <platform-button
                                class="mcp-sync-button"
                                variant="ghost"
                                density="compact"
                                ?disabled=${!serverId || this._sync.busy}
                                @click=${() => this._onSync(serverId)}
                            >
                                <platform-icon name="refresh"></platform-icon>
                                ${this.t('mcp_node_editor.sync_server')}
                            </platform-button>
                        </div>
                    </div>
                    ${schema ? html`
                        <details class="glass-subtle">
                            <summary>${this.t('mcp_node_editor.args_preview')}</summary>
                            <flows-parameters-schema-form
                                .schema=${schema}
                                .values=${{}}
                                ?readonly=${true}
                            ></flows-parameters-schema-form>
                        </details>
                    ` : ''}
                    <details class="glass-subtle" open>
                        <summary>${this.t('mcp_node_editor.headers')}</summary>
                        <flows-http-headers-editor
                            .value=${headers}
                            @change=${this._onHeaders}
                        ></flows-http-headers-editor>
                    </details>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-mcp-node-editor', FlowsMcpNodeEditor);
