/**
 * flows-llm-config-editor — единая форма LLM-конфига.
 *
 * Используется в:
 *   - LLM ноде (`NodeLLMOverride`, `cfg.llm_override`)
 *   - LLM ресурсе (`LLMResourceConfig`, `resource.config`)
 *
 * Поля точно соответствуют [NodeLLMOverride / LLMResourceConfig]
 * (apps/flows/src/models/node_config.py, apps/flows/src/models/resource.py):
 *   provider, model, temperature, max_tokens, api_key, base_url,
 *   top_p, top_k, frequency_penalty, presence_penalty, seed,
 *   reasoning_effort, extra_request_body.
 *
 * Property API:
 *   - config: object  // текущее значение
 *
 * Events (emit):
 *   - 'change' { config }  // полный объект (мерж с предыдущим)
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-json-field-editor.js';
import { asString } from '../../_helpers/flows-resolvers.js';

const REASONING_LEVELS = Object.freeze(['', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh']);

export class FlowsLlmConfigEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        config: { type: Object },
        _showAdvanced: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                container-type: inline-size;
                min-width: 0;
                width: 100%;
                box-sizing: border-box;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-3, 12px);
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
            @container (max-width: 480px) {
                .grid {
                    grid-template-columns: minmax(0, 1fr);
                }
            }
            .field {
                display: flex;
                flex-direction: column;
                gap: 4px;
                min-width: 0;
                max-width: 100%;
            }
            .full { grid-column: 1 / -1; }
            details {
                margin-top: var(--space-2);
                padding: var(--space-2);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                background: var(--glass-solid-subtle);
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
            summary {
                cursor: pointer;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                user-select: none;
                padding: 2px 0;
            }
            details[open] summary {
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }
            .extra {
                margin-top: var(--space-1);
            }
        `,
    ];

    constructor() {
        super();
        this.config = null;
        this._showAdvanced = false;
        this._models = this.useOp('flows/models_list');
        this._providers = this.useOp('flows/providers_list');
        this._loadedProvider = null;
        this._providersLoaded = false;
    }

    connectedCallback() {
        super.connectedCallback();
        if (!this._providersLoaded) {
            this._providersLoaded = true;
            void this._providers.run(null);
        }
    }

    updated(changed) {
        super.updated?.(changed);
        const provider = this._readString('provider');
        if (provider && provider !== this._loadedProvider) {
            this._loadedProvider = provider;
            void this._models.run({ provider });
        }
    }

    _readString(field) {
        const cfg = this.config;
        if (!cfg || typeof cfg !== 'object') return '';
        const v = cfg[field];
        return typeof v === 'string' ? v : '';
    }

    _readNumberField(field) {
        const cfg = this.config;
        if (!cfg || typeof cfg !== 'object') return null;
        const v = cfg[field];
        return typeof v === 'number' && Number.isFinite(v) ? v : null;
    }

    _emitPatch(patch) {
        const base = this.config && typeof this.config === 'object' ? this.config : {};
        const next = { ...base, ...patch };
        this.emit('change', { config: next });
    }

    _onString(field, value) {
        const v = typeof value === 'string' ? value : '';
        if (v.length === 0) {
            const base = this.config && typeof this.config === 'object' ? this.config : {};
            const next = { ...base };
            delete next[field];
            this.emit('change', { config: next });
            return;
        }
        this._emitPatch({ [field]: v });
    }

    _onNumberField(field, detailValue) {
        if (detailValue === null || detailValue === undefined) {
            const base = this.config && typeof this.config === 'object' ? this.config : {};
            const next = { ...base };
            delete next[field];
            this.emit('change', { config: next });
            return;
        }
        if (typeof detailValue !== 'number' || !Number.isFinite(detailValue)) return;
        this._emitPatch({ [field]: detailValue });
    }

    _onJson(field, parsed) {
        const base = this.config && typeof this.config === 'object' ? this.config : {};
        const next = { ...base };
        if (parsed === null || parsed === undefined) {
            delete next[field];
        } else {
            next[field] = parsed;
        }
        this.emit('change', { config: next });
    }

    _modelsList() {
        const result = this._models.lastResult;
        if (Array.isArray(result?.items)) return result.items;
        if (Array.isArray(result)) return result;
        return [];
    }

    _providersList() {
        const result = this._providers.lastResult;
        if (Array.isArray(result?.items)) return result.items;
        if (Array.isArray(result)) return result;
        return [];
    }

    render() {
        const provider = this._readString('provider');
        const model = this._readString('model');
        const apiKey = this._readString('api_key');
        const baseUrl = this._readString('base_url');
        const reasoning = this._readString('reasoning_effort');
        const cfg = this.config && typeof this.config === 'object' ? this.config : {};
        const extraJson = cfg.extra_request_body && typeof cfg.extra_request_body === 'object'
            ? JSON.stringify(cfg.extra_request_body, null, 2)
            : '{}';
        const models = this._modelsList();
        const providers = this._providersList();
        const providerEnumValues = [
            { value: '', label: '—' },
            ...providers.map((p) => ({ value: p, label: p })),
        ];
        const modelEnumValues = [
            { value: '', label: '—' },
            ...models.map((m) => {
                const optValue = typeof m === 'string' ? m : asString(typeof m.value === 'string' && m.value.length > 0 ? m.value : m.id);
                let optLabel;
                if (typeof m === 'string') optLabel = m;
                else if (typeof m.label === 'string' && m.label.length > 0) optLabel = m.label;
                else if (typeof m.value === 'string' && m.value.length > 0) optLabel = m.value;
                else optLabel = String(m.id);
                return { value: optValue, label: optLabel };
            }),
        ];
        const reasoningEnumValues = REASONING_LEVELS.map((lv) => (lv === ''
            ? { value: '', label: '—' }
            : { value: lv, label: lv }));
        return html`
            <div class="grid">
                <div class="field">
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('llm_config_editor.provider')}
                        .value=${provider}
                        .config=${{ values: providerEnumValues }}
                        @change=${(e) => this._onString('provider', typeof e.detail.value === 'string' ? e.detail.value : '')}
                    ></platform-field>
                </div>
                <div class="field">
                    ${models.length > 0
                        ? html`<platform-field
                            type="enum"
                            mode="edit"
                            .label=${this.t('llm_config_editor.model')}
                            .value=${model}
                            .config=${{ values: modelEnumValues }}
                            @change=${(e) => this._onString('model', typeof e.detail.value === 'string' ? e.detail.value : '')}
                        ></platform-field>`
                        : html`<platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('llm_config_editor.model')}
                            .placeholder=${this.t('llm_config_editor.placeholder_model')}
                            .value=${model}
                            @change=${(e) => this._onString('model', typeof e.detail.value === 'string' ? e.detail.value : '')}
                        ></platform-field>`}
                </div>
                <div class="field">
                    <platform-field
                        type="number"
                        mode="edit"
                        .label=${this.t('llm_config_editor.temperature')}
                        .placeholder=${this.t('llm_config_editor.placeholder_temperature')}
                        .value=${this._readNumberField('temperature')}
                        @change=${(e) => this._onNumberField('temperature', e.detail.value)}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="integer"
                        mode="edit"
                        .label=${this.t('llm_config_editor.max_tokens')}
                        .placeholder=${this.t('llm_config_editor.placeholder_max_tokens')}
                        .value=${this._readNumberField('max_tokens')}
                        @change=${(e) => this._onNumberField('max_tokens', e.detail.value)}
                    ></platform-field>
                </div>
            </div>

            <details ?open=${this._showAdvanced} @toggle=${(e) => { this._showAdvanced = e.target.open; }}>
                <summary>${this.t('llm_config_editor.advanced')}</summary>
                <div class="grid">
                    <div class="field full">
                        <platform-field
                            type="string"
                            mode="edit"
                            input-type="password"
                            .label=${this.t('llm_config_editor.api_key')}
                            .placeholder="@var:KEY"
                            .value=${apiKey}
                            @change=${(e) => this._onString('api_key', typeof e.detail.value === 'string' ? e.detail.value : '')}
                        ></platform-field>
                    </div>
                    <div class="field full">
                        <platform-field
                            type="string"
                            mode="edit"
                            .label=${this.t('llm_config_editor.base_url')}
                            .placeholder="https://api.example.com/v1"
                            .value=${baseUrl}
                            @change=${(e) => this._onString('base_url', typeof e.detail.value === 'string' ? e.detail.value : '')}
                        ></platform-field>
                    </div>
                    <div class="field">
                        <platform-field
                            type="number"
                            mode="edit"
                            .label=${this.t('llm_config_editor.top_p')}
                            .placeholder=${this.t('llm_config_editor.placeholder_top_p')}
                            .value=${this._readNumberField('top_p')}
                            @change=${(e) => this._onNumberField('top_p', e.detail.value)}
                        ></platform-field>
                    </div>
                    <div class="field">
                        <platform-field
                            type="integer"
                            mode="edit"
                            .label=${this.t('llm_config_editor.top_k')}
                            .placeholder=${this.t('llm_config_editor.placeholder_top_k')}
                            .value=${this._readNumberField('top_k')}
                            @change=${(e) => this._onNumberField('top_k', e.detail.value)}
                        ></platform-field>
                    </div>
                    <div class="field">
                        <platform-field
                            type="number"
                            mode="edit"
                            .label=${this.t('llm_config_editor.frequency_penalty')}
                            .placeholder=${this.t('llm_config_editor.placeholder_frequency_penalty')}
                            .value=${this._readNumberField('frequency_penalty')}
                            @change=${(e) => this._onNumberField('frequency_penalty', e.detail.value)}
                        ></platform-field>
                    </div>
                    <div class="field">
                        <platform-field
                            type="number"
                            mode="edit"
                            .label=${this.t('llm_config_editor.presence_penalty')}
                            .placeholder=${this.t('llm_config_editor.placeholder_presence_penalty')}
                            .value=${this._readNumberField('presence_penalty')}
                            @change=${(e) => this._onNumberField('presence_penalty', e.detail.value)}
                        ></platform-field>
                    </div>
                    <div class="field">
                        <platform-field
                            type="integer"
                            mode="edit"
                            .label=${this.t('llm_config_editor.seed')}
                            .placeholder=${this.t('llm_config_editor.placeholder_seed')}
                            .value=${this._readNumberField('seed')}
                            @change=${(e) => this._onNumberField('seed', e.detail.value)}
                        ></platform-field>
                    </div>
                    <div class="field">
                        <platform-field
                            type="enum"
                            mode="edit"
                            .label=${this.t('llm_config_editor.reasoning_effort')}
                            .value=${reasoning}
                            .config=${{ values: reasoningEnumValues }}
                            @change=${(e) => this._onString('reasoning_effort', typeof e.detail.value === 'string' ? e.detail.value : '')}
                        ></platform-field>
                    </div>
                    <div class="field full extra">
                        <label>${this.t('llm_config_editor.extra_request_body')}</label>
                        <flows-json-field-editor
                            .value=${extraJson}
                            @change=${(e) => {
                                if (e.detail && 'parsed' in e.detail) this._onJson('extra_request_body', e.detail.parsed);
                            }}
                        ></flows-json-field-editor>
                    </div>
                </div>
            </details>
        `;
    }
}

customElements.define('flows-llm-config-editor', FlowsLlmConfigEditor);
