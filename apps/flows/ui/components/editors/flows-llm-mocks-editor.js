/**
 * flows-llm-mocks-editor — таблица mock-ответов для LLM в тестовом режиме.
 *
 * Каждая строка: { match: string, response: string }. emit('change', { mocks: [...] }).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class FlowsLlmMocksEditor extends PlatformElement {
    static properties = {
        mocks: { type: Array },
        _rows: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .row {
                display: grid; grid-template-columns: 1fr 2fr auto;
                gap: var(--space-2); margin-bottom: var(--space-2); align-items: start;
            }
            .row input, .row textarea {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
            .row textarea { min-height: 64px; resize: vertical; }
            button {
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary); cursor: pointer;
            }
            button:hover { background: var(--glass-solid-medium); color: var(--text-primary); }
            .empty { color: var(--text-tertiary); font-size: var(--text-sm); padding: var(--space-2); }
        `,
    ];

    constructor() {
        super();
        this.mocks = [];
        this._rows = [];
        this._hydrated = false;
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && Array.isArray(this.mocks)) {
            this._rows = this.mocks.map((m) => ({
                match: typeof m?.match === 'string' ? m.match : '',
                response: typeof m?.response === 'string' ? m.response : '',
            }));
            this._hydrated = true;
        }
    }

    _emitChange() {
        const mocks = this._rows
            .filter((r) => r.match.trim() || r.response.trim())
            .map((r) => ({ match: r.match, response: r.response }));
        this.emit('change', { mocks });
    }

    _addRow() {
        this._rows = [...this._rows, { match: '', response: '' }];
    }

    _removeRow(i) {
        this._rows = this._rows.filter((_, idx) => idx !== i);
        this._emitChange();
    }

    _updateRow(i, field, v) {
        this._rows = this._rows.map((r, idx) => (idx === i ? { ...r, [field]: v } : r));
        this._emitChange();
    }

    render() {
        return html`
            ${this._rows.length === 0
                ? html`<div class="empty">${this.t('llm_mocks_editor.empty')}</div>`
                : this._rows.map((r, i) => html`
                    <div class="row">
                        <input
                            type="text"
                            placeholder=${this.t('llm_mocks_editor.placeholder_match')}
                            .value=${r.match}
                            @input=${(e) => this._updateRow(i, 'match', e.target.value)}
                        />
                        <textarea
                            placeholder=${this.t('llm_mocks_editor.placeholder_response')}
                            .value=${r.response}
                            @input=${(e) => this._updateRow(i, 'response', e.target.value)}
                        ></textarea>
                        <button type="button" @click=${() => this._removeRow(i)}>×</button>
                    </div>
                `)}
            <button type="button" @click=${this._addRow}>+ ${this.t('llm_mocks_editor.add')}</button>
        `;
    }
}

customElements.define('flows-llm-mocks-editor', FlowsLlmMocksEditor);
