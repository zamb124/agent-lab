/**
 * platform-variable-input — string input with @var:NAME autocomplete from company variables + system catalog.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { listSystemVariableKeys } from './variables/platform-system-variables-catalog.js';

/**
 * @param {unknown} value
 * @returns {string}
 */
function _asString(value) {
    if (typeof value === 'string') {
        return value;
    }
    if (value === null || value === undefined) {
        return '';
    }
    return String(value);
}

/**
 * @param {unknown} value
 * @returns {unknown[]}
 */
function _asArray(value) {
    if (!Array.isArray(value)) {
        throw new TypeError('platform-variable-input: expected array');
    }
    return value;
}

/**
 * @param {{ source: string, secret?: boolean, expression?: boolean, scoped?: boolean }} item
 * @returns {string}
 */
function _badgeLabel(item) {
    if (item.source === 'system') {
        return 'system';
    }
    if (item.secret) {
        return 'secret';
    }
    if (item.expression) {
        return 'expr';
    }
    if (item.scoped) {
        return 'scoped';
    }
    return '';
}

export class PlatformVariableInput extends PlatformElement {
    static properties = {
        value: { type: String },
        placeholder: { type: String },
        _suggestions: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                position: relative;
            }
            input {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--field-pill-border, var(--glass-border-subtle));
                background: var(--field-pill-bg, var(--glass-solid-subtle));
                color: var(--text-primary);
                font: inherit;
            }
            input:focus {
                border-color: var(--accent);
                box-shadow: var(--focus-ring);
                outline: none;
            }
            .suggestions {
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                background: var(--glass-solid-strong);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                z-index: 10;
                max-height: 200px;
                overflow-y: auto;
            }
            .suggestion {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-1) var(--space-2);
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .suggestion:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .badge {
                font-size: var(--text-xs);
                padding: 1px 5px;
                border-radius: var(--radius-sm);
                border: 1px solid var(--glass-border-subtle);
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.placeholder = '';
        this._suggestions = [];
        this._variables = this.useResource('secrets/variables', { autoload: true });
    }

    _catalogItems() {
        const companyItems = _asArray(this._variables.items).map((item) => {
            const payload = item.payload;
            const base = payload && typeof payload === 'object' ? payload.base : null;
            const expression = base && typeof base === 'object' && base.value_kind === 'expression';
            const scopes = payload && typeof payload === 'object' ? payload.scopes : null;
            const scoped = Array.isArray(scopes) && scopes.length > 0;
            return {
                key: item.variable_key,
                secret: Boolean(item.secret),
                expression: Boolean(expression),
                scoped,
                source: 'company',
            };
        });
        const systemItems = listSystemVariableKeys().map((key) => ({
            key,
            secret: false,
            expression: false,
            scoped: false,
            source: 'system',
        }));
        return [...companyItems, ...systemItems];
    }

    _onInput(e) {
        const target = e.target;
        const v = target && 'value' in target ? _asString(target.value) : '';
        this.value = v;
        this.emit('change', { value: v });
        const last = v.match(/@var:([A-Za-z0-9_]*)$/);
        if (last) {
            const prefix = last[1].toLowerCase();
            const items = this._catalogItems()
                .filter((item) => item.key.toLowerCase().startsWith(prefix))
                .slice(0, 10);
            this._suggestions = items;
        } else {
            this._suggestions = [];
        }
    }

    _select(item) {
        this.value = this.value.replace(/@var:[A-Za-z0-9_]*$/, `@var:${item.key}`);
        this._suggestions = [];
        this.emit('change', { value: this.value });
    }

    render() {
        return html`
            <input
                class="field-pill-input"
                data-canon="search-as-you-type"
                type="text"
                .value=${this.value}
                placeholder=${this.placeholder}
                @input=${this._onInput}
            />
            ${this._suggestions.length > 0
                ? html`
                    <div class="suggestions">
                        ${this._suggestions.map((item) => html`
                            <div class="suggestion" @mousedown=${() => this._select(item)}>
                                <span>@var:${item.key}</span>
                                ${(() => {
                                    const badge = _badgeLabel(item);
                                    return badge ? html`<span class="badge">${badge}</span>` : '';
                                })()}
                            </div>
                        `)}
                    </div>
                `
                : ''}
        `;
    }
}

customElements.define('platform-variable-input', PlatformVariableInput);
