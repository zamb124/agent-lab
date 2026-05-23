import { html, css, nothing } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../fields/platform-field.js';
import '../glass-button.js';

const PROFILE_VALUES = Object.freeze(['off', 'compact', 'standard', 'agent']);
const MODE_VALUES = Object.freeze(['off', 'window', 'smart', 'agent']);
const BUDGET_VALUES = Object.freeze(['tiny', 'small', 'medium', 'large', 'max']);
const MEMORY_VALUES = Object.freeze(['off', 'session', 'node', 'flow', 'company']);
const RETRIEVAL_VALUES = Object.freeze(['off', 'semantic', 'lexical', 'hybrid']);
const COMPACTION_VALUES = Object.freeze(['off', 'auto', 'force']);
const CACHE_VALUES = Object.freeze(['off', 'auto', 'provider_hints']);
const BUDGET_CUSTOM_VALUE = '__custom__';
const BUDGET_TOKEN_FIELDS = Object.freeze([
    'max_input_tokens',
    'active_window_tokens',
    'memory_tokens',
    'rag_tokens',
    'tool_result_tokens',
    'output_reserve_tokens',
    'reasoning_reserve_tokens',
    'safety_buffer_tokens',
]);

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function clonePatch(value) {
    if (!isObject(value)) return {};
    return JSON.parse(JSON.stringify(value));
}

function enumConfig(values, inheritLabel) {
    const items = [{ value: '', label: inheritLabel }];
    for (const value of values) {
        items.push({ value, label: value });
    }
    return { values: items };
}

function budgetEnumConfig(values, inheritLabel, customLabel, includeCustom) {
    const config = enumConfig(values, inheritLabel);
    if (includeCustom) {
        config.values.push({ value: BUDGET_CUSTOM_VALUE, label: customLabel });
    }
    return config;
}

function cleanObject(value) {
    const next = {};
    for (const [key, raw] of Object.entries(value)) {
        if (raw === undefined || raw === null || raw === '') continue;
        if (isObject(raw)) {
            const inner = cleanObject(raw);
            if (Object.keys(inner).length > 0) next[key] = inner;
            continue;
        }
        next[key] = raw;
    }
    return next;
}

function retrievalPatch(config) {
    const raw = config.retrieval;
    if (typeof raw === 'string') return { mode: raw };
    return isObject(raw) ? { ...raw } : {};
}

function budgetPatch(config) {
    return isObject(config.budget) ? { ...config.budget } : {};
}

function clampNumber(value, min, max) {
    return Math.min(max, Math.max(min, value));
}

export class PlatformLlmContextEditor extends PlatformElement {
    static properties = {
        config: { type: Object },
        profiles: { type: Array },
        budgets: { type: Array },
        compact: { type: Boolean, reflect: true },
        clearable: { type: Boolean },
        _advanced: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
            }

