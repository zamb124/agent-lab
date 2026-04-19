/**
 * flows-state-mapping-editor — таблица маппинга {param: source}.
 *
 * Source поддерживает синтаксис @state:..., @var:..., константа.
 * emit('change', { mapping }).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class FlowsStateMappingEditor extends PlatformElement {
    static properties = {
        mapping: { type: Object },
        title: { type: String },
        _rows: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .row {
                display: flex; gap: var(--space-2); align-items: center; margin-bottom: var(--space-2);
            }
            .row input {
                flex: 1; padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
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
        this.mapping = null;
        this.title = '';
        this._rows = [];
        this._hydrated = false;
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.mapping && typeof this.mapping === 'object') {
            this._rows = Object.entries(this.mapping).map(([k, v]) => ({ key: k, value: String(v) }));
            this._hydrated = true;
        }
    }

    _emitChange() {
        const mapping = {};
        for (const r of this._rows) {
            const k = r.key.trim();
            if (!k) continue;
            mapping[k] = r.value;
        }
        this.emit('change', { mapping });
    }

    _addRow() {
        this._rows = [...this._rows, { key: '', value: '' }];
    }

    _removeRow(idx) {
        this._rows = this._rows.filter((_, i) => i !== idx);
        this._emitChange();
    }

    _updateRow(idx, field, value) {
        this._rows = this._rows.map((r, i) => (i === idx ? { ...r, [field]: value } : r));
        this._emitChange();
    }

    render() {
        return html`
            ${this.title ? html`<div style="margin-bottom: var(--space-1)">${this.title}</div>` : ''}
            ${this._rows.length === 0
                ? html`<div class="empty">${this.t('state_mapping_editor.empty')}</div>`
                : this._rows.map((r, i) => html`
                    <div class="row">
                        <input
                            type="text"
                            placeholder=${this.t('state_mapping_editor.placeholder_param')}
                            .value=${r.key}
                            @input=${(e) => this._updateRow(i, 'key', e.target.value)}
                        />
                        <input
                            type="text"
                            placeholder=${this.t('state_mapping_editor.placeholder_source')}
                            .value=${r.value}
                            @input=${(e) => this._updateRow(i, 'value', e.target.value)}
                        />
                        <button type="button" @click=${() => this._removeRow(i)}>×</button>
                    </div>
                `)}
            <button type="button" @click=${this._addRow}>+ ${this.t('state_mapping_editor.add')}</button>
        `;
    }
}

customElements.define('flows-state-mapping-editor', FlowsStateMappingEditor);
