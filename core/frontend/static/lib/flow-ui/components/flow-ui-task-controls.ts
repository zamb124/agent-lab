/**
 * Индикатор активного Task в chrome: кольцо «агент отвечает», при разрешённой отмене — стоп.
 * Событие ``task-cancel`` обрабатывает ``<platform-flow-ui>``.
 */

import { LitElement, css, html, nothing } from 'lit';
import { flowUIText, resolveFlowUILocale } from '../utils/text.js';

export class FlowUITaskControls extends LitElement {
    declare active: boolean;
    declare canCancel: boolean;
    declare locale: string;

    static override properties = {
        active: { type: Boolean },
        canCancel: { type: Boolean, attribute: 'can-cancel' },
        locale: { type: String },
    };

    static override styles = css`
        :host { display: contents; }
        button {
            position: relative; width: 36px; height: 36px; padding: 0; border-radius: 50%; cursor: pointer; box-sizing: border-box;
            display: inline-grid; place-items: center; border: 1px solid var(--flow-ui-border);
            background: color-mix(in srgb, var(--flow-ui-panel-strong, var(--flow-ui-panel)) 92%, transparent);
            color: var(--flow-ui-text); box-shadow: var(--flow-ui-panel-shadow);
        }
        button:disabled { opacity: .72; cursor: default; }
        .ring { position: absolute; inset: 5px; border-radius: 50%; border: 2px solid color-mix(in srgb, var(--flow-ui-accent) 22%, transparent); border-top-color: var(--flow-ui-accent); animation: spin .75s linear infinite; }
        .stop { position: relative; z-index: 1; width: 10px; height: 10px; border-radius: 2px; background: currentColor; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (prefers-reduced-motion: reduce) { .ring { animation-duration: 1.6s; } }
    `;

    constructor() {
        super();
        this.active = false;
        this.canCancel = false;
        this.locale = 'auto';
    }

    override render() {
        if (!this.active) return nothing;
        const locale = resolveFlowUILocale(this.locale);
        const label = flowUIText(locale, this.canCancel ? 'stop_task' : 'task_running');
        return html`<button type="button" class="task-run-control" ?disabled=${!this.canCancel} aria-label=${label} title=${label} aria-busy="true"
            @click=${() => this.dispatchEvent(new CustomEvent('task-cancel', { bubbles: true, composed: true }))}>
            <span class="ring" aria-hidden="true"></span>
            ${this.canCancel ? html`<span class="stop" aria-hidden="true"></span>` : nothing}
        </button>`;
    }
}

if (!customElements.get('flow-ui-task-controls')) customElements.define('flow-ui-task-controls', FlowUITaskControls);
