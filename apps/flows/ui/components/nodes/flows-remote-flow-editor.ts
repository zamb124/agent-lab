/**
 * flows-remote-flow-editor — редактор внешнего A2A flow (RemoteFlowNode).
 *
 * Контракт: только direct A2A URL (без registry flow_id).
 *   - url — JSON-RPC endpoint агента (A2A ≥ 1.0)
 *   - branch_id — Skill ID (A2A skills[].id; у платформы = branch_id; default)
 *   - metadata_template — JSON для SendMessage params.metadata (@state: / @var:)
 *   - headers — dict<str, str>, @var: / @state: в значениях
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-json-editor.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { asObject } from '../../_helpers/flows-resolvers.js';
import './flows-base-node-editor.js';
import '../editors/flows-http-headers-editor.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsRemoteFlowEditor extends PlatformElement {
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
            :host { display: block; height: 100%; min-height: 0; }
            .protocol-panel {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                margin-bottom: var(--space-5);
                padding: var(--space-4);
                border-radius: var(--radius-md);
                border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--border-subtle));
                background:
                    linear-gradient(
                        135deg,
                        color-mix(in srgb, var(--accent) 12%, transparent) 0%,
                        var(--glass-solid-medium) 55%
                    );
            }
            .protocol-panel-header {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
            }
            .protocol-badge {
                display: inline-flex;
                align-items: center;
                padding: 2px 10px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                font-weight: var(--font-bold);
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--accent);
                background: color-mix(in srgb, var(--accent) 16%, transparent);
                border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
            }
            .protocol-title {
                margin: 0;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                line-height: 1.35;
            }
            .protocol-lead {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.5;
            }
            .protocol-list {
                margin: 0;
                padding-left: 1.15rem;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.45;
            }
            .protocol-list li::marker {
                color: var(--accent);
            }
            .protocol-spec {
                margin: 0;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
            }
            .remote-flow-endpoint-stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                margin-bottom: var(--space-5);
            }
            details.metadata-block {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                margin-bottom: var(--space-5);
            }
            details.metadata-block summary {
                cursor: pointer;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }
            .field-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin: var(--space-2) 0;
                line-height: 1.35;
            }
            .field-auth-headers {
                margin-bottom: var(--space-3);
            }
            .headers-label {
                margin: 0 0 var(--space-2);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
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
        this.nodeType = 'remote_flow';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.embedded = false;
    }

    _emitPatch(patch: any) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onUrl(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-remote-flow-editor: url change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-remote-flow-editor: url detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-remote-flow-editor: url string required');
        }
        this._emitPatch({ url: v, flow_id: null });
    }

    _onSkillId(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-remote-flow-editor: branch_id change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-remote-flow-editor: branch_id detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-remote-flow-editor: branch_id string required');
        }
        this._emitPatch({ branch_id: v });
    }

    _onMetadataTemplate(parsed: any) {
        if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
            throw new Error('flows-remote-flow-editor: metadata_template must be a JSON object');
        }
        this._emitPatch({ metadata_template: JSON.stringify(parsed, null, 2) });
    }

    _onHeaders(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d)) {
            throw new Error('flows-remote-flow-editor: headers change detail.value');
        }
        const headers = d.value;
        if (!headers || typeof headers !== 'object' || Array.isArray(headers)) {
            throw new Error('flows-remote-flow-editor: headers must be an object');
        }
        this._emitPatch({ headers });
    }

    _renderProtocolPanel() {
        return html`
            <aside class="protocol-panel" data-testid="remote-flow-protocol-panel">
                <div class="protocol-panel-header">
                    <span class="protocol-badge">${this.t('remote_flow_editor.protocol_badge')}</span>
                    <h3 class="protocol-title">${this.t('remote_flow_editor.protocol_title')}</h3>
                </div>
                <p class="protocol-lead">${this.t('remote_flow_editor.protocol_lead')}</p>
                <ul class="protocol-list">
                    <li>${this.t('remote_flow_editor.protocol_bullet_version')}</li>
                    <li>${this.t('remote_flow_editor.protocol_bullet_rpc')}</li>
                    <li>${this.t('remote_flow_editor.protocol_bullet_card')}</li>
                    <li>${this.t('remote_flow_editor.protocol_bullet_skills')}</li>
                    <li>${this.t('remote_flow_editor.protocol_bullet_metadata')}</li>
                </ul>
                <p class="protocol-spec">${this.t('remote_flow_editor.protocol_spec')}</p>
            </aside>
        `;
    }

    override render(): TemplateResult {
        const cfg = asObject(this.nodeConfig);
        const url = typeof (cfg as any).url === 'string' ? (cfg as any).url : '';
        const branchId = typeof (cfg as any).branch_id === 'string' ? (cfg as any).branch_id : 'default';
        const metadataTemplateStr =
            typeof (cfg as any).metadata_template === 'string' && (cfg as any).metadata_template.length > 0
                ? (cfg as any).metadata_template
                : '{}';
        const headers =
            (cfg as any).headers && typeof (cfg as any).headers === 'object' && !Array.isArray((cfg as any).headers)
                ? (cfg as any).headers
                : {};
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'remote_flow'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
                ?embedded=${this.embedded}
            >
                <div slot="settings">
                    ${this._renderProtocolPanel()}
                    <div class="remote-flow-endpoint-stack">
                        <platform-field
                            mode="edit"
                            type="string"
                            input-type="url"
                            .label=${this.t('remote_flow_editor.url')}
                            .hint=${this.t('remote_flow_editor.url_hint')}
                            .placeholder=${'https://api.example.com/a2a'}
                            .value=${url}
                            @change=${this._onUrl}
                        ></platform-field>
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('remote_flow_editor.skill_id')}
                            .hint=${this.t('remote_flow_editor.skill_hint')}
                            .placeholder=${'default'}
                            .value=${branchId}
                            @change=${this._onSkillId}
                        ></platform-field>
                    </div>
                    <details class="glass-subtle metadata-block" open data-testid="remote-flow-metadata">
                        <summary>${this.t('remote_flow_editor.metadata')}</summary>
                        <p class="field-hint">${this.t('remote_flow_editor.metadata_hint')}</p>
                        <platform-json-editor
                            validate-json
                            show-toolbar="false"
                            .readonly=${false}
                            .value=${metadataTemplateStr}
                            @change=${(e: CustomEvent) => {
                                if (e.detail && 'parsed' in e.detail) {
                                    this._onMetadataTemplate(e.detail.parsed);
                                }
                            }}
                        ></platform-json-editor>
                    </details>
                    <div class="field-auth-headers">
                        <p class="headers-label">${this.t('remote_flow_editor.headers')}</p>
                        <flows-http-headers-editor
                            .value=${headers}
                            @change=${this._onHeaders}
                        ></flows-http-headers-editor>
                    </div>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-remote-flow-editor', FlowsRemoteFlowEditor);
