import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import {
    buildLaraFlowsContext,
    flattenLaraFlowsContext,
    laraNodeHelperBranchId,
} from '../../_helpers/lara-node-helper.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';

export class FlowsNodeAiHelper extends PlatformElement {
    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        nodeId: { type: String, attribute: 'node-id' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1 1 0;
                height: 100%;
                min-height: 0;
                overflow: hidden;
                background: color-mix(in oklab, var(--bg-secondary) 72%, transparent);
            }

            .chat-shell {
                flex: 1 1 0;
                min-height: 0;
                padding: var(--space-2);
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            platform-flow-ui {
                flex: 1 1 0;
                min-height: 0;
                height: 100%;
                --flow-ui-radius: var(--radius-lg);
                --flow-ui-accent: var(--accent);
                --flow-ui-accent-muted: var(--accent-subtle);
                --flow-ui-on-accent: var(--text-inverse);
                /* spa profile clears page fill; keep an opaque surface in the assistant column */
                --flow-ui-page-background: color-mix(in oklab, var(--bg-secondary) 88%, transparent);
                --flow-ui-background: var(--flow-ui-page-background);
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this.nodeId = '';
        this._editor = this.useOp('flows/editor');
        this._getExtraMetadataVariables = async () => flattenLaraFlowsContext(this._nodeContext());
    }

    _nodeContext() {
        const editorState = asObject(this._editor.state);
        const branchData = isPlainObject(editorState.branchData) ? editorState.branchData : {};
        const nodes = isPlainObject(branchData.nodes) ? branchData.nodes : {};
        const node = this.nodeId && isPlainObject(nodes[this.nodeId]) ? nodes[this.nodeId] : null;
        const nodeType = node && typeof node.type === 'string' ? node.type : '';
        const assistantBranchId = laraNodeHelperBranchId(nodeType);
        return buildLaraFlowsContext(
            editorState,
            { flowId: this.flowId, branchId: this.branchId },
            {
                flow_id: this.flowId,
                branch_id: this.branchId,
                node_id: this.nodeId,
                assistant_branch_id: assistantBranchId,
                request_kind: 'node_ai_helper',
                selection_source: 'node_header_ai',
                screen: 'flow_editor_node_ai_helper',
            },
        );
    }

    render() {
        const context = this._nodeContext();
        return html`
            <div class="chat-shell">
                <platform-flow-ui
                    display="panel"
                    profile="spa"
                    theme="auto"
                    locale="auto"
                    base-url="/flows"
                    flow-id="lara"
                    branch-id=${context.assistant_branch_id}
                    .getExtraMetadataVariables=${this._getExtraMetadataVariables}
                ></platform-flow-ui>
            </div>
        `;
    }
}

customElements.define('flows-node-ai-helper', FlowsNodeAiHelper);
