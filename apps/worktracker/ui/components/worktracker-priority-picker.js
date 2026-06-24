/**
 * WorktrackerPriorityPicker — priority enum in inspector row.
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './worktracker-inspector-row.js';
import '@platform/lib/components/fields/platform-field.js';

export class WorktrackerPriorityPicker extends PlatformElement {
    static i18nNamespace = 'worktracker';

    static properties = {
        value: { type: String },
        config: { type: Object },
        label: { type: String },
        disabled: { type: Boolean },
    };

    constructor() {
        super();
        this.value = 'normal';
        this.config = {};
        this.label = '';
        this.disabled = false;
    }

    _onChange(event) {
        const nextValue = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this.emit('wt-priority-change', { value: nextValue });
    }

    render() {
        const rowLabel = typeof this.label === 'string' && this.label.length > 0
            ? this.label
            : this.t('detail_page.label_priority');
        return html`
            <worktracker-inspector-row label=${rowLabel}>
                <platform-field
                    type="enum"
                    mode="edit"
                    pill-density="dense"
                    pill-embed
                    .label=${''}
                    .value=${this.value}
                    .config=${this.config}
                    ?disabled=${this.disabled}
                    @change=${(e) => this._onChange(e)}
                ></platform-field>
            </worktracker-inspector-row>
        `;
    }
}

customElements.define('worktracker-priority-picker', WorktrackerPriorityPicker);
