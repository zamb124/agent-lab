/**
 * flows-bottom-toolbar — undo/redo, активный tool, индикаторы.
 *
 * Actions фабрики `flows/editor`: undo/redo/setActiveTool.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

const TOOLS = Object.freeze(['select', 'pan']);

export class FlowsBottomToolbar extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-top: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
            }
            .spacer { flex: 1; }
            .tool-btn[active] { background: var(--accent-subtle); color: var(--accent); }
        `,
    ];

    constructor() {
        super();
        this._editor = this.useOp('flows/editor');
    }

    _undo() { this._editor.undo({}); }
    _redo() { this._editor.redo({}); }
    _setTool(tool) { this._editor.setActiveTool({ tool }); }

    render() {
        const state = this._editor.state || {};
        const activeTool = state.activeTool || 'select';
        return html`
            <platform-button class="tool-btn" ?disabled=${!state.canUndo} @click=${this._undo}>
                <platform-icon name="undo" size="16"></platform-icon>
                ${this.t('bottom_toolbar.undo')}
            </platform-button>
            <platform-button class="tool-btn" ?disabled=${!state.canRedo} @click=${this._redo}>
                <platform-icon name="redo" size="16"></platform-icon>
                ${this.t('bottom_toolbar.redo')}
            </platform-button>
            <span class="spacer"></span>
            ${TOOLS.map((t) => html`
                <platform-button class="tool-btn" ?active=${activeTool === t} @click=${() => this._setTool(t)}>
                    ${this.t(`bottom_toolbar.tool_${t}`)}
                </platform-button>
            `)}
        `;
    }
}

customElements.define('flows-bottom-toolbar', FlowsBottomToolbar);
