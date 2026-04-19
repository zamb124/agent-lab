/**
 * flows-llm-config-editor — форма provider/model/temperature/max_tokens.
 *
 * Список моделей — `useOp('flows/models_list')` (фильтр по provider).
 * Изменения уходят родителю через emit('change', { config }).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const PROVIDERS = Object.freeze(['openai', 'anthropic', 'openrouter', 'ya', 'sber', 'mock']);

export class FlowsLlmConfigEditor extends PlatformElement {
    static properties = {
        config: { type: Object },
        _provider: { state: true },
        _model: { state: true },
        _temperature: { state: true },
        _maxTokens: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); }
            .field input, .field select {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
        `,
    ];

    constructor() {
        super();
        this.config = null;
        this._provider = 'openai';
        this._model = '';
        this._temperature = 0.7;
        this._maxTokens = 1024;
        this._hydrated = false;
        this._models = this.useOp('flows/models_list');
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.config) {
            this._provider = this.config.provider || 'openai';
            this._model = this.config.model || '';
            this._temperature = typeof this.config.temperature === 'number' ? this.config.temperature : 0.7;
            this._maxTokens = typeof this.config.max_tokens === 'number' ? this.config.max_tokens : 1024;
            this._hydrated = true;
            void this._models.run({ provider: this._provider });
        }
    }

    _emitChange() {
        this.emit('change', {
            config: {
                provider: this._provider,
                model: this._model,
                temperature: Number(this._temperature),
                max_tokens: Number(this._maxTokens),
            },
        });
    }

    async _onProviderChange(e) {
        this._provider = e.target.value;
        await this._models.run({ provider: this._provider });
        this._emitChange();
    }

    render() {
        const result = this._models.lastResult;
        const models = Array.isArray(result?.items)
            ? result.items
            : Array.isArray(result)
                ? result
                : [];
        return html`
            <div class="grid">
                <div class="field">
                    <label>${this.t('llm_config_editor.field_provider')}</label>
                    <select .value=${this._provider} @change=${this._onProviderChange}>
                        ${PROVIDERS.map((p) => html`<option value=${p}>${p}</option>`)}
                    </select>
                </div>
                <div class="field">
                    <label>${this.t('llm_config_editor.field_model')}</label>
                    <select
                        .value=${this._model}
                        @change=${(e) => { this._model = e.target.value; this._emitChange(); }}
                    >
                        <option value="">${this.t('llm_config_editor.field_model_pick')}</option>
                        ${models.map((m) => html`<option value=${typeof m === 'string' ? m : m.value || m.id}>
                            ${typeof m === 'string' ? m : m.label || m.value || m.id}
                        </option>`)}
                    </select>
                </div>
                <div class="field">
                    <label>${this.t('llm_config_editor.field_temperature')}</label>
                    <input
                        type="number" min="0" max="2" step="0.1"
                        .value=${String(this._temperature)}
                        @input=${(e) => { this._temperature = parseFloat(e.target.value || '0'); this._emitChange(); }}
                    />
                </div>
                <div class="field">
                    <label>${this.t('llm_config_editor.field_max_tokens')}</label>
                    <input
                        type="number" min="0" step="1"
                        .value=${String(this._maxTokens)}
                        @input=${(e) => { this._maxTokens = parseInt(e.target.value || '0', 10); this._emitChange(); }}
                    />
                </div>
            </div>
        `;
    }
}

customElements.define('flows-llm-config-editor', FlowsLlmConfigEditor);
