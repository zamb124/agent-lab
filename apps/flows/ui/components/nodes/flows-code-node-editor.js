/**
 * flows-code-node-editor — редактор code-ноды.
 *
 * Поля: `code`, `args_schema`, `language` (NodeConfig / CodeNode).
 * Область кода — `flows-code-workbench` (общий UI с code-ресурсом).
 * Если в данных был только `tool_id` без `code`, при открытии подставляется исходник из реестра, `tool_id` сбрасывается.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-code-workbench.js';
import { asString } from '../../_helpers/flows-resolvers.js';
import { normalizeFlowCodeLanguage } from '../../_helpers/flows-code-languages.js';

export class FlowsCodeNodeEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        dataflowNode: { type: Object },
        expanded: { type: Boolean, reflect: true },
        embedded: { type: Boolean, reflect: true },
        _hydrateKey: { state: true },
    };

    static styles = [
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

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = 'code';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.expanded = false;
        this.embedded = false;
        this._hydrateKey = '';
        this._toolSource = this.useOp('flows/code_tool_source');
    }

    willUpdate(changed) {
        super.willUpdate?.(changed);
        if (changed.has('nodeId')) {
            this._hydrateKey = '';
        }
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('nodeConfig') || changed.has('nodeId')) {
            void this._maybeHydrateCodeFromTool();
        }
    }

    async _maybeHydrateCodeFromTool() {
        const cfg = this.nodeConfig;
        if (!cfg || typeof cfg !== 'object') {
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
        const source = result && typeof result === 'object' && result !== null && 'source' in result
            ? asString(result.source)
            : '';
        if (source.length > 0) {
            this._emitPatch({ code: source, tool_id: null });
        }
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onWorkbenchChange(e) {
        const d = e.detail;
        if (!d || typeof d !== 'object' || !('type' in d)) {
            throw new Error('flows-code-node-editor: code-workbench-change detail');
        }
        if (d.type === 'code') {
            this._emitPatch({ code: asString(d.value), tool_id: null });
            return;
        }
        if (d.type === 'args_schema') {
            this._emitPatch({ args_schema: d.args_schema });
            return;
        }
        if (d.type === 'language') {
            if (typeof d.language !== 'string' || d.language.length === 0) {
                throw new Error('flows-code-node-editor: language required');
            }
            const patch = { language: normalizeFlowCodeLanguage(d.language) };
            if (typeof d.code === 'string') {
                patch.code = d.code;
                patch.tool_id = null;
            }
            this._emitPatch(patch);
            return;
        }
        throw new Error('flows-code-node-editor: unknown code-workbench-change type');
    }

    render() {
        const cfg = this.nodeConfig && typeof this.nodeConfig === 'object' ? this.nodeConfig : {};
        const code = typeof cfg.code === 'string' ? cfg.code : '';
        const argsSchema = cfg.args_schema && typeof cfg.args_schema === 'object' && !Array.isArray(cfg.args_schema)
            ? cfg.args_schema
            : {};
        const language = normalizeFlowCodeLanguage(cfg.language);
        const fv =
            this.flowVariables &&
            typeof this.flowVariables === 'object' &&
            !Array.isArray(this.flowVariables)
                ? this.flowVariables
                : {};
        const completionVariableKeys = Object.keys(fv);
        const bid = typeof this.branchId === 'string' && this.branchId.length > 0 ? this.branchId : '';
        const fid = typeof this.flowId === 'string' ? this.flowId : '';
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'code'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
            >
                <div slot="settings" class="settings-wrap">
                    <flows-code-workbench
                        variant="node"
                        .scopeKey=${this.nodeId}
                        documentation-perspective="node"
                        .code=${code}
                        .language=${language}
                        .argsSchema=${argsSchema}
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
