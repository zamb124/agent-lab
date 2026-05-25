/**
 * flows-external-api-editor — редактор external_api ноды.
 *
 * Контракт: ExternalAPIConfig (apps/flows/src/models/external_api.py).
 * Данные в запрос: через input_mapping (общий маппинг как у всех нод): ключи входа подставляются в {имя}
 * в URL и мержатся в JSON body после body_template.
 * Шаблоны — @state: / @var: в строках заголовков и body_template.
 * Для ноды как тула у LLM — parameters_schema задайте через общий редактор ноды (/workbench), когда нужно.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-node-editor.js';
import '../editors/flows-json-field-editor.js';
import { asObject } from '../../_helpers/flows-resolvers.js';

const HTTP_METHODS = Object.freeze(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);

export class FlowsExternalApiEditor extends PlatformElement {
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
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .settings-wrap {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            details {
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            summary { cursor: pointer; font-size: var(--text-sm); font-weight: var(--font-semibold); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-2); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); }
            .field-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin: 0 0 var(--space-2);
                line-height: 1.35;
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
        this.expanded = false;
        this.embedded = false;
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onString(field, e) {
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

    _onMethod(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-external-api-editor: method change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-external-api-editor: method detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-external-api-editor: method string required');
        }
        this._emitPatch({ method: v });
    }

    _onTimeout(e) {
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

    _onHeaders(parsed) {
        this._emitPatch({ headers: parsed && typeof parsed === 'object' ? parsed : {} });
    }

    _onBodyTemplate(parsed) {
        if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
            throw new Error('flows-external-api-editor: body_template must be a JSON object');
        }
        this._emitPatch({ body_template: JSON.stringify(parsed, null, 2) });
    }

    render() {
        const cfg = asObject(this.nodeConfig);
        const name = typeof cfg.name === 'string' ? cfg.name : '';
        const description = typeof cfg.description === 'string' ? cfg.description : '';
        const url = typeof cfg.url === 'string' ? cfg.url : '';
        const method = HTTP_METHODS.includes(cfg.method) ? cfg.method : 'POST';
        const timeout = typeof cfg.timeout === 'number' ? cfg.timeout : 30.0;
        const headersJson = cfg.headers && typeof cfg.headers === 'object'
            ? JSON.stringify(cfg.headers, null, 2) : '{}';
        const bodyTemplateStr =
            typeof cfg.body_template === 'string' && cfg.body_template.length > 0
                ? cfg.body_template
                : '{}';
        const methodValues = HTTP_METHODS.map((m) => ({ value: m, label: m }));
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
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
            >
                <div slot="settings" class="settings-wrap">
                    <div class="grid">
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('external_api_editor.name')}
                            .value=${name}
                            @change=${(e) => this._onString('name', e)}
                        ></platform-field>
                        <platform-field
                            mode="edit"
                            type="enum"
                            .label=${this.t('external_api_editor.method')}
                            .value=${method}
                            .config=${{ values: methodValues }}
                            @change=${this._onMethod}
                        ></platform-field>
                    </div>
                    <platform-field
                        mode="edit"
                        type="string"
                        input-type="url"
                        .label=${this.t('external_api_editor.url')}
                        .hint=${this.t('external_api_editor.url_hint')}
                        .placeholder=${'https://api.example.com/v1/items/{item_id}'}
                        .value=${url}
                        @change=${(e) => this._onString('url', e)}
                    ></platform-field>
                    <platform-field
                        mode="edit"
                        type="string"
                        .label=${this.t('external_api_editor.description')}
                        .value=${description}
                        @change=${(e) => this._onString('description', e)}
                    ></platform-field>
                    <platform-field
                        mode="edit"
                        type="number"
                        .label=${this.t('external_api_editor.timeout')}
                        .value=${timeout}
                        @change=${this._onTimeout}
                    ></platform-field>
                    <details>
                        <summary>${this.t('external_api_editor.body_template')}</summary>
                        <p class="field-hint">${this.t('external_api_editor.body_template_hint')}</p>
                        <flows-json-field-editor
                            .value=${bodyTemplateStr}
                            @change=${(e) => {
                                if (e.detail && 'parsed' in e.detail) {
                                    this._onBodyTemplate(e.detail.parsed);
                                }
                            }}
                        ></flows-json-field-editor>
                    </details>
                    <details>
                        <summary>${this.t('external_api_editor.headers')}</summary>
                        <p class="field-hint">${this.t('external_api_editor.headers_hint')}</p>
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

customElements.define('flows-external-api-editor', FlowsExternalApiEditor);
