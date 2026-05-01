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
import '@platform/lib/components/glass-input.js';
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
                --flows-sessions-filter-gap: var(--space-3);
            }
            .flows-sessions-body {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            .flows-sessions-filters {
                min-width: 0;
            }
            .flows-sessions-filters-one-row {
                display: grid;
                grid-template-columns:
                    minmax(9rem, 1fr)
                    minmax(9rem, 1fr)
                    minmax(6.5rem, 0.85fr)
                    minmax(11rem, 1.05fr)
                    minmax(11rem, 1.05fr)
                    auto
                    auto;
                gap: var(--flows-sessions-filter-gap);
                align-items: center;
                min-width: 0;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
                padding-bottom: 2px;
            }
            .flows-sessions-filters-one-row .flows-sessions-cb,
            .flows-sessions-filters-one-row glass-input {
                min-width: 0;
                width: 100%;
            }
            .flows-sessions-filters-one-row .flows-sessions-dt {
                min-width: 11rem;
                max-width: 100%;
            }
            .flows-sessions-filters-one-row .flows-sessions-dt platform-date-picker {
                width: 100%;
                min-width: 0;
                max-width: 100%;
                display: block;
            }
            .flows-sessions-filter-icon-btn,
            .flows-sessions-btn-continue-icon {
                position: relative;
            }
            .flows-sessions-apply-filters,
            .flows-sessions-reset-filters {
                flex: 0 0 auto;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                padding: 0;
                margin: 0;
                box-sizing: border-box;
                border: none;
                border-radius: var(--radius-md, 8px);
                cursor: pointer;
                color: #ffffff;
                transition: background var(--duration-fast, 0.15s) ease;
            }
            .flows-sessions-apply-filters {
                background: var(--platform-btn-primary-bg, #99a6f9);
            }
            .flows-sessions-apply-filters:hover {
                background: var(--platform-btn-primary-bg-hover, #8794f0);
            }
            .flows-sessions-reset-filters {
                color: var(--platform-btn-secondary-text, #99a6f9);
                background: var(--platform-btn-secondary-bg, rgba(153, 166, 249, 0.15));
            }
            .flows-sessions-reset-filters:hover {
                background: var(--platform-btn-secondary-bg-hover, rgba(153, 166, 249, 0.1));
            }
            .flows-sessions-apply-filters:focus-visible,
            .flows-sessions-reset-filters:focus-visible {
                outline: none;
                box-shadow: var(--focus-ring, 0 0 0 3px rgba(153, 166, 249, 0.4));
            }
            .flows-sessions-sr-only {
                position: absolute;
                width: 1px;
                height: 1px;
                padding: 0;
                margin: -1px;
                overflow: hidden;
                clip: rect(0, 0, 0, 0);
                white-space: nowrap;
                border: 0;
            }
            .flows-sessions-table-scroll {
                overflow-x: auto;
                min-width: 0;
                max-width: 100%;
                -webkit-overflow-scrolling: touch;
            }
            .flows-sessions-table {
                width: 100%;
                min-width: min(100%, 52rem);
                table-layout: fixed;
                border-collapse: collapse;
                color: var(--text-secondary);
            }
            .flows-sessions-table th,
            .flows-sessions-table td {
                padding: var(--space-2) var(--space-3);
                text-align: left;
                border-bottom: 1px solid var(--border-subtle);
                vertical-align: top;
            }
            .flows-sessions-table th {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .flows-sessions-col-session {
                width: 38%;
            }
            .flows-sessions-col-flow {
                width: 20%;
            }
            .flows-sessions-col-last {
                width: 15%;
            }
            .flows-sessions-col-actions {
                width: 27%;
            }
            .flows-sessions-id {
                display: block;
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
                flex-wrap: wrap;
            }
            .flows-sessions-row-actions platform-button {
                flex: 0 1 auto;
            }
            .flows-sessions-btn-continue-icon {
                --btn-padding: 6px 10px;
            }
            .flows-sessions-table td.flows-sessions-td-actions {
                vertical-align: middle;
            }
            .flows-sessions-empty {
                text-align: center;
                color: var(--text-tertiary);
                padding: var(--space-6);
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

    _open(session) {
        const sessionId = session.session_id || session.id;
        if (!sessionId) {
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

    async _delete(session) {
        const sessionId = session.session_id || session.id;
        if (!sessionId) {
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
            return html`<tr><td colspan="4"><glass-spinner></glass-spinner></td></tr>`;
        }
        if (items.length === 0) {
            return html`<tr><td colspan="4" class="flows-sessions-empty">${this.t('sessions_modal.empty')}</td></tr>`;
        }
        return items.map(
            (s) => html`
            <tr>
                <td class="flows-sessions-col-session">
                    <code class="flows-sessions-id">${s.session_id || s.id}</code>
                </td>
                <td class="flows-sessions-col-flow">${asString(s.flow_id)}</td>
                <td class="flows-sessions-col-last">${this._formatLastActivity(s)}</td>
                <td class="flows-sessions-td-actions flows-sessions-col-actions">
                    <div class="flows-sessions-row-actions">
                        <platform-button
                            class="flows-sessions-btn-continue-icon"
                            title=${this.t('sessions_modal.continue_aria')}
                            @click=${() => this._open(s)}
                        >
                            <span class="flows-sessions-sr-only">${this.t('sessions_modal.continue_aria')}</span>
                            <platform-icon name="chat" size="18"></platform-icon>
                        </platform-button>
                        <platform-button
                            type="button"
                            danger
                            title=${this.t('sessions_modal.delete_btn')}
                            @click=${() => this._delete(s)}
                        >
                            <span class="flows-sessions-sr-only">${this.t('sessions_modal.delete_btn')}</span>
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
                            class="flows-sessions-cb"
                            .value=${this._filterUserId}
                            .options=${this._userFilterOptions()}
                            placeholder=${this.t('sessions_modal.filter_user')}
                            emptyLabel=${this.t('sessions_modal.filter_empty')}
                            ariaLabel=${this.t('sessions_modal.filter_user_aria')}
                            @change=${this._onUserFilterCombobox}
                        ></flows-searchable-combobox>
                        <flows-searchable-combobox
                            class="flows-sessions-cb"
                            .value=${this._filterFlowId}
                            .options=${this._flowFilterOptions()}
                            placeholder=${this.t('sessions_modal.filter_flow')}
                            emptyLabel=${this.t('sessions_modal.filter_empty')}
                            ariaLabel=${this.t('sessions_modal.filter_flow_aria')}
                            @change=${this._onFlowFilterCombobox}
                        ></flows-searchable-combobox>
                        <glass-input
                            .inputTitle=${this.t('sessions_modal.filter_branch_aria')}
                            .value=${this._filterBranchId}
                            placeholder=${this.t('sessions_modal.filter_branch')}
                            @input=${(e) => {
                                const t = e.target;
                                this._filterBranchId = t && 'value' in t ? t.value : '';
                            }}
                        ></glass-input>
                        <div class="flows-sessions-dt">
                            <platform-date-picker
                                compact
                                mode="datetime"
                                .label=${this.t('sessions_modal.filter_date_from')}
                                .value=${this._dateFromValue}
                                @change=${this._onDateFrom}
                            ></platform-date-picker>
                        </div>
                        <div class="flows-sessions-dt">
                            <platform-date-picker
                                compact
                                mode="datetime"
                                .label=${this.t('sessions_modal.filter_date_to')}
                                .value=${this._dateToValue}
                                @change=${this._onDateTo}
                            ></platform-date-picker>
                        </div>
                        <button
                            type="button"
                            class="flows-sessions-apply-filters"
                            title=${this.t('sessions_modal.filter_apply_aria')}
                            aria-label=${this.t('sessions_modal.filter_apply_aria')}
                            @click=${() => this._applyFromUi()}
                        >
                            <span class="flows-sessions-sr-only">${this.t('sessions_modal.filter_apply_aria')}</span>
                            <platform-icon name="check" size="20"></platform-icon>
                        </button>
                        <button
                            type="button"
                            class="flows-sessions-reset-filters"
                            title=${this.t('sessions_modal.filter_reset_aria')}
                            aria-label=${this.t('sessions_modal.filter_reset_aria')}
                            @click=${() => this._resetFilters()}
                        >
                            <span class="flows-sessions-sr-only">${this.t('sessions_modal.filter_reset_aria')}</span>
                            <platform-icon name="rotate-ccw" size="20"></platform-icon>
                        </button>
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
