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
import './flows-json-field-editor.js';

const PROVIDERS = Object.freeze([
    'openai', 'anthropic', 'openrouter', 'bothub', 'ya', 'sber', 'provider_litserve', 'mock',
]);

const REASONING_LEVELS = Object.freeze(['', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh']);

export class FlowsLlmConfigEditor extends PlatformElement {
    static properties = {
        config: { type: Object },
        _showAdvanced: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-2);
            }
            .field { display: flex; flex-direction: column; gap: var(--space-1); }
            .full { grid-column: 1 / -1; }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input, select {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
            details {
                margin-top: var(--space-3);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            summary {
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                user-select: none;
                padding: var(--space-1) 0;
            }
            details[open] summary {
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }
            .extra {
                margin-top: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.config = null;
        this._showAdvanced = false;
        this._models = this.useOp('flows/models_list');
        this._loadedProvider = null;
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

    _readNumberOrEmpty(field) {
        const cfg = this.config;
        if (!cfg || typeof cfg !== 'object') return '';
        const v = cfg[field];
        return typeof v === 'number' && Number.isFinite(v) ? String(v) : '';
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

    _onNumber(field, raw, isInt = false) {
        if (raw === '' || raw === null || raw === undefined) {
            const base = this.config && typeof this.config === 'object' ? this.config : {};
            const next = { ...base };
            delete next[field];
            this.emit('change', { config: next });
            return;
        }
        const n = isInt ? parseInt(raw, 10) : parseFloat(raw);
        if (!Number.isFinite(n)) return;
        this._emitPatch({ [field]: n });
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
        return html`
            <div class="grid">
                <div class="field">
                    <label>${this.t('llm_config_editor.provider')}</label>
                    <select
                        .value=${provider}
                        @change=${(e) => this._onString('provider', e.target.value)}
                    >
                        <option value="">—</option>
                        ${PROVIDERS.map((p) => html`<option value=${p} ?selected=${provider === p}>${p}</option>`)}
                    </select>
                </div>
                <div class="field">
                    <label>${this.t('llm_config_editor.model')}</label>
                    ${models.length > 0
                        ? html`<select
                            .value=${model}
                            @change=${(e) => this._onString('model', e.target.value)}
                          >
                            <option value="">—</option>
                            ${models.map((m) => {
                                const value = typeof m === 'string' ? m : (m.value || m.id || '');
                                const label = typeof m === 'string' ? m : (m.label || m.value || m.id);
                                return html`<option value=${value} ?selected=${value === model}>${label}</option>`;
                            })}
                          </select>`
                        : html`<input
                            type="text"
                            .value=${model}
                            @input=${(e) => this._onString('model', e.target.value)}
                          />`}
                </div>
                <div class="field">
                    <label>${this.t('llm_config_editor.temperature')}</label>
                    <input
                        type="number" min="0" max="2" step="0.1"
                        .value=${this._readNumberOrEmpty('temperature')}
                        @input=${(e) => this._onNumber('temperature', e.target.value)}
                    />
                </div>
                <div class="field">
                    <label>${this.t('llm_config_editor.max_tokens')}</label>
                    <input
                        type="number" min="0" step="1"
                        .value=${this._readNumberOrEmpty('max_tokens')}
                        @input=${(e) => this._onNumber('max_tokens', e.target.value, true)}
                    />
                </div>
            </div>

            <details ?open=${this._showAdvanced} @toggle=${(e) => { this._showAdvanced = e.target.open; }}>
                <summary>${this.t('llm_config_editor.advanced')}</summary>
                <div class="grid">
                    <div class="field full">
                        <label>${this.t('llm_config_editor.api_key')}</label>
                        <input
                            type="password"
                            autocomplete="off"
                            placeholder="@var:KEY"
                            .value=${apiKey}
                            @input=${(e) => this._onString('api_key', e.target.value)}
                        />
                    </div>
                    <div class="field full">
                        <label>${this.t('llm_config_editor.base_url')}</label>
                        <input
                            type="text"
                            placeholder="https://api.example.com/v1"
                            .value=${baseUrl}
                            @input=${(e) => this._onString('base_url', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label>${this.t('llm_config_editor.top_p')}</label>
                        <input
                            type="number" min="0" max="1" step="0.05"
                            .value=${this._readNumberOrEmpty('top_p')}
                            @input=${(e) => this._onNumber('top_p', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label>${this.t('llm_config_editor.top_k')}</label>
                        <input
                            type="number" min="0" step="1"
                            .value=${this._readNumberOrEmpty('top_k')}
                            @input=${(e) => this._onNumber('top_k', e.target.value, true)}
                        />
                    </div>
                    <div class="field">
                        <label>${this.t('llm_config_editor.frequency_penalty')}</label>
                        <input
                            type="number" min="-2" max="2" step="0.1"
                            .value=${this._readNumberOrEmpty('frequency_penalty')}
                            @input=${(e) => this._onNumber('frequency_penalty', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label>${this.t('llm_config_editor.presence_penalty')}</label>
                        <input
                            type="number" min="-2" max="2" step="0.1"
                            .value=${this._readNumberOrEmpty('presence_penalty')}
                            @input=${(e) => this._onNumber('presence_penalty', e.target.value)}
                        />
                    </div>
                    <div class="field">
                        <label>${this.t('llm_config_editor.seed')}</label>
                        <input
                            type="number" step="1"
                            .value=${this._readNumberOrEmpty('seed')}
                            @input=${(e) => this._onNumber('seed', e.target.value, true)}
                        />
                    </div>
                    <div class="field">
                        <label>${this.t('llm_config_editor.reasoning_effort')}</label>
                        <select
                            .value=${reasoning}
                            @change=${(e) => this._onString('reasoning_effort', e.target.value)}
                        >
                            ${REASONING_LEVELS.map((lv) => html`<option value=${lv} ?selected=${reasoning === lv}>${lv === '' ? '—' : lv}</option>`)}
                        </select>
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