            .stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: var(--space-2);
                min-width: 0;
            }

            :host([compact]) .grid {
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            }

            .actions {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .advanced {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
            }

            .advanced-group {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
            }

            .advanced-title {
                margin: 0;
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.config = {};
        this.profiles = [];
        this.budgets = [];
        this.compact = false;
        this.clearable = false;
        this._advanced = false;
    }

    _patch() {
        return clonePatch(this.config);
    }

    _emitConfig(config) {
        this.emit('change', { config: cleanObject(config) });
    }

    _setTopLevel(key, value) {
        const next = this._patch();
        if (value === '') {
            delete next[key];
        } else {
            next[key] = value;
        }
        this._emitConfig(next);
    }

    _setRetrieval(key, value) {
        const next = this._patch();
        const retrieval = retrievalPatch(next);
        if (value === '' || value === null || value === undefined) {
            delete retrieval[key];
        } else {
            retrieval[key] = value;
        }
        if (key === 'rerank' && value === true && (!retrieval.mode || retrieval.mode === 'off')) {
            retrieval.mode = 'hybrid';
        }
        if (retrieval.mode === 'off' && retrieval.rerank === true) {
            retrieval.rerank = false;
        }
        if (Object.keys(cleanObject(retrieval)).length === 0) {
            delete next.retrieval;
        } else {
            next.retrieval = cleanObject(retrieval);
        }
        this._emitConfig(next);
    }

    _setBudget(key, value) {
        const next = this._patch();
        const budget = budgetPatch(next);
        if (value === '' || value === null || value === undefined) {
            delete budget[key];
        } else {
            budget[key] = value;
        }
        const cleaned = cleanObject(budget);
        if (Object.keys(cleaned).length === 0) {
            delete next.budget;
        } else {
            next.budget = cleaned;
        }
        this._emitConfig(next);
    }

    _onEnum(key) {
        return (e) => {
            const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
            this._setTopLevel(key, value);
        };
    }

    _onBudgetPreset(e) {
        const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
        if (value === BUDGET_CUSTOM_VALUE) {
            return;
        }
        this._setTopLevel('budget', value);
    }

    _onRetrievalEnum(key) {
        return (e) => {
            const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
            this._setRetrieval(key, value);
        };
    }

    _onRetrievalNumber(key) {
        return (e) => {
            const raw = e.detail?.value;
            let value = typeof raw === 'number' && Number.isFinite(raw) ? raw : null;
            if (value !== null && key === 'top_k') {
                value = clampNumber(Math.round(value), 1, 256);
            }
            if (value !== null && key === 'min_score') {
                value = clampNumber(value, 0, 1);
            }
            this._setRetrieval(key, value);
        };
    }

    _onBudgetNumber(key) {
        return (e) => {
            const raw = e.detail?.value;
            let value = typeof raw === 'number' && Number.isFinite(raw) ? Math.round(raw) : null;
            if (value !== null) {
                value = key === 'max_input_tokens'
                    ? Math.max(1, value)
                    : Math.max(0, value);
            }
            this._setBudget(key, value);
        };
    }

    _onRetrievalBool(key) {
        return (e) => {
            const value = e.detail?.value === true;
            this._setRetrieval(key, value);
        };
    }

    _clear() {
        this.emit('clear', {});
        this._emitConfig({});
    }

    render() {
        const patch = this._patch();
        const retrieval = retrievalPatch(patch);
        const budgetPatchValue = budgetPatch(patch);
        const hasCustomBudget = isObject(patch.budget);
        const inherit = this.t('llm_context_editor.inherit');
        const profile = typeof patch.profile === 'string' ? patch.profile : '';
        const mode = typeof patch.mode === 'string' ? patch.mode : '';
        const budget = typeof patch.budget === 'string'
            ? patch.budget
            : (hasCustomBudget ? BUDGET_CUSTOM_VALUE : '');
        const memory = typeof patch.memory === 'string' ? patch.memory : '';
        const retrievalMode = typeof retrieval.mode === 'string' ? retrieval.mode : '';
        const topK = typeof retrieval.top_k === 'number' ? retrieval.top_k : null;
        const minScore = typeof retrieval.min_score === 'number' ? retrieval.min_score : null;
        const rerank = retrieval.rerank === true;
        const compaction = typeof patch.compaction === 'string' ? patch.compaction : '';
        const cache = typeof patch.cache === 'string' ? patch.cache : '';
        const profileValues = Array.isArray(this.profiles) && this.profiles.length > 0
            ? this.profiles
            : PROFILE_VALUES;
        const budgetValues = Array.isArray(this.budgets) && this.budgets.length > 0
            ? this.budgets
            : BUDGET_VALUES;

        return html`
            <div class="stack">
                <div class="grid">
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('llm_context_editor.profile')}
                        .value=${profile}
                        .config=${enumConfig(profileValues, inherit)}
                        @change=${this._onEnum('profile')}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('llm_context_editor.memory')}
                        .value=${memory}
                        .config=${enumConfig(MEMORY_VALUES, inherit)}
                        @change=${this._onEnum('memory')}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('llm_context_editor.retrieval')}
                        .value=${retrievalMode}
                        .config=${enumConfig(RETRIEVAL_VALUES, inherit)}
                        @change=${this._onRetrievalEnum('mode')}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('llm_context_editor.budget')}
                        .value=${budget}
                        .config=${budgetEnumConfig(
                            budgetValues,
                            inherit,
                            this.t('llm_context_editor.custom_budget'),
                            hasCustomBudget,
                        )}
                        @change=${this._onBudgetPreset}
                    ></platform-field>
                </div>

                <div class="actions">
                    <glass-button
                        size="sm"
                        variant="ghost"
                        type="button"
                        @click=${() => { this._advanced = !this._advanced; }}
                    >
                        ${this._advanced
                            ? this.t('llm_context_editor.hide_advanced')
                            : this.t('llm_context_editor.show_advanced')}
                    </glass-button>
                    ${this.clearable
                        ? html`
                            <glass-button size="sm" variant="ghost" type="button" @click=${this._clear}>
                                ${this.t('llm_context_editor.clear')}
                            </glass-button>
                        `
                        : nothing}
                </div>

                ${this._advanced
                    ? html`
                        <div class="advanced">
                            <div class="advanced-group">
                                <h5 class="advanced-title">${this.t('llm_context_editor.advanced_retrieval')}</h5>
                                <div class="grid">
                                    <platform-field
                                        type="enum"
                                        mode="edit"
                                        .label=${this.t('llm_context_editor.mode')}
                                        .value=${mode}
                                        .config=${enumConfig(MODE_VALUES, inherit)}
                                        @change=${this._onEnum('mode')}
                                    ></platform-field>
                                    <platform-field
                                        type="integer"
                                        mode="edit"
                                        .label=${this.t('llm_context_editor.top_k')}
                                        .value=${topK}
                                        @change=${this._onRetrievalNumber('top_k')}
                                    ></platform-field>
                                    <platform-field
                                        type="number"
                                        mode="edit"
                                        .label=${this.t('llm_context_editor.min_score')}
                                        .value=${minScore}
                                        @change=${this._onRetrievalNumber('min_score')}
                                    ></platform-field>
                                    <platform-field
                                        type="boolean"
                                        mode="edit"
                                        .label=${this.t('llm_context_editor.rerank')}
                                        .value=${rerank}
                                        @change=${this._onRetrievalBool('rerank')}
                                    ></platform-field>
                                    <platform-field
                                        type="enum"
                                        mode="edit"
                                        .label=${this.t('llm_context_editor.compaction')}
                                        .value=${compaction}
                                        .config=${enumConfig(COMPACTION_VALUES, inherit)}
                                        @change=${this._onEnum('compaction')}
                                    ></platform-field>
                                    <platform-field
                                        type="enum"
                                        mode="edit"
                                        .label=${this.t('llm_context_editor.cache')}
                                        .value=${cache}
                                        .config=${enumConfig(CACHE_VALUES, inherit)}
                                        @change=${this._onEnum('cache')}
                                    ></platform-field>
                                </div>
                            </div>
                            <div class="advanced-group">
                                <h5 class="advanced-title">${this.t('llm_context_editor.advanced_budget')}</h5>
                                <div class="grid">
                                    ${BUDGET_TOKEN_FIELDS.map((key) => html`
                                        <platform-field
                                            type="integer"
                                            mode="edit"
                                            .label=${this.t(`llm_context_editor.${key}`)}
                                            .value=${typeof budgetPatchValue[key] === 'number' ? budgetPatchValue[key] : null}
                                            @change=${this._onBudgetNumber(key)}
                                        ></platform-field>
                                    `)}
                                </div>
                            </div>
                        </div>
                    `
                    : nothing}
            </div>
        `;
    }
}

customElements.define('platform-llm-context-editor', PlatformLlmContextEditor);
