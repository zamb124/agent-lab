/**
 * WorktrackerStatePill — colored state indicator pill.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class WorktrackerStatePill extends PlatformElement {
    static i18nNamespace = 'worktracker';

    static properties = {
        state: { type: String },
        label: { type: String },
        interactive: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
            }
            .pill {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 2px 8px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                border: none;
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                font: inherit;
            }
            .pill.interactive {
                cursor: pointer;
            }
            .pill.interactive:hover {
                background: var(--glass-tint-medium);
                filter: brightness(1.05);
            }
            .dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                flex-shrink: 0;
            }
            .dot[data-state="open"] { background: var(--work-item-state-open); }
            .dot[data-state="in_progress"] { background: var(--work-item-state-in_progress); }
            .dot[data-state="blocked"] { background: var(--work-item-state-blocked); }
            .dot[data-state="done"] { background: var(--work-item-state-done); }
            .dot[data-state="cancelled"] { background: var(--work-item-state-cancelled); }
            .dot[data-state="failed"] { background: var(--work-item-state-failed); }
            .pill[data-state="open"] {
                color: var(--work-item-state-open);
                background: var(--work-item-state-open-subtle);
            }
            .pill[data-state="in_progress"] {
                color: var(--work-item-state-in_progress);
                background: var(--work-item-state-in_progress-subtle);
            }
            .pill[data-state="blocked"] {
                color: var(--work-item-state-blocked);
                background: var(--work-item-state-blocked-subtle);
            }
            .pill[data-state="done"] {
                color: var(--work-item-state-done);
                background: var(--work-item-state-done-subtle);
            }
            .pill[data-state="cancelled"] {
                color: var(--work-item-state-cancelled);
                background: var(--work-item-state-cancelled-subtle);
            }
            .pill[data-state="failed"] {
                color: var(--work-item-state-failed);
                background: var(--work-item-state-failed-subtle);
            }
        `,
    ];

    constructor() {
        super();
        this.state = 'open';
        this.label = '';
        this.interactive = false;
    }

    _displayLabel() {
        if (typeof this.label === 'string' && this.label.length > 0) {
            return this.label;
        }
        if (typeof this.state !== 'string' || this.state.length === 0) {
            throw new Error('WorktrackerStatePill: state is required');
        }
        return this.t('state.' + this.state);
    }

    render() {
        const state = typeof this.state === 'string' && this.state.length > 0 ? this.state : 'open';
        const text = this._displayLabel();
        if (this.interactive) {
            return html`
                <button type="button" class="pill interactive" data-state=${state}>
                    <span class="dot" data-state=${state}></span>
                    <span>${text}</span>
                </button>
            `;
        }
        return html`
            <span class="pill" data-state=${state}>
                <span class="dot" data-state=${state}></span>
                <span>${text}</span>
            </span>
        `;
    }
}

customElements.define('worktracker-state-pill', WorktrackerStatePill);
