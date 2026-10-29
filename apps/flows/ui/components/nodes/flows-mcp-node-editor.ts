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
import type { PropertyValues } from 'lit';
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
        flowNodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        dataflowNode: { type: Object },
        embedded: { type: Boolean, reflect: true },
    }
    declare nodeId: string;
    declare flowId: string;
    declare branchId: string;
    declare nodeConfig: Record<string, unknown> | null;
    declare flowNodeType: string;
    declare flowVariables: Record<string, unknown> | null;
    declare graphNodes: unknown[] | null;
    declare previewExecutionState: Record<string, unknown> | null;
    declare dataflowNode: Record<string, unknown> | null;
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
    private _mcpGetPending: string | null;
    private _draftGenFullId: string | null;
    private _prevInputMappingKeyCount: number;

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.flowNodeType = 'mcp';
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
            if (!ev || !isPlainObject(ev.payload) || !isPlainObject((ev).payload.item)) {
                return;
            }
            const loadedId = (ev).payload.item.tool_id;
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

    override updated(changed: PropertyValues<this>) {
        super.updated(changed);
        this._mcpFlattenLegacyNested();
        this._applyMcpToolFetchAndDraft();
    }

    _emitPatch(patch: Record<string, unknown>) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    /**
     * Рантайм и API ожидают server_id / tool_name на корне ноды.
     * Ранее дроп писал их во вложенный `config` — смотрим оба варианта.
     */
    _mcpFieldBundle() {
        const o = asObject(this.nodeConfig);
        const nest = isPlainObject((o).config) ? (o).config : null;
        let serverId = '';
        if (typeof (o).server_id === 'string' && (o).server_id.length > 0) {
            serverId = (o).server_id;
        } else if (typeof (o).mcp_server_id === 'string' && (o).mcp_server_id.length > 0) {
            serverId = (o).mcp_server_id;
        } else if (nest && typeof nest.server_id === 'string' && nest.server_id.length > 0) {
            serverId = nest.server_id;
        } else if (nest && typeof nest.mcp_server_id === 'string' && nest.mcp_server_id.length > 0) {
            serverId = nest.mcp_server_id;
        }
        let toolName = '';
        if (typeof (o).tool_name === 'string' && (o).tool_name.length > 0) {
            toolName = (o).tool_name;
        } else if (typeof (o).mcp_tool_name === 'string' && (o).mcp_tool_name.length > 0) {
            toolName = (o).mcp_tool_name;
        } else if (nest && typeof nest.tool_name === 'string' && nest.tool_name.length > 0) {
            toolName = nest.tool_name;
        } else if (nest && typeof nest.mcp_tool_name === 'string' && nest.mcp_tool_name.length > 0) {
            toolName = nest.mcp_tool_name;
        }
        let headers;
        if (isPlainObject((o).headers)) {
            headers = (o).headers;
        } else if (nest && isPlainObject(nest.headers)) {
            headers = nest.headers;
        } else {
            headers = {};
        }
        let stateMapping;
        if (isPlainObject((o).state_mapping)) {
            stateMapping = (o).state_mapping;
        } else if (nest && isPlainObject(nest.state_mapping)) {
            stateMapping = nest.state_mapping;
        } else {
            stateMapping = {};
        }
        let inputMapping;
        if (isPlainObject((o).input_mapping)) {
            inputMapping = (o).input_mapping;
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
    _findToolRecordInStore(wantId: unknown) {
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
        if (typeof (o).server_id === 'string' && (o).server_id.length > 0) {
            return;
        }
        const nest = isPlainObject((o).config) ? (o).config : null;
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

    async _onSync(serverId: string) {
        if (!serverId) return;
        await this._sync.run({ server_id: serverId });
    }

    _findServer(servers: readonly unknown[], id: string) {
        const found = servers.find((server) => isPlainObject(server) && server.server_id === id);
        return found ? found : null;
    }

    _onPickTool() {
        this.openModal('flows.tool_picker', {
            pickMode: 'mcp_only',
            onPick: (detail: unknown) => {
                if (!isPlainObject(detail) || detail.kind !== 'tool') return;
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

    _toolSchema(tool: unknown) {
        if (!isPlainObject(tool) || !isPlainObject(tool.parameters_schema)) return null;
        const properties = tool.parameters_schema.properties;
        return isPlainObject(properties) ? properties : null;
    }

    _resolveLoadedToolRecord(serverId: unknown, toolName: unknown) {
        if (typeof serverId !== 'string' || serverId.length === 0) {
            return null;
        }
        if (typeof toolName !== 'string' || toolName.length === 0) {
            return null;
        }
        const rec = this._findToolRecordInStore(fullMcpToolId(serverId, toolName));
        return isPlainObject(rec) ? rec : null;
    }

    _selectionLabel(server: unknown, serverId: unknown, toolName: unknown, loaded: unknown) {
        if (typeof serverId !== 'string' || serverId.length === 0 || typeof toolName !== 'string' || toolName.length === 0) {
            return this.t('mcp_node_editor.tool_not_selected');
        }
        const loadedRecord = isPlainObject(loaded) ? loaded : null;
        const serverRecord = isPlainObject(server) ? server : null;
        const toolTitle = loadedRecord !== null && typeof loadedRecord.title === 'string' && loadedRecord.title.length > 0
            ? loadedRecord.title
            : toolName;
        const serverLabel = serverRecord !== null && typeof serverRecord.name === 'string' && serverRecord.name.length > 0
            ? serverRecord.name
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
                .flowNodeType=${this.flowNodeType.length > 0 ? this.flowNodeType : 'mcp'}
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
