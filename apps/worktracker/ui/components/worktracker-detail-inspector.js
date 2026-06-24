/**
 * WorktrackerDetailInspector — sticky properties sidebar.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { worktrackerInspectorStyles } from '../styles/worktracker-inspector.styles.js';
import {
    assigneeUserId,
} from '../utils/work-item-detail-shared.js';
import './worktracker-inspector-row.js';
import './worktracker-priority-picker.js';
import './worktracker-assignee-picker.js';
import './worktracker-icon-action.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-variables-panel.js';

export class WorktrackerDetailInspector extends PlatformElement {
    static i18nNamespace = 'worktracker';

    static properties = {
        item: { attribute: false },
        dueDateDraft: { type: String, attribute: 'due-date-draft' },
        labelsDraft: { type: Array, attribute: false },
        variablesDraft: { type: Object, attribute: false },
        statusValue: { type: String, attribute: 'status-value' },
        statusConfig: { type: Object, attribute: false },
        priorityConfig: { type: Object, attribute: false },
        teamOptions: { type: Array, attribute: false },
        queueLabel: { type: String, attribute: 'queue-label' },
        boardLabel: { type: String, attribute: 'board-label' },
        locale: { type: String },
        showTitle: { type: Boolean, attribute: 'show-title' },
        showLifecycleActions: { type: Boolean, attribute: 'show-lifecycle-actions' },
        showClaim: { type: Boolean, attribute: 'show-claim' },
    };

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

    constructor() {
        super();
        this.item = null;
        this.dueDateDraft = '';
        this.labelsDraft = [];
        this.variablesDraft = {};
        this.statusValue = '';
        this.statusConfig = {};
        this.priorityConfig = {};
        this.teamOptions = [];
        this.queueLabel = '';
        this.boardLabel = '';
        this.locale = 'ru';
        this.showTitle = true;
        this.showLifecycleActions = false;
        this.showClaim = false;
    }

    _formatTimestamp(value) {
        if (typeof value !== 'string' || value.length === 0) {
            return '';
        }
        return formatPlatformDateTime(value, this.locale);
    }

    _renderToolbar() {
        if (!this.showLifecycleActions && !this.showClaim) {
            return nothing;
        }
        return html`
            <div class="wt-inspector-toolbar">
                ${this.showClaim ? html`
                    <worktracker-icon-action
                        icon="user-plus"
                        title=${this.t('detail_panel.claim')}
                        @action=${() => this.emit('wt-claim', null)}
                    ></worktracker-icon-action>
                ` : nothing}
                ${this.showLifecycleActions ? html`
                    <worktracker-icon-action
                        icon="check"
                        title=${this.t('detail_panel.complete')}
                        @action=${() => this.emit('wt-complete', null)}
                    ></worktracker-icon-action>
                    <worktracker-icon-action
                        icon="close"
                        title=${this.t('detail_panel.cancel')}
                        @action=${() => this.emit('wt-cancel', null)}
                    ></worktracker-icon-action>
                ` : nothing}
            </div>
        `;
    }

    render() {
        const item = this.item;
        if (!item || typeof item !== 'object') {
            return nothing;
        }

        const assigneeId = assigneeUserId(item);
        const queue = typeof this.queueLabel === 'string' ? this.queueLabel : '';
        const board = typeof this.boardLabel === 'string' ? this.boardLabel : '';

        return html`
            <aside class="wt-inspector">
                ${this._renderToolbar()}
                ${this.showTitle ? html`
                    <h3 class="wt-inspector-title">${this.t('detail_page.section_properties')}</h3>
                ` : nothing}
                <worktracker-inspector-row label=${this.t('detail_page.label_state')}>
                    <platform-field
                        type="enum"
                        mode="edit"
                        pill-density="dense"
                        pill-embed
                        .label=${''}
                        .value=${this.statusValue}
                        .config=${this.statusConfig}
                        @change=${(e) => {
                            const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                            this.emit('wt-status-change', { value });
                        }}
                    ></platform-field>
                </worktracker-inspector-row>
                <worktracker-priority-picker
                    .value=${item.priority}
                    .config=${this.priorityConfig}
                    @wt-priority-change=${(e) => {
                        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                        this.emit('wt-priority-change', { value });
                    }}
                ></worktracker-priority-picker>
                <worktracker-assignee-picker
                    user-id=${assigneeId}
                    queue-label=${queue}
                    .teamOptions=${this.teamOptions}
                    @wt-assignee-change=${(e) => {
                        const userId = e.detail && typeof e.detail.user_id === 'string' ? e.detail.user_id : '';
                        this.emit('wt-assignee-change', { user_id: userId });
                    }}
                ></worktracker-assignee-picker>
                <worktracker-inspector-row label=${this.t('detail_page.label_due_date')}>
                    <platform-field
                        type="datetime"
                        mode="edit"
                        pill-density="dense"
                        pill-embed
                        .label=${''}
                        .value=${this.dueDateDraft}
                        @change=${(e) => {
                            const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                            this.emit('wt-due-date-change', { value });
                        }}
                    ></platform-field>
                </worktracker-inspector-row>
                <worktracker-inspector-row label=${this.t('detail_page.label_labels')}>
                    <platform-field
                        type="array"
                        mode="edit"
                        pill-density="dense"
                        pill-embed
                        .label=${''}
                        .value=${this.labelsDraft}
                        @change=${(e) => {
                            const values = e.detail && Array.isArray(e.detail.value) ? e.detail.value : [];
                            this.emit('wt-labels-change', { values });
                        }}
                    ></platform-field>
                </worktracker-inspector-row>
                <div class="wt-inspector-section">
                    <platform-variables-panel
                        section-title=${this.t('detail_page.section_variables')}
                        .variables=${this.variablesDraft}
                        @variables-change=${(e) => {
                            const variables = e.detail && e.detail.variables && typeof e.detail.variables === 'object'
                                ? e.detail.variables
                                : {};
                            this.emit('wt-variables-change', { variables });
                        }}
                    ></platform-variables-panel>
                </div>
                <div class="wt-inspector-meta">
                    ${board.length > 0 ? html`
                        <worktracker-inspector-row label=${this.t('detail_page.label_board')}>
                            <button type="button" class="wt-inspector-link" @click=${() => this.emit('wt-board-open', null)}>
                                ${board}
                            </button>
                        </worktracker-inspector-row>
                    ` : nothing}
                    <worktracker-inspector-row label=${this.t('detail_page.label_kind')}>
                        <span class="wt-inspector-readonly">${this.t('kind.' + item.kind)}</span>
                    </worktracker-inspector-row>
                    <worktracker-inspector-row label=${this.t('detail_page.label_created')}>
                        <span class="wt-inspector-readonly">${this._formatTimestamp(item.created_at)}</span>
                    </worktracker-inspector-row>
                    <worktracker-inspector-row label=${this.t('detail_page.label_updated')}>
                        <span class="wt-inspector-readonly">${this._formatTimestamp(item.updated_at)}</span>
                    </worktracker-inspector-row>
                </div>
            </aside>
        `;
    }
}

customElements.define('worktracker-detail-inspector', WorktrackerDetailInspector);
