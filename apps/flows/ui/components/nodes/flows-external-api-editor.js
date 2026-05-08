/**
 * flows-external-api-editor — редактор external_api ноды.
 *
 * Поля точно по `ExternalAPIConfig`
 * (apps/flows/src/models/external_api.py):
 *   - name, description
 *   - url, method (HTTPMethod enum)
 *   - timeout (float)
 *   - headers (dict<str, str>)
 *   - auth_headers (dict<str, str>)
 *   - parameters (list[ParameterSchema] с location)
 *   - state_mapping (dict<str, str>)
 *
 * Поля `body` в модели нет — параметры с location='body' формируют тело
 * запроса автоматически.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-node-editor.js';
import '../editors/flows-json-field-editor.js';
import '../editors/flows-state-mapping-editor.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';

const HTTP_METHODS = Object.freeze(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);
const PARAM_LOCATIONS = Object.freeze(['body', 'query', 'path', 'header']);
const PARAM_TYPES = Object.freeze(['string', 'integer', 'number', 'boolean', 'object', 'array']);

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
        expanded: { type: Boolean, reflect: true },
        embedded: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            details {
                margin-bottom: var(--space-3);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            summary { cursor: pointer; font-size: var(--text-sm); font-weight: var(--font-semibold); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-2); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input, select {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); }
            .param-row {
                display: grid;
                grid-template-columns: 1.4fr 1fr 1fr 60px 30px;
                gap: var(--space-1);
                align-items: end;
                padding: var(--space-1);
                border-bottom: 1px solid var(--border-subtle);
            }
            .param-row .req {
                display: flex; justify-content: center;
            }
            .param-row button.del {
                background: none; border: none; padding: 0; cursor: pointer;
                color: var(--text-tertiary);
            }
            .param-row button.del:hover { color: var(--error); }
            .add-btn { margin-top: var(--space-2); }
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

    _onParamName(idx, e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-external-api-editor: param name change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-external-api-editor: param name detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-external-api-editor: param name string required');
        }
        this._updateParam(idx, { name: v });
    }

    _onParamLocation(idx, e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-external-api-editor: param location change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-external-api-editor: param location detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-external-api-editor: param location string required');
        }
        this._updateParam(idx, { location: v });
    }

    _onParamType(idx, e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-external-api-editor: param type change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-external-api-editor: param type detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-external-api-editor: param type string required');
        }
        this._updateParam(idx, { type: v });
    }

    _onHeaders(parsed) {
        this._emitPatch({ headers: parsed && typeof parsed === 'object' ? parsed : {} });
    }

    _onAuthHeaders(parsed) {
        this._emitPatch({ auth_headers: parsed && typeof parsed === 'object' ? parsed : {} });
    }

    _onStateMapping(e) {
        const mapping = e.detail?.mapping;
        this._emitPatch({ state_mapping: isPlainObject(mapping) ? mapping : {} });
    }

    _params() {
        return Array.isArray(this.nodeConfig?.parameters) ? this.nodeConfig.parameters : [];
    }

    _setParams(next) {
        this._emitPatch({ parameters: next });
    }

    _addParam() {
        this._setParams([
            ...this._params(),
            { name: '', location: 'body', type: 'string', required: false, default: null },
        ]);
    }

    _removeParam(idx) {
        this._setParams(this._params().filter((_, i) => i !== idx));
    }

    _updateParam(idx, patch) {
        const next = this._params().map((p, i) => (i === idx ? { ...p, ...patch } : p));
        this._setParams(next);
    }

    _renderParams() {
        const params = this._params();
        return html`
            <details>
                <summary>${this.t('external_api_editor.parameters')}</summary>
                ${params.map((p, idx) => {
                    const loc = typeof p.location === 'string' ? p.location : 'body';
                    const ptype = typeof p.type === 'string' ? p.type : 'string';
                    const locationValues = PARAM_LOCATIONS.map((locId) => ({
                        value: locId,
                        label: this.t(`external_api_editor.location_${locId}`),
                    }));
                    const typeValues = PARAM_TYPES.map((t) => ({ value: t, label: t }));
                    return html`
                    <div class="param-row">
                        <platform-field
                            mode="edit"
                            type="string"
                            .placeholder=${this.t('external_api_editor.parameter_name')}
                            .value=${typeof p.name === 'string' ? p.name : ''}
                            @change=${(e) => this._onParamName(idx, e)}
                        ></platform-field>
                        <platform-field
                            mode="edit"
                            type="enum"
                            .value=${loc}
                            .config=${{ values: locationValues }}
                            @change=${(e) => this._onParamLocation(idx, e)}
                        ></platform-field>
                        <platform-field
                            mode="edit"
                            type="enum"
                            .value=${ptype}
                            .config=${{ values: typeValues }}
                            @change=${(e) => this._onParamType(idx, e)}
                        ></platform-field>
                        <label class="req">
                            <input type="checkbox" ?checked=${Boolean(p.required)}
                                @change=${(e) => this._updateParam(idx, { required: e.target.checked })} />
                        </label>
                        <button class="del" title=${this.t('external_api_editor.parameter_remove')}
                            @click=${() => this._removeParam(idx)}>
                            <platform-icon name="trash" size="xs"></platform-icon>
                        </button>
                    </div>
                `;
                })}
                <glass-button class="add-btn" size="sm" variant="ghost" @click=${this._addParam}>
                    <platform-icon name="plus"></platform-icon>
                    ${this.t('external_api_editor.parameter_add')}
                </glass-button>
            </details>
        `;
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
        const authHeadersJson = cfg.auth_headers && typeof cfg.auth_headers === 'object'
            ? JSON.stringify(cfg.auth_headers, null, 2) : '{}';
        const stateMapping = cfg.state_mapping && typeof cfg.state_mapping === 'object'
            ? cfg.state_mapping : {};
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
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
            >
                <div slot="settings">
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
                        .placeholder=${'https://api.example.com/{path}'}
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
                        <summary>${this.t('external_api_editor.headers')}</summary>
                        <flows-json-field-editor
                            .value=${headersJson}
                            @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._onHeaders(e.detail.parsed); }}
                        ></flows-json-field-editor>
                    </details>
                    <details>
                        <summary>${this.t('external_api_editor.auth_headers')}</summary>
                        <flows-json-field-editor
                            .value=${authHeadersJson}
                            @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._onAuthHeaders(e.detail.parsed); }}
                        ></flows-json-field-editor>
                    </details>
                    ${this._renderParams()}
                    <details>
                        <summary>${this.t('external_api_editor.response_mapping')}</summary>
                        <flows-state-mapping-editor
                            syncKey=${String(this.flowId ?? '')}--${String(this.nodeId ?? '')}--extapi-state
                            kind="output"
                            .mapping=${stateMapping}
                            @change=${this._onStateMapping}
                        ></flows-state-mapping-editor>
                    </details>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-external-api-editor', FlowsExternalApiEditor);
