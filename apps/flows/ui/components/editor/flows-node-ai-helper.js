import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/embed-chat/platform-embed-chat.js';
import {
    buildLaraFlowsContext,
    flattenLaraFlowsContext,
    laraNodeHelperBranchId,
    laraNodeHelperConversationKey,
} from '../../_helpers/lara-node-helper.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';
import { normalizeFlowCodeLanguage } from '../../_helpers/flows-code-languages.js';

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
                height: 100%;
                min-height: 0;
                background: var(--bg-primary);
            }

            .chat-shell {
                flex: 1;
                min-height: 0;
                padding: var(--space-3);
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
            }

            platform-embed-chat {
                flex: 1;
                min-height: 0;
                --embed-radius: var(--radius-lg);
                --embed-chat-accent: var(--accent);
                --embed-chat-accent-muted: var(--accent-subtle);
                --embed-chat-on-accent: var(--text-inverse);
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this.nodeId = '';
        this._editor = this.useOp('flows/editor');
        this._codeDocs = this.useOp('flows/code_documentation');
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

    _codeDocumentationLanguage(context) {
        const node = isPlainObject(context.node_payload) ? context.node_payload : {};
        const fromNode = typeof node.language === 'string' ? node.language : '';
        const branchCode = isPlainObject(context.branch_code_payload) ? context.branch_code_payload : {};
        const selectedCode = isPlainObject(branchCode.selected_node) ? branchCode.selected_node : {};
        const fromSelected = typeof selectedCode.language === 'string' ? selectedCode.language : '';
        return normalizeFlowCodeLanguage(fromNode || fromSelected || 'python');
    }

    async _codeDocumentationVariables(context) {
        if (context.node_type !== 'code') {
            return {};
        }
        const language = this._codeDocumentationLanguage(context);
        try {
            const result = await this._codeDocs.run({
                language,
                perspective: 'node',
            });
            const markdown = typeof result === 'string'
                ? result
                : result && typeof result === 'object' && typeof result.markdown === 'string'
                    ? result.markdown
                    : '';
            return {
                code_inline_documentation_language: language,
                code_inline_documentation_md: markdown,
                code_inline_documentation_source: 'flows/code_documentation',
            };
        } catch (error) {
            return {
                code_inline_documentation_language: language,
                code_inline_documentation_md: '',
                code_inline_documentation_source: 'flows/code_documentation',
                code_inline_documentation_error: error instanceof Error ? error.message : String(error),
            };
        }
    }

    _chatVariables = async () => {
        const context = this._nodeContext();
        return {
            ...flattenLaraFlowsContext(context),
            ...await this._codeDocumentationVariables(context),
        };
    };

    _labels() {
        return {
            greeting: '',
            placeholder: this.t('node_ai_helper.placeholder'),
        };
    }

    render() {
        const context = this._nodeContext();
        return html`
            <div class="chat-shell">
                <platform-embed-chat
                    .hideHeader=${true}
                    .visible=${true}
                    embed-theme="light"
                    interface-locale="auto"
                    .flowsBaseUrl=${'/flows'}
                    flow-id="lara"
                    branch-id=${context.assistant_branch_id}
                    conversation-key=${laraNodeHelperConversationKey(context)}
                    .assistantTitle=${'Lara'}
                    .title=${'Lara'}
                    .labels=${this._labels()}
                    ?use-credentials=${true}
                    .enableVoice=${false}
                    .getExtraMetadataVariables=${this._chatVariables}
                    event-namespace="assistant"
                ></platform-embed-chat>
            </div>
        `;
    }
}

customElements.define('flows-node-ai-helper', FlowsNodeAiHelper);
