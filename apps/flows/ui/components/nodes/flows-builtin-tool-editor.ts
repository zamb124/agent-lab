/**
 * Contract panel for platform builtin tools (no editable source).
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formatJsonPretty } from '@platform/lib/utils/json-format.js';
import './flows-base-node-editor.js';
import { asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsBuiltinToolEditor extends PlatformElement {
    static i18nNamespace = 'flows';

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
        css`
            :host {
                display: block;
                height: 100%;
                min-height: 0;
            }
            .builtin-contract {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-1) 0;
            }
            .builtin-desc {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.45;
                white-space: pre-wrap;
            }
            .builtin-meta {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }
            .builtin-chip {
                display: inline-flex;
                align-items: center;
                font-size: 10px;
                font-weight: var(--font-medium);
                letter-spacing: 0.02em;
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .builtin-chip[data-kind='floor'] {
                background: color-mix(in srgb, var(--warning) 18%, var(--glass-tint-medium));
                color: var(--text-secondary);
            }
            .builtin-section-title {
                margin: 0;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .builtin-schema {
                margin: 0;
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-tint-medium);
                font-family: var(--font-mono);
                font-size: 11px;
                line-height: 1.4;
                overflow: auto;
                max-height: 320px;
                white-space: pre;
                color: var(--text-secondary);
            }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = 'builtin';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.embedded = false;
    }

    _confirmationLabel(floor: any) {
        if (floor === 'preview') {
            return this.t('builtin_tool_editor.confirmation_preview');
        }
        if (floor === 'approval') {
            return this.t('builtin_tool_editor.confirmation_approval');
        }
        return this.t('builtin_tool_editor.confirmation_none');
    }

    override render(): TemplateResult {
        const cfg = isPlainObject(this.nodeConfig) ? this.nodeConfig : {};
        const description = typeof cfg.description! === 'string' ? cfg.description! : '';
        const rawEffects = cfg.effects;
        const effects = Array.isArray(rawEffects)
            ? rawEffects.filter((effect) => typeof effect === 'string')
            : [];
        const confirmationFloor =
            typeof cfg.confirmation_floor! === 'string' && cfg.confirmation_floor.length! > 0
                ? cfg.confirmation_floor!
                : 'none';
        const parametersSchema = isPlainObject(cfg.parameters_schema)
            ? cfg.parameters_schema
            : { type: 'object', properties: {} };
        const schemaText = formatJsonPretty(parametersSchema);

        return html`
            <flows-base-node-editor
                .nodeId=${asString(this.nodeId)}
                .flowId=${asString(this.flowId)}
                .branchId=${asString(this.branchId)}
                .nodeConfig=${cfg}
                .nodeType=${'builtin'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
                ?embedded=${this.embedded}
                @change=${(event: CustomEvent) => this.emit('change', event.detail)}
                @delete-node=${(event: CustomEvent) => this.emit('delete-node', event.detail)}
                @duplicate-node=${(event: CustomEvent) => this.emit('duplicate-node', event.detail)}
            >
                <div slot="settings" class="builtin-contract">
                    ${description.length > 0
                        ? html`<p class="builtin-desc">${description}</p>`
                        : nothing}
                    <div class="builtin-meta">
                        ${effects.map(
                            (effect) => html`
                                <span class="builtin-chip" data-kind="effect">${effect}</span>
                            `,
                        )}
                        <span class="builtin-chip" data-kind="floor">
                            ${this._confirmationLabel(confirmationFloor)}
                        </span>
                    </div>
                    <h4 class="builtin-section-title">${this.t('builtin_tool_editor.parameters')}</h4>
                    <pre class="builtin-schema">${schemaText}</pre>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-builtin-tool-editor', FlowsBuiltinToolEditor);
