/**
 * platform-variables-panel — inline редактор VariableMap { key: { value, secret, ... } }.
 */

import { html, css, nothing } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';
import './fields/platform-field.js';

function _normalizeEntry(raw) {
    if (raw === null || raw === undefined) {
        return { value: '', secret: false };
    }
    if (typeof raw === 'object' && !Array.isArray(raw) && 'value' in raw) {
        return {
            value: raw.value,
            secret: Boolean(raw.secret),
            public: Boolean(raw.public),
            title: typeof raw.title === 'string' ? raw.title : undefined,
            description: typeof raw.description === 'string' ? raw.description : undefined,
        };
    }
    return { value: raw, secret: false };
}

function _stringifyValue(entry) {
    if (!entry || typeof entry !== 'object') {
        return '';
    }
    if (entry.secret) {
        return '***';
    }
    return _editValue(entry);
}

function _editValue(entry) {
    if (!entry || typeof entry !== 'object') {
        return '';
    }
    const value = entry.value;
    if (value === null || value === undefined) {
        return '';
    }
    if (typeof value === 'string') {
        return value;
    }
    return JSON.stringify(value);
}

export function variableMapToPromptValues(variables) {
    if (!variables || typeof variables !== 'object' || Array.isArray(variables)) {
        return {};
    }
    const promptValues = {};
    for (const [key, raw] of Object.entries(variables)) {
        const entry = _normalizeEntry(raw);
        promptValues[key] = entry.value;
    }
    return promptValues;
}

