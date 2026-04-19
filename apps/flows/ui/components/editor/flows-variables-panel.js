/**
 * flows-variables-panel — переменные текущего flow.
 *
 * Источник — useResource('flows/flows').items[?].variables. Save через
 * useOp('flows/flow_update') с обновлёнными variables.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsVariablesPanel extends PlatformElement {
    static properties = {
        flowId: { type: String },
        _hydrated: { state: true },
        _rows: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; padding: var(--space-3); border-top: 1px solid var(--border-subtle); }
            .row { display: flex; gap: var(--space-2); margin-bottom: var(--space-2); }
            .row input {
                flex: 1; padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this._hydrated = false;
        this._rows = [];
        this._editor = this.useOp('flows/editor');
        this._update = this.useOp('flows/flow_update');
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated) {
            const state = this._editor.state;
            const vars = state?.flowConfig?.variables;
            if (vars) {
                this._rows = Object.entries(vars).map(([k, v]) => ({ key: k, value: typeof v === 'string' ? v : JSON.stringify(v) }));
                this._hydrated = true;
            }
        }
    }

    _addRow() {
        this._rows = [...this._rows, { key: '', value: '' }];
    }

    _removeRow(i) {
        this._rows = this._rows.filter((_, idx) => idx !== i);
    }

    async _save() {
        const variables = {};
        for (const r of this._rows) {
            const k = r.key.trim();
            if (!k) continue;
            variables[k] = r.value;
        }
        const state = this._editor.state;
        if (!state?.flowConfig) return;
        const body = { ...state.flowConfig, variables };
        await this._update.run({ flow_id: this.flowId, body });
        this._editor.updateSkillsData({ data: { ...state.skillsData, variables } });
    }

    render() {
        const state = this._editor.state || {};
        if (!state.variablesPanelOpen) return html``;
        return html`
            ${this._rows.map((r, i) => html`
                <div class="row">
                    <input
                        type="text"
                        placeholder=${this.t('variables_panel.placeholder_key')}
                        .value=${r.key}
                        @input=${(e) => { this._rows = this._rows.map((row, idx) => idx === i ? { ...row, key: e.target.value } : row); }}
                    />
                    <input
                        type="text"
                        placeholder=${this.t('variables_panel.placeholder_value')}
                        .value=${r.value}
                        @input=${(e) => { this._rows = this._rows.map((row, idx) => idx === i ? { ...row, value: e.target.value } : row); }}
                    />
                    <platform-button danger @click=${() => this._removeRow(i)}>×</platform-button>
                </div>
            `)}
            <platform-button @click=${this._addRow}>+ ${this.t('variables_panel.add')}</platform-button>
            <platform-button variant="primary" @click=${this._save}>${this.t('variables_panel.save')}</platform-button>
        `;
    }
}

customElements.define('flows-variables-panel', FlowsVariablesPanel);
