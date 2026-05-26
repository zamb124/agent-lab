/**
 * flows-sessions-modal — список сессий и фильтры.
 *
 * Источник — useResource('flows/sessions'). Открытие сессии —
 * `this.navigate('flow_chat_session', { flowId, sessionId })`.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-date-picker.js';
import '../components/editors/flows-searchable-combobox.js';
import { asArray, asString } from '../_helpers/flows-resolvers.js';

export class FlowsSessionsModal extends PlatformModal {
    static modalKind = 'flows.sessions';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        flowId: { type: String },
        _filterUserId: { type: String, state: true },
        _filterFlowId: { type: String, state: true },
        _filterBranchId: { type: String, state: true },
        _dateFromValue: { state: true },
        _dateToValue: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            :host {
                --modal-width: min(1180px, calc(100vw - 24px));
                --flows-sessions-filter-gap: var(--space-2);
            }
            .flows-sessions-body {
                min-width: 0;
                min-height: 0;
                height: 100%;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .flows-sessions-filters {
                min-width: 0;
                padding: var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
            }
            .flows-sessions-filters-one-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--flows-sessions-filter-gap);
                align-items: stretch;
                min-width: 0;
            }
            .flows-sessions-filter {
                min-width: 0;
                flex: 1 1 13rem;
            }
            .flows-sessions-filter--branch {
                flex: 0.8 1 10rem;
            }
            .flows-sessions-filter--date {
                flex: 1 1 12rem;
            }
            .flows-sessions-filter platform-field,
            .flows-sessions-filter platform-date-picker,
            .flows-sessions-filter flows-searchable-combobox {
                width: 100%;
                min-width: 0;
                max-width: 100%;
                display: block;
            }
            .flows-sessions-filter-actions {
                flex: 0 0 auto;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                margin-left: auto;
            }
            .flows-sessions-filter-actions platform-button,
            .flows-sessions-row-actions platform-button {
                --platform-button-icon-size: 36px;
                --platform-button-icon-radius: var(--radius-full);
            }
            .flows-sessions-table-scroll {
                overflow-x: auto;
                overflow-y: auto;
                min-width: 0;
                max-width: 100%;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                -webkit-overflow-scrolling: touch;
            }
            .flows-sessions-table {
                width: 100%;
                min-width: min(100%, 48rem);
                table-layout: fixed;
                border-collapse: separate;
                border-spacing: 0;
                color: var(--text-secondary);
            }
            .flows-sessions-table th,
            .flows-sessions-table td {
                padding: 10px var(--space-3);
                text-align: left;
                vertical-align: middle;
            }
            .flows-sessions-table th {
                position: sticky;
                top: 0;
                z-index: 1;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                background: var(--glass-solid-medium);
                border-bottom: 1px solid var(--border-subtle);
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
            }
            .flows-sessions-table td {
                border-top: 1px solid var(--border-subtle);
            }
            .flows-sessions-table tbody tr:first-child td {
                border-top: none;
            }
            .flows-sessions-table tbody tr:hover td {
                background: var(--glass-tint-subtle);
            }
            .flows-sessions-col-session {
                width: 40%;
            }
            .flows-sessions-col-flow {
                width: 20%;
            }
            .flows-sessions-col-last {
                width: 22%;
            }
            .flows-sessions-col-actions {
                width: 18%;
            }
            .flows-sessions-id {
                display: inline-flex;
                max-width: 100%;
                padding: 3px 7px;
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font-size: var(--text-xs);
                line-height: 1.4;
                word-break: break-all;
                overflow-wrap: anywhere;
            }
            .flows-sessions-table td.flows-sessions-col-flow {
                word-break: break-word;
                overflow-wrap: anywhere;
            }
            .flows-sessions-table td.flows-sessions-col-last {
                white-space: nowrap;
            }
            .flows-sessions-row-actions {
                display: flex;
                flex-direction: row;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-2);
                flex-wrap: nowrap;
            }
            .flows-sessions-table td.flows-sessions-td-actions {
                vertical-align: middle;
            }
            .flows-sessions-empty {
                text-align: center;
                color: var(--text-tertiary);
                padding: var(--space-6);
            }
            .flows-sessions-loading {
                text-align: center;
                padding: var(--space-6);
            }
            .flows-sessions-table td.flows-sessions-empty,
            .flows-sessions-table td.flows-sessions-loading {
                text-align: center;
            }
            @media (max-width: 760px) {
                .flows-sessions-filters {
                    padding: var(--space-2);
                    border-radius: var(--radius-lg);
                }
                .flows-sessions-filter {
                    flex-basis: 100%;
                }
                .flows-sessions-filter-actions {
                    width: 100%;
                    margin-left: 0;
                    justify-content: flex-end;
                }
                .flows-sessions-table-scroll {
                    overflow: visible;
                    border: none;
                    background: transparent;
                }
                .flows-sessions-table,
                .flows-sessions-table thead,
                .flows-sessions-table tbody,
                .flows-sessions-table tr,
                .flows-sessions-table td {
                    display: block;
                    width: 100%;
                    min-width: 0;
                    box-sizing: border-box;
                }
                .flows-sessions-table thead {
                    display: none;
                }
                .flows-sessions-table tbody {
                    display: grid;
                    gap: var(--space-2);
                }
                .flows-sessions-table tr {
                    padding: var(--space-2);
                    border: 1px solid var(--border-subtle);
                    border-radius: var(--radius-lg);
                    background: var(--glass-solid-subtle);
                }
                .flows-sessions-table td {
                    display: grid;
                    grid-template-columns: minmax(5.5rem, 32%) minmax(0, 1fr);
                    gap: var(--space-2);
                    padding: 6px 0;
                    border-top: none;
                }
                .flows-sessions-table td::before {
                    content: attr(data-label);
                    color: var(--text-tertiary);
                    font-size: var(--text-xs);
                    font-weight: var(--font-semibold);
                    text-transform: uppercase;
                    letter-spacing: 0.04em;
                }
                .flows-sessions-table td.flows-sessions-td-actions {
                    display: block;
                    padding-top: var(--space-2);
                }
                .flows-sessions-table td.flows-sessions-td-actions::before {
                    display: none;
                }
                .flows-sessions-table td.flows-sessions-empty,
                .flows-sessions-table td.flows-sessions-loading {
                    display: block;
                }
                .flows-sessions-table td.flows-sessions-empty::before,
                .flows-sessions-table td.flows-sessions-loading::before {
                    display: none;
                }
                .flows-sessions-row-actions {
                    justify-content: flex-start;
                }
                .flows-sessions-table td.flows-sessions-col-last {
                    white-space: normal;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this.flowId = '';
        this._filterUserId = '';
        this._filterFlowId = '';
        this._filterBranchId = '';
        this._dateFromValue = null;
        this._dateToValue = null;
        this._sessions = this.useResource('flows/sessions');
        this._flows = this.useResource('flows/flows', { autoload: true });
        this._teamSel = this.select((s) => s.team);
    }

    _userFilterOptions() {
        const team = this._teamSel.value;
        const members =
            team && typeof team === 'object' && Array.isArray(team.members) ? team.members : [];
        const out = [];
        for (const m of members) {
            if (!m || typeof m !== 'object') {
                continue;
            }
            const uid = m.user_id;
            if (typeof uid !== 'string' || uid.length === 0) {
                continue;
            }
            let label = uid;
            if (typeof m.name === 'string' && m.name.length > 0) {
                if (typeof m.email === 'string' && m.email.length > 0) {
                    label = `${m.name} — ${m.email}`;
                } else {
                    label = m.name;
                }
            } else if (typeof m.email === 'string' && m.email.length > 0) {
                label = m.email;
            }
            out.push({ value: uid, label });
        }
        return out;
    }

    _flowFilterOptions() {
        const items = asArray(this._flows.items);
        const out = [];
        for (const f of items) {
            if (!f || typeof f !== 'object') {
                continue;
            }
            const id = f.flow_id;
            if (typeof id !== 'string' || id.length === 0) {
                continue;
            }
            let label = id;
            if (typeof f.name === 'string' && f.name.length > 0) {
                label = f.name;
            }
            out.push({ value: id, label });
        }
        return out;
    }

    _onUserFilterCombobox(e) {
        const d = e.detail;
        if (d && typeof d === 'object' && 'value' in d) {
            const v = d.value;
            this._filterUserId = typeof v === 'string' ? v : '';
        }
    }

    _onFlowFilterCombobox(e) {
        const d = e.detail;
        if (d && typeof d === 'object' && 'value' in d) {
            const v = d.value;
            this._filterFlowId = typeof v === 'string' ? v : '';
        }
    }

    _buildLoadPayload() {
        const payload = { limit: 200 };
        if (this._filterUserId.length > 0) {
            payload.user_id = this._filterUserId;
        }
        if (this._filterFlowId.length > 0) {
            payload.flow_id = this._filterFlowId;
        }
        if (this._filterBranchId.length > 0) {
            payload.branch_id = this._filterBranchId;
        }
        if (this._dateFromValue !== null && typeof this._dateFromValue === 'string' && this._dateFromValue.length > 0) {
            payload.date_from = this._dateFromValue;
        }
        if (this._dateToValue !== null && typeof this._dateToValue === 'string' && this._dateToValue.length > 0) {
            payload.date_to = this._dateToValue;
        }
        return payload;
    }

    _loadSessions() {
        this._sessions.load(this._buildLoadPayload());
    }

    _applyFromUi() {
        const root = this.renderRoot;
        if (root) {
            for (const el of root.querySelectorAll('flows-searchable-combobox')) {
                if (typeof el.flush === 'function') {
                    el.flush();
                }
            }
        }
        this._loadSessions();
    }

    _resetFilters() {
        this._filterUserId = '';
        this._filterFlowId = typeof this.flowId === 'string' ? this.flowId : '';
        this._filterBranchId = '';
        this._dateFromValue = null;
        this._dateToValue = null;
        this._loadSessions();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('flowId')) {
            this._filterFlowId = typeof this.flowId === 'string' ? this.flowId : '';
            this._loadSessions();
        }
    }

    _sessionId(session) {
        if (!session || typeof session !== 'object') {
            return '';
        }
        const sessionId = asString(session.session_id);
        if (sessionId.length > 0) {
            return sessionId;
        }
        return asString(session.id);
    }

    _open(session) {
        const sessionId = this._sessionId(session);
        if (sessionId.length === 0) {
            return;
        }
        let flowForNav = asString(session.flow_id);
        if (flowForNav.length === 0) {
            flowForNav = this._filterFlowId;
        }
        if (typeof this.flowId === 'string' && this.flowId.length > 0 && flowForNav.length === 0) {
            flowForNav = this.flowId;
        }
        if (flowForNav.length === 0) {
            return;
        }
        this.navigate('flow_chat_session', { flowId: flowForNav, sessionId });
        this.close();
    }

    _openDurableHistory(session) {
        const sessionId = this._sessionId(session);
        if (sessionId.length === 0) {
            return;
        }
        this.openModal('flows.durable_history', { sessionId });
    }

    async _delete(session) {
        const sessionId = this._sessionId(session);
        if (sessionId.length === 0) {
            return;
        }
        const ok = await platformConfirm(
            this.t('sessions_modal.delete_message', { id: sessionId }),
            {
                title: this.t('sessions_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('sessions_modal.delete_btn'),
                cancelText: this.t('sessions_modal.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._sessions.remove(sessionId);
    }

    _formatLastActivity(s) {
        if (!s || typeof s !== 'object') {
            return this.t('sessions_modal.col_last_empty');
        }
        const raw = s.last_activity;
        if (raw === null || raw === undefined) {
            return this.t('sessions_modal.col_last_empty');
        }
        if (typeof raw === 'string' && raw.length > 0) {
            const d = new Date(raw);
            if (Number.isNaN(d.getTime())) {
                return this.t('sessions_modal.col_last_empty');
            }
            return new Intl.DateTimeFormat(undefined, {
                dateStyle: 'short',
                timeStyle: 'short',
            }).format(d);
        }
        return this.t('sessions_modal.col_last_empty');
    }

    _onDateFrom(e) {
        const d = e.detail;
        if (d && typeof d === 'object' && 'value' in d) {
            this._dateFromValue = d.value;
        }
    }

    _onDateTo(e) {
        const d = e.detail;
        if (d && typeof d === 'object' && 'value' in d) {
            this._dateToValue = d.value;
        }
    }

    _renderRows() {
        const items = asArray(this._sessions.items);
        if (this._sessions.loading && items.length === 0) {
            return html`<tr><td colspan="4" class="flows-sessions-loading"><glass-spinner></glass-spinner></td></tr>`;
        }
        if (items.length === 0) {
            return html`<tr><td colspan="4" class="flows-sessions-empty">${this.t('sessions_modal.empty')}</td></tr>`;
        }
        return items.map(
            (s) => html`
            <tr>
                <td class="flows-sessions-col-session" data-label=${this.t('sessions_modal.col_session')}>
                    <code class="flows-sessions-id">${this._sessionId(s)}</code>
                </td>
                <td class="flows-sessions-col-flow" data-label=${this.t('sessions_modal.col_flow')}>${asString(s.flow_id)}</td>
                <td class="flows-sessions-col-last" data-label=${this.t('sessions_modal.col_last')}>${this._formatLastActivity(s)}</td>
                <td class="flows-sessions-td-actions flows-sessions-col-actions" data-label=${this.t('sessions_modal.col_actions')}>
                    <div class="flows-sessions-row-actions">
                        <platform-button
                            icon-only
                            variant="primary"
                            title=${this.t('sessions_modal.continue_aria')}
                            aria-label=${this.t('sessions_modal.continue_aria')}
                            @click=${() => this._open(s)}
                        >
                            <platform-icon name="chat" size="18"></platform-icon>
                        </platform-button>
                        <platform-button
                            icon-only
                            variant="secondary"
                            title=${this.t('sessions_modal.history_aria')}
                            aria-label=${this.t('sessions_modal.history_aria')}
                            @click=${() => this._openDurableHistory(s)}
                        >
                            <platform-icon name="trace-timeline" size="18"></platform-icon>
                        </platform-button>
                        <platform-button
                            icon-only
                            variant="danger"
                            title=${this.t('sessions_modal.delete_btn')}
                            aria-label=${this.t('sessions_modal.delete_btn')}
                            @click=${() => this._delete(s)}
                        >
                            <platform-icon name="trash" size="14"></platform-icon>
                        </platform-button>
                    </div>
                </td>
            </tr>
        `,
        );
    }

    renderHeader() {
        return this.t('sessions_modal.modal_title');
    }

    renderBody() {
        return html`
            <div class="flows-sessions-body">
                <div class="flows-sessions-filters" part="filters">
                    <div class="flows-sessions-filters-one-row">
                        <flows-searchable-combobox
                            class="flows-sessions-filter"
                            compact
                            .value=${this._filterUserId}
                            .options=${this._userFilterOptions()}
                            .label=${this.t('sessions_modal.filter_user')}
                            placeholder=${this.t('sessions_modal.filter_user')}
                            emptyLabel=${this.t('sessions_modal.filter_empty')}
                            ariaLabel=${this.t('sessions_modal.filter_user_aria')}
                            @change=${this._onUserFilterCombobox}
                        ></flows-searchable-combobox>
                        <flows-searchable-combobox
                            class="flows-sessions-filter"
                            compact
                            .value=${this._filterFlowId}
                            .options=${this._flowFilterOptions()}
                            .label=${this.t('sessions_modal.filter_flow')}
                            placeholder=${this.t('sessions_modal.filter_flow')}
                            emptyLabel=${this.t('sessions_modal.filter_empty')}
                            ariaLabel=${this.t('sessions_modal.filter_flow_aria')}
                            @change=${this._onFlowFilterCombobox}
                        ></flows-searchable-combobox>
                        <platform-field
                            class="flows-sessions-filter flows-sessions-filter--branch"
                            type="string"
                            mode="edit"
                            pill-density="compact"
                            .value=${this._filterBranchId}
                            .label=${this.t('sessions_modal.filter_branch')}
                            .placeholder=${this.t('sessions_modal.filter_branch')}
                            @change=${(e) => {
                                this._filterBranchId = e.detail.value;
                            }}
                        ></platform-field>
                        <div class="flows-sessions-filter flows-sessions-filter--date">
                            <platform-date-picker
                                compact
                                mode="datetime"
                                .label=${this.t('sessions_modal.filter_date_from')}
                                .value=${this._dateFromValue}
                                @change=${this._onDateFrom}
                            ></platform-date-picker>
                        </div>
                        <div class="flows-sessions-filter flows-sessions-filter--date">
                            <platform-date-picker
                                compact
                                mode="datetime"
                                .label=${this.t('sessions_modal.filter_date_to')}
                                .value=${this._dateToValue}
                                @change=${this._onDateTo}
                            ></platform-date-picker>
                        </div>
                        <div class="flows-sessions-filter-actions">
                            <platform-button
                                icon-only
                                variant="primary"
                                title=${this.t('sessions_modal.filter_apply_aria')}
                                aria-label=${this.t('sessions_modal.filter_apply_aria')}
                                @click=${() => this._applyFromUi()}
                            >
                                <platform-icon name="check" size="20"></platform-icon>
                            </platform-button>
                            <platform-button
                                icon-only
                                variant="secondary"
                                title=${this.t('sessions_modal.filter_reset_aria')}
                                aria-label=${this.t('sessions_modal.filter_reset_aria')}
                                @click=${() => this._resetFilters()}
                            >
                                <platform-icon name="rotate-ccw" size="20"></platform-icon>
                            </platform-button>
                        </div>
                    </div>
                </div>
                <div class="flows-sessions-table-scroll">
                    <table class="flows-sessions-table">
                        <thead>
                            <tr>
                                <th class="flows-sessions-col-session">${this.t('sessions_modal.col_session')}</th>
                                <th class="flows-sessions-col-flow">${this.t('sessions_modal.col_flow')}</th>
                                <th class="flows-sessions-col-last">${this.t('sessions_modal.col_last')}</th>
                                <th class="flows-sessions-col-actions">${this.t('sessions_modal.col_actions')}</th>
                            </tr>
                        </thead>
                        <tbody>${this._renderRows()}</tbody>
                    </table>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-sessions-modal', FlowsSessionsModal);
registerModalKind(FlowsSessionsModal.modalKind, 'flows-sessions-modal');
