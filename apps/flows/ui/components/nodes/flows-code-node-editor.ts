/**
 * flows-code-node-editor — редактор code-ноды.
 *
 * Поля: `code`, `parameters_schema`, `language` (NodeConfig / CodeNode).
 * Область кода — `flows-code-workbench` (общий UI с code-ресурсом).
 * Если в данных был только `tool_id` без `code`, при открытии подставляется исходник из реестра, `tool_id` сбрасывается.
 */

import type { OpController } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-code-workbench.js';
import { asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import { normalizeFlowCodeLanguage } from '../../_helpers/flows-code-languages.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

export class FlowsCodeNodeEditor extends PlatformElement {
    static i18nNamespace = 'flows';

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
        _hydrateKey: { state: true },
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
    declare _hydrateKey: string;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                height: 100%;
                min-height: 0;
            }
            .settings-wrap {
                display: flex;
                flex-direction: column;
                gap: 0;
            }
        `,
    ];
    private _toolSource: OpController;

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.flowNodeType = 'code';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.embedded = false;
        this._hydrateKey = '';
        this._toolSource = this.useOp('flows/code_tool_source');
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate?.(changed);
        if (changed.has('nodeId')) {
            this._hydrateKey = '';
        }
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (changed.has('nodeConfig') || changed.has('nodeId')) {
            void this._maybeHydrateCodeFromTool();
        }
    }

    async _maybeHydrateCodeFromTool() {
        const cfg = this.nodeConfig;
        if (!isPlainObject(cfg)) {
            return;
        }
        const tid = cfg.tool_id;
        const c = typeof cfg.code === 'string' ? cfg.code : '';
        if (typeof tid !== 'string' || tid.length === 0) {
            return;
        }
        if (c.trim().length > 0) {
            return;
        }
        const key = `${asString(this.nodeId)}:${tid}`;
        if (this._hydrateKey === key) {
            return;
        }
        this._hydrateKey = key;
        const result = await this._toolSource.run({ tool_path: tid });
        const source = isPlainObject(result) ? asString(result.source) : '';
        if (source.length > 0) {
            this._emitPatch({ code: source, tool_id: null });
        }
    }

    _emitPatch(patch: Record<string, unknown>) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onWorkbenchChange(e: CustomEvent) {
        const d = e.detail;
        if (!d || typeof d !== 'object' || !('type' in d)) {
            throw new Error('flows-code-node-editor: code-workbench-change detail');
        }
        if (d.type === 'code') {
            this._emitPatch({ code: asString(d.value), tool_id: null });
            return;
        }
        if (d.type === 'parameters_schema') {
            this._emitPatch({ parameters_schema: d.parameters_schema });
            return;
        }
        if (d.type === 'language') {
            if (typeof d.language !== 'string' || d.language.length === 0) {
                throw new Error('flows-code-node-editor: language required');
            }
            const patch: Record<string, unknown> = { language: normalizeFlowCodeLanguage(d.language) };
            if (typeof d.code === 'string') {
                patch.code = d.code;
                patch.tool_id = null;
            }
            this._emitPatch(patch);
            return;
        }
        throw new Error('flows-code-node-editor: unknown code-workbench-change type');
    }

    override render(): TemplateResult {
        const cfg = isPlainObject(this.nodeConfig) ? this.nodeConfig : {};
        const code = typeof cfg.code === 'string' ? cfg.code : '';
        const schema = cfg.parameters_schema;
        const parametersSchema = isPlainObject(schema)
            ? schema
            : { type: 'object', properties: {}, required: [] };
        const language = normalizeFlowCodeLanguage(cfg.language);
        const fv = isPlainObject(this.flowVariables) ? this.flowVariables : {};
        const completionVariableKeys = Object.keys(fv);
        const bid = typeof this.branchId === 'string' && this.branchId.length > 0 ? this.branchId : '';
        const fid = typeof this.flowId === 'string' ? this.flowId : '';
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .flowNodeType=${this.flowNodeType.length > 0 ? this.flowNodeType : 'code'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
                ?embedded=${this.embedded}
                @change=${(e: CustomEvent) => {
                    const detail = e.detail;
                    if (!detail || typeof detail !== 'object' || !('patch' in detail)) {
                        return;
                    }
                    e.stopPropagation();
                    this.emit('change', detail);
                }}
                @delete-node=${(e: CustomEvent) => this.emit('delete-node', e.detail)}
                @duplicate-node=${(e: CustomEvent) => this.emit('duplicate-node', e.detail)}
            >
                <div slot="settings" class="settings-wrap">
                    <flows-code-workbench
                        variant="node"
                        .scopeKey=${this.nodeId}
                        documentation-perspective="node"
                        .code=${code}
                        .language=${language}
                        .parametersSchema=${parametersSchema}
                        .completionFlowId=${fid}
                        .completionBranchId=${bid}
                        .completionVariableKeys=${completionVariableKeys}
                        @code-workbench-change=${this._onWorkbenchChange}
                    ></flows-code-workbench>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-code-node-editor', FlowsCodeNodeEditor);