export class PlatformVariablesPanel extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        variables: { type: Object, attribute: false },
        readonly: { type: Boolean, reflect: true },
        compact: { type: Boolean, reflect: true },
        sectionTitle: { type: String, attribute: 'section-title' },
    };

    static styles = css`
        :host {
            display: block;
        }
        .section-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: var(--space-2);
            margin-bottom: var(--space-2);
        }
        .section-title {
            font-size: var(--text-xs);
            font-weight: var(--font-semibold);
            color: var(--text-tertiary);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin: 0;
            min-width: 0;
        }
        .add-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            flex-shrink: 0;
            border: none;
            border-radius: var(--radius-sm);
            background: transparent;
            color: var(--text-secondary);
            cursor: pointer;
        }
        .add-btn:hover {
            background: var(--glass-tint-medium);
            color: var(--text-primary);
        }
        .rows {
            display: flex;
            flex-direction: column;
            gap: var(--space-2);
        }
        .row {
            display: grid;
            grid-template-columns: minmax(72px, 0.9fr) minmax(0, 1.6fr) auto auto;
            gap: var(--space-2);
            align-items: center;
        }
        .field-key,
        .field-value {
            min-width: 0;
        }
        .field-key platform-field,
        .field-value platform-field {
            width: 100%;
        }
        .field-value platform-field {
            --field-pill-bg: var(--glass-solid-subtle);
            --field-pill-border: 1px solid var(--glass-border-subtle);
            --field-pill-padding-x: var(--space-2);
            --field-pill-padding-y: var(--space-1);
            --field-pill-radius: var(--radius-sm);
            --field-pill-input-size: var(--text-sm);
        }
        .field-value platform-field:focus-within {
            --field-pill-bg: var(--glass-tint-medium);
            --field-pill-border: 1px solid var(--accent-subtle);
        }
        .field-key platform-field {
            --field-pill-input-size: var(--text-sm);
            --field-pill-input-color: var(--text-secondary);
        }
        .secret-toggle {
            border: 0;
            background: transparent;
            color: var(--text-tertiary);
            cursor: pointer;
            padding: var(--space-1);
            border-radius: var(--radius-sm);
        }
        .secret-toggle[aria-pressed="true"] {
            color: var(--accent);
        }
        .empty {
            font-size: var(--text-sm);
            color: var(--text-tertiary);
        }
    `;

    constructor() {
        super();
        this.variables = {};
        this.readonly = false;
        this.compact = false;
        this.sectionTitle = '';
        this._valueDrafts = {};
        this._keyDrafts = {};
    }

    _displayKey(key) {
        if (Object.prototype.hasOwnProperty.call(this._keyDrafts, key)) {
            return this._keyDrafts[key];
        }
        return key;
    }

    _displayValue(key, entry) {
        if (Object.prototype.hasOwnProperty.call(this._valueDrafts, key)) {
            return this._valueDrafts[key];
        }
        if (entry.secret && this.readonly) {
            return _stringifyValue(entry);
        }
        return _editValue(entry);
    }

    _setValueDraft(key, value) {
        if (typeof key !== 'string' || typeof value !== 'string') {
            return;
        }
        this._valueDrafts = { ...this._valueDrafts, [key]: value };
        this.requestUpdate();
    }

    _setKeyDraft(key, value) {
        if (typeof key !== 'string' || typeof value !== 'string') {
            return;
        }
        this._keyDrafts = { ...this._keyDrafts, [key]: value };
        this.requestUpdate();
    }

    _commitValueDraft(key) {
        if (!Object.prototype.hasOwnProperty.call(this._valueDrafts, key)) {
            return;
        }
        const value = this._valueDrafts[key];
        const nextDrafts = { ...this._valueDrafts };
        delete nextDrafts[key];
        this._valueDrafts = nextDrafts;
        const current = _editValue(_normalizeEntry(this.variables[key]));
        if (value !== current) {
            this._updateValue(key, value);
        }
    }

    _commitKeyDraft(key) {
        if (!Object.prototype.hasOwnProperty.call(this._keyDrafts, key)) {
            return;
        }
        const value = this._keyDrafts[key];
        const nextDrafts = { ...this._keyDrafts };
        delete nextDrafts[key];
        this._keyDrafts = nextDrafts;
        this._updateKey(key, value);
    }

    _commitRowDrafts(key) {
        this._commitValueDraft(key);
        this._commitKeyDraft(key);
    }

    /** @param {FocusEvent} e */
    _onFieldFocusOut(key, container, commitFn, e) {
        const relatedTarget = e.relatedTarget;
        if (relatedTarget instanceof Node && container.contains(relatedTarget)) {
            return;
        }
        commitFn.call(this, key);
    }

    _emitChange(nextVariables) {
        this.emit('variables-change', { variables: nextVariables });
    }

    _entries() {
        if (!this.variables || typeof this.variables !== 'object' || Array.isArray(this.variables)) {
            return [];
        }
        return Object.entries(this.variables).map(([key, raw]) => ({
            key,
            entry: _normalizeEntry(raw),
        }));
    }

    _updateKey(oldKey, newKey) {
        if (typeof oldKey !== 'string' || typeof newKey !== 'string') {
            return;
        }
        const trimmed = newKey.trim();
        if (!trimmed || trimmed === oldKey) {
            return;
        }
        const next = { ...this.variables };
        if (trimmed in next) {
            return;
        }
        next[trimmed] = next[oldKey];
        delete next[oldKey];
        if (Object.prototype.hasOwnProperty.call(this._valueDrafts, oldKey)) {
            const nextValueDrafts = { ...this._valueDrafts };
            nextValueDrafts[trimmed] = nextValueDrafts[oldKey];
            delete nextValueDrafts[oldKey];
            this._valueDrafts = nextValueDrafts;
        }
        this._emitChange(next);
    }

    _updateValue(key, value) {
        const next = { ...this.variables };
        const entry = _normalizeEntry(next[key]);
        entry.value = value;
        next[key] = entry;
        this._emitChange(next);
    }

    _toggleSecret(key) {
        this._commitRowDrafts(key);
        const next = { ...this.variables };
        const entry = _normalizeEntry(next[key]);
        entry.secret = !entry.secret;
        next[key] = entry;
        this._emitChange(next);
    }

    _remove(key) {
        this._commitRowDrafts(key);
        const next = { ...this.variables };
        delete next[key];
        const nextValueDrafts = { ...this._valueDrafts };
        delete nextValueDrafts[key];
        this._valueDrafts = nextValueDrafts;
        const nextKeyDrafts = { ...this._keyDrafts };
        delete nextKeyDrafts[key];
        this._keyDrafts = nextKeyDrafts;
        this._emitChange(next);
    }

    _add() {
        const next = { ...this.variables };
        let index = 1;
        let candidate = 'var';
        while (candidate in next) {
            candidate = `var_${index}`;
            index += 1;
        }
        next[candidate] = { value: '', secret: false };
        this._emitChange(next);
    }

    render() {
        const entries = this._entries();
        const sectionTitle = typeof this.sectionTitle === 'string' ? this.sectionTitle.trim() : '';
        return html`
            ${sectionTitle.length > 0 ? html`
                <div class="section-head">
                    <h4 class="section-title">${sectionTitle}</h4>
                    ${this.readonly ? nothing : html`
                        <button
                            type="button"
                            class="add-btn"
                            title=${this.t('variables_panel.add')}
                            aria-label=${this.t('variables_panel.add')}
                            @click=${() => this._add()}
                        >
                            <platform-icon name="plus" size="16"></platform-icon>
                        </button>
                    `}
                </div>
            ` : nothing}
            <div class="rows">
                ${entries.length === 0
                    ? html`<div class="empty">${this.t('variables_panel.empty')}</div>`
                    : entries.map(({ key, entry }) => html`
                        <div class="row">
                            <div
                                class="field-key"
                                @focusout=${(e) => this._onFieldFocusOut(key, e.currentTarget, this._commitKeyDraft, e)}
                            >
                                <platform-field
                                    type="string"
                                    mode="edit"
                                    pill-density="dense"
                                    pill-embed
                                    .label=${''}
                                    .value=${this._displayKey(key)}
                                    .placeholder=${this.t('variables_panel.key_placeholder')}
                                    ?disabled=${this.readonly}
                                    @change=${(e) => {
                                        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                                        this._setKeyDraft(key, value);
                                    }}
                                ></platform-field>
                            </div>
                            <div
                                class="field-value"
                                @focusout=${(e) => this._onFieldFocusOut(key, e.currentTarget, this._commitValueDraft, e)}
                            >
                                <platform-field
                                    type="string"
                                    mode="edit"
                                    pill-density="dense"
                                    .label=${''}
                                    .value=${this._displayValue(key, entry)}
                                    .placeholder=${this.t('variables_panel.value_placeholder')}
                                    input-type=${entry.secret ? 'password' : 'text'}
                                    ?disabled=${this.readonly}
                                    @change=${(e) => {
                                        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                                        this._setValueDraft(key, value);
                                    }}
                                ></platform-field>
                            </div>
                            ${this.readonly ? nothing : html`
                                <button
                                    type="button"
                                    class="secret-toggle"
                                    aria-pressed=${entry.secret ? 'true' : 'false'}
                                    title=${this.t('variables_panel.secret')}
                                    @mousedown=${() => this._commitRowDrafts(key)}
                                    @click=${() => this._toggleSecret(key)}
                                >
                                    <platform-icon name=${entry.secret ? 'lock' : 'unlock'} size="16"></platform-icon>
                                </button>
                                <button
                                    type="button"
                                    class="secret-toggle"
                                    title=${this.t('variables_panel.remove')}
                                    @mousedown=${() => this._commitRowDrafts(key)}
                                    @click=${() => this._remove(key)}
                                >
                                    <platform-icon name="trash" size="16"></platform-icon>
                                </button>
                            `}
                        </div>
                    `)}
            </div>
        `;
    }
}

customElements.define('platform-variables-panel', PlatformVariablesPanel);
