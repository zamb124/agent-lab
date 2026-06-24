/**
 * WorktrackerAssigneePicker — assignee via platform-user-chip + team enum.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { worktrackerInspectorStyles } from '../styles/worktracker-inspector.styles.js';
import './worktracker-inspector-row.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/fields/platform-field.js';

export class WorktrackerAssigneePicker extends PlatformElement {
    static i18nNamespace = 'worktracker';

    static styles = [
        PlatformElement.styles,
        worktrackerInspectorStyles,
        css`
            :host {
                display: block;
                min-width: 0;
            }
        `,
    ];

    static properties = {
        userId: { type: String, attribute: 'user-id' },
        queueLabel: { type: String, attribute: 'queue-label' },
        teamOptions: { type: Array, attribute: false },
        label: { type: String },
        disabled: { type: Boolean },
    };

    constructor() {
        super();
        this.userId = '';
        this.queueLabel = '';
        this.teamOptions = [];
        this.label = '';
        this.disabled = false;
    }

    _onChange(event) {
        const nextValue = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this.emit('wt-assignee-change', { user_id: nextValue });
    }

    render() {
        const rowLabel = typeof this.label === 'string' && this.label.length > 0
            ? this.label
            : this.t('detail_page.label_assignee');
        const options = Array.isArray(this.teamOptions) ? this.teamOptions : [];
        const queue = typeof this.queueLabel === 'string' ? this.queueLabel : '';
        const assigneeId = typeof this.userId === 'string' ? this.userId : '';

        let control = nothing;
        if (queue.length > 0 && assigneeId.length === 0) {
            control = html`<span class="wt-inspector-readonly">${queue}</span>`;
        } else if (options.length > 0 && !this.disabled) {
            control = html`
                <platform-field
                    type="enum"
                    mode="edit"
                    pill-density="dense"
                    pill-embed
                    .label=${''}
                    .value=${assigneeId}
                    .config=${{ values: options }}
                    @change=${(e) => this._onChange(e)}
                ></platform-field>
            `;
        } else if (assigneeId.length > 0) {
            control = html`
                <platform-user-chip user-id=${assigneeId} size="sm" .interactive=${false}></platform-user-chip>
            `;
        } else {
            control = html`<span class="wt-inspector-readonly">${this.t('detail_page.unassigned')}</span>`;
        }

        return html`
            <worktracker-inspector-row label=${rowLabel}>
                ${control}
            </worktracker-inspector-row>
        `;
    }
}

customElements.define('worktracker-assignee-picker', WorktrackerAssigneePicker);
