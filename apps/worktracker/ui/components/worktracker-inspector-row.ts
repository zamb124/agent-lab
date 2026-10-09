/**
 * WorktrackerInspectorRow — compact inspector property row (label | control).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { worktrackerInspectorStyles } from '../styles/worktracker-inspector.styles.js';

export class WorktrackerInspectorRow extends PlatformElement {
    declare label: string;

    static override properties = {
        label: { type: String },
    };

    static override styles = [
        PlatformElement.styles,
        worktrackerInspectorStyles,
        css`
            :host {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-height: var(--worktracker-inspector-row-height);
                min-width: 0;
            }
            .label {
                flex: 0 0 var(--worktracker-inspector-label-width);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                min-width: 0;
            }
            .control {
                flex: 1;
                min-width: 0;
                display: flex;
                align-items: center;
            }
        `,
    ];

    constructor() {
        super();
        this.label = '';
    }

    override render() {
        return html`
            <span class="label">${this.label}</span>
            <div class="control">
                <slot></slot>
            </div>
        `;
    }
}

customElements.define('worktracker-inspector-row', WorktrackerInspectorRow);
