/**
 * flows-base-node-editor — общая обёртка для редакторов нод.
 *
 * Предоставляет:
 *   - заголовок (name + type badge);
 *   - табы Settings / Input / Output / Test;
 *   - вкладка Test использует <flows-test-panel>;
 *   - вкладки Input/Output — <flows-state-mapping-editor> над `input_mapping`/`output_mapping`.
 *
 * Конкретные ноды наследуют через slot 'settings'.
 *
 * Save → emit('change', { patch }) родителю; родитель сам пишет в
 * useResource('flows/flows').update / useOp('flows/flow_update').
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '../editors/flows-state-mapping-editor.js';
import '../editors/flows-test-panel.js';

const TABS = ['settings', 'input', 'output', 'test'];

export class FlowsBaseNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        _tab: { state: true },
        _name: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; padding: var(--space-3); color: var(--text-primary); }
            .header {
                display: flex; align-items: center; gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            .header input {
                flex: 1; padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            .badge {
                padding: 2px 8px; font-size: var(--text-xs);
                border-radius: var(--radius-sm);
                background: var(--accent-subtle); color: var(--accent);
            }
            .tabs { display: flex; gap: var(--space-1); border-bottom: 1px solid var(--border-subtle); margin-bottom: var(--space-3); }
            .tab {
                padding: var(--space-2) var(--space-3); cursor: pointer;
                border-bottom: 2px solid transparent;
                color: var(--text-secondary); font-size: var(--text-sm);
            }
            .tab[active] { border-color: var(--accent); color: var(--accent); }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
        this.nodeType = '';
        this._tab = 'settings';
        this._name = '';
        this._hydrated = false;
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.nodeConfig) {
            this._name = this.nodeConfig.name || this.nodeId;
            this.nodeType = this.nodeConfig.type || this.nodeType;
            this._hydrated = true;
        }
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onName(e) {
        this._name = e.target.value;
        this._emitPatch({ name: this._name });
    }

    _onMapping(field, e) {
        this._emitPatch({ [field]: e.detail?.mapping || {} });
    }

    _renderTab() {
        if (this._tab === 'settings') {
            return html`<slot name="settings"></slot>`;
        }
        if (this._tab === 'input') {
            return html`
                <flows-state-mapping-editor
                    .mapping=${this.nodeConfig?.input_mapping || {}}
                    @change=${(e) => this._onMapping('input_mapping', e)}
                ></flows-state-mapping-editor>
            `;
        }
        if (this._tab === 'output') {
            return html`
                <flows-state-mapping-editor
                    .mapping=${this.nodeConfig?.output_mapping || {}}
                    @change=${(e) => this._onMapping('output_mapping', e)}
                ></flows-state-mapping-editor>
            `;
        }
        return html`
            <flows-test-panel
                .nodeType=${this.nodeType}
                .nodeConfig=${this.nodeConfig || {}}
                .flowId=${this.flowId}
                .skillId=${this.skillId || 'base'}
            ></flows-test-panel>
        `;
    }

    render() {
        if (!this.nodeConfig) return html`<div>${this.t('property_panel.select_node')}</div>`;
        return html`
            <div class="header">
                <input type="text" .value=${this._name} @input=${this._onName} />
                <span class="badge">${this.nodeType}</span>
            </div>
            <div class="tabs">
                ${TABS.map((t) => html`
                    <div class="tab" ?active=${this._tab === t} @click=${() => { this._tab = t; }}>
                        ${this.t(`base_node_editor.tab_${t}`)}
                    </div>
                `)}
            </div>
            <div class="body">${this._renderTab()}</div>
        `;
    }
}

customElements.define('flows-base-node-editor', FlowsBaseNodeEditor);
