/**
 * flows-breakpoint-manager — индикатор брейкпоинтов на текущем flow.
 *
 * Реагирует на push `flows/chat/breakpoint` и обновляет previewExecutionState
 * через useOp('flows/editor').setPreviewExecutionState. Сам список breakpoints
 * хранит локально и пробрасывает в metadata.breakpoints команды send.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class FlowsBreakpointManager extends PlatformElement {
    static properties = {
        flowId: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; padding: var(--space-2); font-size: var(--text-sm); color: var(--text-secondary); }
            .empty { color: var(--text-tertiary); }
            .bp { display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px; border-radius: var(--radius-sm); background: var(--warning-subtle, var(--glass-solid-medium)); color: var(--warning); margin-right: var(--space-1); }
            button { background: transparent; border: none; color: inherit; cursor: pointer; }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this._editor = this.useOp('flows/editor');
        this.useEvent('flows/chat/breakpoint', (event) => {
            const payload = event?.payload;
            if (!payload) return;
            this._editor.setPreviewExecutionState({ snapshot: payload.breakpoint?.state || null });
        });
    }

    render() {
        const state = this._editor.state || {};
        const preview = state.previewExecutionState;
        const breakpoints = preview?.breakpoints || [];
        if (breakpoints.length === 0) {
            return html`<div class="empty">${this.t('breakpoint_manager.empty')}</div>`;
        }
        return html`
            <span>${this.t('breakpoint_manager.title')}:</span>
            ${breakpoints.map((bp) => html`<span class="bp">${bp.node_id || bp}</span>`)}
        `;
    }
}

customElements.define('flows-breakpoint-manager', FlowsBreakpointManager);
