/**
 * flows-external-api-editor — редактор external_api ноды.
 *
 * Контракт: ExternalAPIConfig (apps/flows/src/models/external_api.py).
 * Данные в запрос: через input_mapping (общий маппинг как у всех нод): ключи входа подставляются в {имя}
 * в URL и мержатся в JSON body после body_template (для методов кроме GET; GET body не шлёт).
 * Шаблоны — @state: / @var: в строках заголовков и body_template.
 * Для ноды как тула у LLM — parameters_schema задайте через общий редактор ноды (/workbench), когда нужно.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-segmented-control.js';
import './flows-base-node-editor.js';
import '@platform/lib/components/platform-json-editor.js';
import '../editors/flows-http-headers-editor.js';
import { asObject } from '../../_helpers/flows-resolvers.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

const HTTP_METHODS = Object.freeze(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);

/** @type {Readonly<Record<string, string>>} */
const HTTP_METHOD_TONES = Object.freeze({
    GET: 'success',
    POST: 'accent-secondary',
    PUT: 'warning',
    PATCH: 'accent-tertiary',
    DELETE: 'error',
});

export class FlowsExternalApiEditor extends PlatformElement {
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
            .settings-wrap {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            details {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
            }
            summary { cursor: pointer; font-size: var(--text-sm); font-weight: var(--font-semibold); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-2); }
            .field-label {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--text-secondary);
            }
            .field-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin: 0 0 var(--space-2);
                line-height: 1.35;
            }
            .method-toggle {
                width: 100%;
            }
            .method-toggle platform-segmented-control {
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = 'external_api';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.embedded = false;
    }

    _emitPatch(patch: any) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onString(field: string, e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-external-api-editor: string field change detail');
        }
        if (!('value' in d)) {
            throw new Error(`flows-external-api-editor: ${field} detail.value`);
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error(`flows-external-api-editor: ${field} string required`);
        }
        this._emitPatch({ [field]: v });
    }

    _onMethod(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-external-api-editor: method change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-external-api-editor: method detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string' || !HTTP_METHODS.includes(v)) {
            throw new Error(`flows-external-api-editor: unsupported HTTP method "${String(v)}"`);
        }
        this._emitPatch({ method: v });
    }

    _onTimeout(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-external-api-editor: timeout change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-external-api-editor: timeout detail.value');
        }
        const v = d.value;
        if (v === null) {
            this._emitPatch({ timeout: 30.0 });
            return;
        }
        if (typeof v !== 'number' || !Number.isFinite(v)) {
            throw new Error('flows-external-api-editor: timeout number|null required');
        }
        this._emitPatch({ timeout: v });
    }

    _onHeaders(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d)) {
            throw new Error('flows-external-api-editor: headers change detail.value');
        }
        const headers = d.value;
        if (!headers || typeof headers !== 'object' || Array.isArray(headers)) {
            throw new Error('flows-external-api-editor: headers must be an object');
        }
        this._emitPatch({ headers });
    }

    _onBodyTemplate(parsed: any) {
        if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
            throw new Error('flows-external-api-editor: body_template must be a JSON object');
        }
        this._emitPatch({ body_template: JSON.stringify(parsed, null, 2) });
    }

    override render(): TemplateResult {
        const cfg = asObject(this.nodeConfig);
        const url = typeof (cfg as any).url === 'string' ? (cfg as any).url : '';
        const method = HTTP_METHODS.includes((cfg as any).method) ? (cfg as any).method : 'POST';
        const timeout = typeof (cfg as any).timeout === 'number' ? (cfg as any).timeout : 30.0;
        const headers =
            (cfg as any).headers && typeof (cfg as any).headers === 'object' && !Array.isArray((cfg as any).headers)
                ? (cfg as any).headers
                : {};
        const bodyTemplateStr =
            typeof (cfg as any).body_template === 'string' && (cfg as any).body_template.length > 0
                ? (cfg as any).body_template
                : '{}';
        const methodItems = HTTP_METHODS.map((m) => ({
            value: m,
            label: m,
            tone: (HTTP_METHOD_TONES as any)[m],
        }));
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'external_api'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
                ?embedded=${this.embedded}
            >
                <div slot="settings" class="settings-wrap">
                    <div class="field method-toggle">
                        <span class="field-label">${this.t('external_api_editor.method')}</span>
                        <platform-segmented-control
                            full-width
                            density="dense"
                            .value=${method}
                            .items=${methodItems}
                            aria-label=${this.t('external_api_editor.method')}
                            @change=${this._onMethod}
                        ></platform-segmented-control>
                    </div>
                    <platform-field
                        mode="edit"
                        type="string"
                        input-type="url"
                        .label=${this.t('external_api_editor.url')}
                        .hint=${this.t('external_api_editor.url_hint')}
                        .placeholder=${'https://api.example.com/v1/items/{item_id}'}
                        .value=${url}
                        @change=${(e: CustomEvent) => this._onString('url', e)}
                    ></platform-field>
                    <platform-field
                        mode="edit"
                        type="number"
                        .label=${this.t('external_api_editor.timeout')}
                        .value=${timeout}
                        @change=${this._onTimeout}
                    ></platform-field>
                    ${method === 'GET'
                        ? nothing
                        : html`
                            <details class="glass-subtle">
                                <summary>${this.t('external_api_editor.body_template')}</summary>
                                <p class="field-hint">${this.t('external_api_editor.body_template_hint')}</p>
                                <platform-json-editor
                                    validate-json
                                    show-toolbar="false"
                                    .readonly=${false}
                                    .value=${bodyTemplateStr}
                                    @change=${(e: CustomEvent) => {
                                        if (e.detail && 'parsed' in e.detail) {
                                            this._onBodyTemplate(e.detail.parsed);
                                        }
                                    }}
                                ></platform-json-editor>
                            </details>
                        `}
                    <details class="glass-subtle" open>
                        <summary>${this.t('external_api_editor.headers')}</summary>
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

customElements.define('flows-external-api-editor', FlowsExternalApiEditor);
