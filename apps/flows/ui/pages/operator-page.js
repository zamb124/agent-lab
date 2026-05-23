/**
 * OperatorPage — рабочее место оператора.
 *
 * Состав:
 *   - Шапка: ссылка обратно в /flows, переключатель темы, заголовок.
 *   - Полоса очередей: chips с join/leave, форма создания (admin/owner).
 *   - Канбан задач по статусам STATUSES (open/claimed/user_dialog/awaiting_agent/completed/cancelled).
 *   - Панель деталей (~половина ширины) только при выбранной карточке: заголовок, статус,
 *     (i) — JSON, закрыть; history, dialog_log, composer.
 *
 * Фабрики:
 *   - useResource('flows/operator_queues')        — list/create
 *   - useOp('flows/operator_queue_add_member')    — join
 *   - useOp('flows/operator_queue_remove_member') — leave
 *   - useOp('flows/operator_tasks_list')          — список задач (фильтр queue_id/status)
 *   - useOp('flows/operator_task_get')            — детали выбранной
 *   - useOp('flows/operator_task_claim')          — claim (WS)
 *   - useOp('flows/operator_task_post_message')   — message (WS)
 *   - useOp('flows/operator_task_complete')       — complete (WS)
 *   - useOp('flows/file_upload')                  — multipart upload
 *
 * Push: useEvent('notify/flows/flows_operator_tasks_updated_received') -> refresh.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import { asArray, asString, isPlainObject } from '../_helpers/flows-resolvers.js';

const STATUSES = Object.freeze(['open', 'claimed', 'user_dialog', 'awaiting_agent', 'completed', 'cancelled']);
const OPERATOR_ROLES = new Set(['admin', 'owner']);
const OPERATOR_PUSH_EVENT = 'notify/flows/flows_operator_tasks_updated_received';
const QUEUE_SLUG_PATTERN = /^[a-z][a-z0-9_]{1,63}$/;

function userIsAdmin(user, activeCompanyId) {
    if (!user || typeof activeCompanyId !== 'string') return false;
    const directCompanies = isPlainObject(user.companies) ? user.companies : null;
    const rawCompanies = isPlainObject(user.raw) && isPlainObject(user.raw.companies) ? user.raw.companies : null;
    const companies = directCompanies !== null ? directCompanies : rawCompanies;
    if (!companies) return false;
    const raw = companies[activeCompanyId];
    if (!raw) return false;
    const list = Array.isArray(raw) ? raw : [raw];
    for (const r of list) {
        if (typeof r !== 'string') continue;
        if (OPERATOR_ROLES.has(r.trim().toLowerCase())) return true;
    }
    return false;
}

export class OperatorPage extends PlatformPage {
    static properties = {
        _selectedQueueId: { state: true },
        _selectedTaskId: { state: true },
        _composerDraft: { state: true },
        _pendingFiles: { state: true },
        _queueName: { state: true },
        _queueSlug: { state: true },
        _showTaskData: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                flex: 1; min-width: 0; min-height: 0;
                display: flex; flex-direction: column;
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-subtle);
                margin: var(--space-3); overflow: hidden;
            }
            .header {
                display: flex; align-items: center; gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
            }
            .header-title { font-size: var(--text-lg); font-weight: var(--font-semibold); flex: 1; }
            .header-icon-btn {
                display: inline-flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                color: var(--text-secondary); cursor: pointer; text-decoration: none;
            }
            .header-icon-btn:hover { background: var(--glass-solid-medium); color: var(--text-primary); }
            .queues-bar {
                display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap;
                padding: var(--space-2) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
            }
            .queue-chip {
                display: inline-flex; align-items: center; gap: var(--space-2);
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                cursor: pointer; font-size: var(--text-sm);
            }
            .queue-chip[active] { background: var(--accent-subtle); color: var(--accent); border-color: var(--accent); }
            .queue-chip-leave, .queue-chip-join {
                margin-left: var(--space-2); padding: 2px 6px;
                font-size: var(--text-xs); border: none; cursor: pointer;
                border-radius: var(--radius-sm);
            }
            .queue-chip-leave { background: transparent; color: var(--error); }
            .queue-chip-join { background: var(--accent); color: white; }
            .queue-form {
                display: flex; gap: var(--space-2); margin-left: auto;
            }
            .queue-form input {
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            .body {
                flex: 1; min-height: 0; display: flex;
            }
            .kanban {
                flex: 1 1 0; min-width: 0; overflow-x: auto;
                display: flex; gap: var(--space-2); padding: var(--space-3);
            }
            .column {
                flex-shrink: 0; min-width: 240px; max-width: 280px;
                display: flex; flex-direction: column; gap: var(--space-2);
            }
            .column-title {
                font-size: var(--text-xs); text-transform: uppercase;
                color: var(--text-tertiary); letter-spacing: 0.06em;
                padding: var(--space-1) var(--space-2);
            }
            .task-card {
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer; font-size: var(--text-sm);
            }
            .task-card:hover { background: var(--glass-solid-medium); }
            .task-card[active] { border-color: var(--accent); background: var(--accent-subtle); color: var(--accent); }
            .task-card[active] .task-card-status { color: var(--accent); opacity: 0.9; }
            .task-card-head {
                display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-2);
                margin-bottom: 2px;
            }
            .task-card-title { flex: 1; min-width: 0; font-weight: var(--font-medium); }
            .task-card-status {
                flex-shrink: 0; max-width: 48%; text-align: right;
                font-size: 10px; line-height: var(--leading-tight);
                text-transform: uppercase; letter-spacing: 0.04em;
                color: var(--text-tertiary);
            }
            .task-card-meta { font-size: var(--text-xs); color: var(--text-tertiary); margin-top: 2px; }
            .detail-panel {
                flex: 0 0 50%;
                min-width: 0;
                max-width: 50%;
                min-height: 0;
                display: flex; flex-direction: column;
                border-left: 1px solid var(--border-subtle);
                box-sizing: border-box;
                padding-top: var(--space-3);
                padding-inline: var(--space-3);
                padding-bottom: max(var(--space-4), env(safe-area-inset-bottom, 0px));
                overflow-y: auto;
                overflow-x: hidden;
                gap: var(--space-3);
                scroll-padding-bottom: var(--space-3);
            }
            .panel-head {
                display: flex; align-items: flex-start; justify-content: space-between;
                gap: var(--space-2);
            }
            .panel-title { font-size: var(--text-xs); font-weight: var(--font-semibold); text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-tertiary); }
            .panel-title--main { flex: 1; min-width: 0; text-align: left; line-height: var(--leading-tight); }
            .panel-head-right {
                flex-shrink: 0; display: flex; flex-direction: row; align-items: center; gap: var(--space-2);
            }
            .panel-status {
                max-width: 9rem; text-align: right;
                font-size: 10px; font-weight: var(--font-semibold);
                line-height: var(--leading-tight);
                text-transform: uppercase; letter-spacing: 0.04em;
                color: var(--text-tertiary);
            }
            .detail-info-btn {
                flex-shrink: 0;
                display: inline-flex; align-items: center; justify-content: center;
                width: 36px; height: 36px; padding: 0; margin: 0;
                border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
                background: var(--glass-solid-subtle); color: var(--text-secondary);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }
            .detail-info-btn:hover { background: var(--glass-solid-medium); color: var(--text-primary); }
            .detail-info-btn:focus-visible { outline: none; box-shadow: var(--focus-ring, 0 0 0 3px rgba(153, 166, 249, 0.4)); }
            .detail-close-btn {
                flex-shrink: 0;
                display: inline-flex; align-items: center; justify-content: center;
                width: 36px; height: 36px; padding: 0; margin: 0;
                border: 1px solid var(--border-subtle); border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle); color: var(--text-secondary);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }
            .detail-close-btn:hover { background: var(--glass-solid-medium); color: var(--text-primary); }
            .detail-close-btn:focus-visible { outline: none; box-shadow: var(--focus-ring, 0 0 0 3px rgba(153, 166, 249, 0.4)); }
            .task-data-section { display: flex; flex-direction: column; gap: var(--space-2); flex-shrink: 0; }
            .task-data-label { font-size: var(--text-xs); font-weight: var(--font-semibold); text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-tertiary); }
            .task-data-json {
                margin: 0; padding: var(--space-2) var(--space-3);
                max-height: min(50vh, 360px);
                overflow: auto;
                font-family: var(--font-mono, ui-monospace, monospace);
                font-size: var(--text-xs);
                line-height: var(--leading-normal);
                white-space: pre;
                color: var(--text-primary);
                background: var(--bg-secondary, var(--glass-solid-subtle));
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
            }
            .dialog-entry {
                display: flex; flex-direction: column; gap: 2px;
                padding: var(--space-2); border-radius: var(--radius-md);
                background: var(--glass-solid-subtle); margin-bottom: var(--space-1);
            }
            .dialog-entry--user { background: var(--accent-subtle); }
            .dialog-entry--operator { background: var(--glass-solid-medium); }
            .dialog-role { font-size: var(--text-xs); color: var(--text-tertiary); font-weight: var(--font-semibold); }
            .operator-composer {
                display: flex; flex-direction: column; gap: var(--space-2);
                margin-top: auto;
                flex-shrink: 0;
                padding-top: var(--space-1);
            }
            .operator-claim {
                display: flex; justify-content: flex-end; align-items: center;
                width: 100%; box-sizing: border-box;
                padding-top: var(--space-2);
            }
            .composer {
                box-sizing: border-box;
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                transition: border-color var(--duration-fast);
            }
            .composer:focus-within { border-color: var(--border-focus, var(--accent)); }
            .composer-input {
                flex: 1; min-width: 0; border: none; background: transparent;
                color: var(--text-primary); font: inherit; font-size: var(--text-sm);
                line-height: var(--leading-tight); padding: var(--space-1) 0; outline: none;
            }
            .composer-input::placeholder { color: var(--text-tertiary); }
            .composer-btn {
                display: inline-flex; align-items: center; justify-content: center;
                flex-shrink: 0; width: 40px; height: 40px; padding: 0; margin: 0;
                border: none; border-radius: var(--radius-full); cursor: pointer;
                background: var(--glass-solid-medium); color: var(--accent);
                transition: background var(--duration-fast), opacity var(--duration-fast);
            }
            .composer-btn:hover:not([disabled]) { background: var(--glass-solid-strong); }
            .composer-btn:focus-visible { outline: none; box-shadow: var(--focus-ring, 0 0 0 3px rgba(153, 166, 249, 0.4)); }
            .composer-btn[disabled] { opacity: 0.45; cursor: not-allowed; }
            .composer-btn--send { color: var(--accent); }
            .composer-btn--complete { color: var(--success); background: var(--success-bg); }
            .composer-btn--complete:hover:not([disabled]) { background: var(--success-border); }
            .pending-files { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .pending-file {
                display: inline-flex; align-items: center; gap: 4px;
                padding: 2px 6px; font-size: var(--text-xs);
                background: var(--glass-solid-subtle); border-radius: var(--radius-sm);
            }
            .empty { padding: var(--space-4); text-align: center; color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this._selectedQueueId = '';
        this._selectedTaskId = '';
        this._composerDraft = '';
        this._pendingFiles = [];
        this._queueName = '';
        this._queueSlug = '';
        this._showTaskData = false;
        this._queues = this.useResource('flows/operator_queues', { autoload: true });
        this._tasksList = this.useOp('flows/operator_tasks_list');
        this._taskGet = this.useOp('flows/operator_task_get');
        this._claim = this.useOp('flows/operator_task_claim');
        this._postMessage = this.useOp('flows/operator_task_post_message');
        this._complete = this.useOp('flows/operator_task_complete');
        this._addMember = this.useOp('flows/operator_queue_add_member');
        this._removeMember = this.useOp('flows/operator_queue_remove_member');
        this._upload = this.useOp('flows/file_upload');
        this._authSel = this.select((s) => {
            const user = isPlainObject(s.auth) && isPlainObject(s.auth.user) ? s.auth.user : null;
            const companyId = isPlainObject(s.companies) && typeof s.companies.activeId === 'string'
                ? s.companies.activeId
                : null;
            return { user, companyId };
        });
        this._themeSel = this.select((s) => {
            const mode = isPlainObject(s.theme) ? s.theme.mode : null;
            return mode === 'light' ? 'light' : 'dark';
        });
        this.useEvent(OPERATOR_PUSH_EVENT, () => this._refreshTasks());
    }

    connectedCallback() {
        super.connectedCallback();
        this._refreshTasks();
    }

    async _refreshTasks() {
        const payload = { limit: 200, offset: 0 };
        if (this._selectedQueueId) payload.queue_id = this._selectedQueueId;
        await this._tasksList.run(payload);
        if (this._selectedTaskId) {
            await this._taskGet.run({ task_id: this._selectedTaskId });
        }
    }

    _selectQueue(queueId) {
        this._selectedQueueId = queueId === this._selectedQueueId ? '' : queueId;
        this._selectedTaskId = '';
        this._showTaskData = false;
        this._refreshTasks();
    }

    _labelForTaskStatus(statusRaw) {
        const s = typeof statusRaw === 'string' && STATUSES.includes(statusRaw) ? statusRaw : 'open';
        return this.t(`operator.status_${s}`);
    }

    _onCloseDetail() {
        this._selectedTaskId = '';
        this._showTaskData = false;
    }

    _selectTask(taskId) {
        this._selectedTaskId = taskId;
        this._showTaskData = false;
        void this._taskGet.run({ task_id: taskId });
    }

    async _joinQueue(queue) {
        const me = this._authSel.value;
        if (!me?.user?.user_id) return;
        await this._addMember.run({
            queue_id: queue.id,
            body: { user_id: String(me.user.user_id), role: 'agent' },
        });
        await this._queues.load();
    }

    async _leaveQueue(queue) {
        const me = this._authSel.value;
        if (!me?.user?.user_id) return;
        await this._removeMember.run({
            queue_id: queue.id,
            member_user_id: String(me.user.user_id),
        });
        await this._queues.load();
    }

    async _createQueue() {
        const name = this._queueName.trim();
        const slug = this._queueSlug.trim();
        if (!name || !QUEUE_SLUG_PATTERN.test(slug)) return;
        await this._queues.create({ name, slug });
        this._queueName = '';
        this._queueSlug = '';
    }

    _toggleTheme() {
        const mode = this._themeSel.value === 'dark' ? 'light' : 'dark';
        this.setTheme(mode);
    }

    async _onFilesSelected(event) {
        const files = event.target.files ? Array.from(event.target.files) : [];
        if (files.length === 0) return;
        const uploaded = [];
        for (const file of files) {
            const result = await this._upload.run({ file });
            if (!result?.file_id) {
                throw new Error('operator file_upload op must return file_id');
            }
            if (typeof result.original_name !== 'string' || result.original_name.length === 0) {
                throw new Error('operator file_upload op must return original_name');
            }
            uploaded.push({ file_id: result.file_id, original_name: result.original_name });
        }
        this._pendingFiles = [...this._pendingFiles, ...uploaded];
        event.target.value = '';
    }

    _removePendingFile(index) {
        this._pendingFiles = this._pendingFiles.filter((_, i) => i !== index);
    }

    async _onClaim() {
        if (!this._selectedTaskId) return;
        await this._claim.run({ task_id: this._selectedTaskId });
        await this._taskGet.run({ task_id: this._selectedTaskId });
    }

    async _onSendMessage() {
        const text = this._composerDraft.trim();
        if (!text || !this._selectedTaskId) return;
        await this._postMessage.run({
            task_id: this._selectedTaskId,
            text,
            file_ids: this._pendingFiles.map((f) => f.file_id),
        });
        this._composerDraft = '';
        this._pendingFiles = [];
        await this._taskGet.run({ task_id: this._selectedTaskId });
    }

    async _onComplete() {
        const text = this._composerDraft.trim();
        if (!this._selectedTaskId) return;
        await this._complete.run({
            task_id: this._selectedTaskId,
            resolution: text.length > 0 ? text : this.t('operator.default_resolution'),
            file_ids: this._pendingFiles.map((f) => f.file_id),
        });
        this._composerDraft = '';
        this._pendingFiles = [];
        await this._refreshTasks();
    }

    _renderQueues() {
        const items = asArray(this._queues.items);
        const me = this._authSel.value;
        const isAdmin = userIsAdmin(me.user, me.companyId);
        return html`
            ${items.map((q) => html`
                <span
                    class="queue-chip"
                    ?active=${this._selectedQueueId === q.id}
                    @click=${() => this._selectQueue(q.id)}
                >
                    <span>${q.name}</span>
                    <code>${q.slug}</code>
                    ${q.i_am_member
                        ? html`<button type="button" class="queue-chip-leave" @click=${(e) => { e.stopPropagation(); this._leaveQueue(q); }}>${this.t('operator.btn_leave_queue')}</button>`
                        : html`<button type="button" class="queue-chip-join" @click=${(e) => { e.stopPropagation(); this._joinQueue(q); }}>${this.t('operator.btn_join_queue')}</button>`}
                </span>
            `)}
            ${isAdmin
                ? html`
                    <div class="queue-form">
                        <platform-field
                            type="string"
                            mode="edit"
                            .placeholder=${this.t('operator.queue_name_placeholder')}
                            .value=${this._queueName}
                            @change=${(e) => {
                                this._queueName = typeof e.detail.value === 'string' ? e.detail.value : '';
                            }}
                        ></platform-field>
                        <platform-field
                            type="string"
                            mode="edit"
                            .placeholder=${this.t('operator.queue_slug_placeholder')}
                            .value=${this._queueSlug}
                            @change=${(e) => {
                                this._queueSlug = typeof e.detail.value === 'string' ? e.detail.value : '';
                            }}
                        ></platform-field>
                        <glass-button @click=${this._createQueue}>${this.t('operator.queue_create')}</glass-button>
                    </div>
                `
                : ''}
        `;
    }

    _renderKanban() {
        const data = this._tasksList.lastResult;
        const items = Array.isArray(data?.items) ? data.items : [];
        const byStatus = {};
        for (const status of STATUSES) byStatus[status] = [];
        for (const task of items) {
            const status = STATUSES.includes(task.status) ? task.status : 'open';
            byStatus[status].push(task);
        }
        if (this._tasksList.busy && items.length === 0) {
            return html`<div class="empty"><glass-spinner></glass-spinner></div>`;
        }
        return html`${STATUSES.map((status) => html`
            <div class="column">
                <div class="column-title">${this.t(`operator.status_${status}`)}</div>
                ${byStatus[status].length === 0
                    ? html`<div class="empty">${this.t('operator.empty_column')}</div>`
                    : byStatus[status].map((task) => {
                        const cardStatus = typeof task.status === 'string' && STATUSES.includes(task.status) ? task.status : 'open';
                        return html`
                        <div
                            class="task-card"
                            ?active=${this._selectedTaskId === task.id}
                            @click=${() => this._selectTask(task.id)}
                        >
                            <div class="task-card-head">
                                <div class="task-card-title">${
                                    typeof task.handoff_title === 'string' && task.handoff_title.length > 0
                                        ? task.handoff_title
                                        : (typeof task.flow_display_name === 'string' && task.flow_display_name.length > 0
                                            ? task.flow_display_name
                                            : task.id)
                                }</div>
                                <span class="task-card-status" role="status">${this._labelForTaskStatus(cardStatus)}</span>
                            </div>
                            <div class="task-card-meta">${asString(task.handoff_message_preview)}</div>
                            <div class="task-card-meta"><code>${task.flow_id}</code> / ${
                                typeof task.branch_id === 'string' && task.branch_id.length > 0 ? task.branch_id : 'base'
                            }</div>
                        </div>
                    `;
                    })}
            </div>
        `)}`;
    }

    _detailHandoffMode(detail) {
        const task = isPlainObject(detail?.task) ? detail.task : null;
        if (task !== null && typeof task.handoff_mode === 'string' && task.handoff_mode.trim() === 'takeover') {
            return 'takeover';
        }
        const taskMeta = task !== null && isPlainObject(task.metadata) ? task.metadata : null;
        const directMeta = isPlainObject(detail?.metadata) ? detail.metadata : null;
        const meta = taskMeta !== null ? taskMeta : directMeta;
        if (meta !== null && typeof meta.handoff_mode === 'string' && meta.handoff_mode.trim() === 'takeover') {
            return 'takeover';
        }
        return 'single_reply';
    }

    _renderDialog(detail) {
        const dialogMessages = isPlainObject(detail) && Array.isArray(detail.dialog_messages) ? detail.dialog_messages : [];
        const history = dialogMessages
            .filter((m) => (m.role === 'user' || m.role === 'agent'))
            .map((m) => {
                const text = typeof m.message_text === 'string' ? m.message_text : '';
                return { role: m.role, text };
            })
            .filter((e) => e.text.trim());
        const log = Array.isArray(detail?.dialog_log) ? detail.dialog_log : [];
        if (history.length === 0 && log.length === 0) {
            return html`<div class="empty">${this.t('operator.takeover_no_messages')}</div>`;
        }
        return html`
            ${history.length > 0
                ? html`
                    <div class="panel-title">${this.t('operator.section_chat_history')}</div>
                    ${history.map((e) => html`
                        <div class="dialog-entry dialog-entry--${e.role === 'user' ? 'user' : 'agent'}">
                            <span class="dialog-role">${e.role === 'user' ? this.t('operator.role_user') : this.t('operator.role_agent')}</span>
                            <span>${e.text}</span>
                        </div>
                    `)}
                `
                : ''}
            ${log.length > 0
                ? html`
                    <div class="panel-title">${this.t('operator.section_operator_dialog')}</div>
                    ${log.map((entry) => html`
                        <div class="dialog-entry dialog-entry--${entry.role}">
                            <span class="dialog-role">${entry.role === 'operator' ? this.t('operator.role_operator') : this.t('operator.role_user')}</span>
                            <span>${entry.text}</span>
                            ${asArray(entry.file_ids).map((fid) => html`
                                <a href="/flows/api/v1/files/download/${fid}" target="_blank" rel="noopener">
                                    ${this.t('operator.download_file')}
                                </a>
                            `)}
                        </div>
                    `)}
                `
                : ''}
        `;
    }

    _renderComposer(detail) {
        const tsk = isPlainObject(detail) && isPlainObject(detail.task) ? detail.task : null;
        const status = tsk !== null && typeof tsk.status === 'string' ? tsk.status : '';
        if (status === 'open') {
            return html`
                <div class="operator-claim">
                    <glass-button @click=${(e) => { e.stopPropagation(); void this._onClaim(); }}>${this.t('operator.btn_claim')}</glass-button>
                </div>
            `;
        }
        const mode = this._detailHandoffMode(detail);
        const textOk = this._composerDraft.trim().length > 0;
        const postBusy = this._postMessage.busy;
        const completeBusy = this._complete.busy;
        const uploadBusy = this._upload.busy;
        const sendDisabled = !textOk || postBusy || uploadBusy;
        const completeTitle = mode === 'takeover'
            ? this.t('operator.tooltip_reply_and_close')
            : this.t('operator.btn_complete');
        return html`
            ${this._pendingFiles.length > 0
                ? html`
                    <div class="pending-files">
                        ${this._pendingFiles.map((f, i) => html`
                            <span class="pending-file">
                                <platform-icon name="file" size="12"></platform-icon>
                                <span>${f.original_name}</span>
                                <button type="button" @click=${() => this._removePendingFile(i)}>
                                    <platform-icon name="close" size="10"></platform-icon>
                                </button>
                            </span>
                        `)}
                    </div>
                `
                : ''}
            <input type="file" id="op-file-input" multiple hidden @change=${this._onFilesSelected} />
            <div class="composer">
                <button
                    type="button"
                    class="composer-btn"
                    title=${this.t('operator.tooltip_attach_file')}
                    aria-label=${this.t('operator.tooltip_attach_file')}
                    ?disabled=${uploadBusy}
                    @click=${() => this.shadowRoot.getElementById('op-file-input').click()}
                >
                    <platform-icon name="paperclip" size="18"></platform-icon>
                </button>
                <input
                    type="text"
                    class="composer-input"
                    data-canon="composer"
                    placeholder=${mode === 'takeover'
                        ? this.t('operator.placeholder_composer')
                        : this.t('operator.placeholder_single_reply')}
                    .value=${this._composerDraft}
                    aria-label=${mode === 'takeover'
                        ? this.t('operator.placeholder_composer')
                        : this.t('operator.placeholder_single_reply')}
                    @input=${(e) => { this._composerDraft = asString(e.target.value); }}
                    @keydown=${(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            if (!sendDisabled) void this._onSendMessage();
                        }
                    }}
                />
                <button
                    type="button"
                    class="composer-btn composer-btn--send"
                    title=${this.t('operator.btn_send')}
                    aria-label=${this.t('operator.btn_send')}
                    ?disabled=${sendDisabled}
                    @click=${() => void this._onSendMessage()}
                >
                    <platform-icon name="send" size="18"></platform-icon>
                </button>
                <button
                    type="button"
                    class="composer-btn composer-btn--complete"
                    title=${completeTitle}
                    aria-label=${completeTitle}
                    ?disabled=${completeBusy}
                    @click=${() => void this._onComplete()}
                >
                    <platform-icon name="check" size="18"></platform-icon>
                </button>
            </div>
        `;
    }

    _taskDetailJsonPayload(detail) {
        if (!isPlainObject(detail)) {
            throw new Error('operator: task detail must be a plain object');
        }
        return {
            task: detail.task,
            interrupt_snapshot: detail.interrupt_snapshot,
            resolution_payload: detail.resolution_payload,
            dialog_log: detail.dialog_log,
            dialog_messages: detail.dialog_messages,
        };
    }

    _renderDetail() {
        const detail = this._taskGet.lastResult;
        if (this._taskGet.busy && !detail) {
            return html`<div class="empty"><glass-spinner></glass-spinner></div>`;
        }
        if (!detail) {
            return html`<div class="empty">${this.t('operator.no_detail')}</div>`;
        }
        const titleText = isPlainObject(detail.task) && typeof detail.task.handoff_title === 'string' && detail.task.handoff_title.length > 0
            ? detail.task.handoff_title
            : (isPlainObject(detail.task) ? detail.task.id : '');
        const detailStatus = isPlainObject(detail.task) && typeof detail.task.status === 'string' ? detail.task.status : 'open';
        const detailStatusLabel = this._labelForTaskStatus(detailStatus);
        const infoShow = this.t('operator.task_data_show');
        const infoHide = this.t('operator.task_data_hide');
        const infoBtnTitle = this._showTaskData ? infoHide : infoShow;
        const closeLabel = this.t('operator.close_detail');
        const jsonText = JSON.stringify(this._taskDetailJsonPayload(detail), null, 2);
        return html`
            <div class="panel-head">
                <div class="panel-title panel-title--main">${titleText}</div>
                <div class="panel-head-right">
                    <span class="panel-status" role="status">${detailStatusLabel}</span>
                    <button
                        type="button"
                        class="detail-info-btn"
                        title=${infoBtnTitle}
                        aria-label=${infoBtnTitle}
                        aria-pressed=${this._showTaskData ? 'true' : 'false'}
                        @click=${() => { this._showTaskData = !this._showTaskData; }}
                    >
                        <platform-icon name="info" size="18"></platform-icon>
                    </button>
                    <button
                        type="button"
                        class="detail-close-btn"
                        title=${closeLabel}
                        aria-label=${closeLabel}
                        @click=${() => { this._onCloseDetail(); }}
                    >
                        <platform-icon name="close" size="18"></platform-icon>
                    </button>
                </div>
            </div>
            ${this._showTaskData ? html`
                <section class="task-data-section" aria-label=${this.t('operator.task_data_title')}>
                    <div class="task-data-label">${this.t('operator.task_data_title')}</div>
                    <pre class="task-data-json">${jsonText}</pre>
                </section>
            ` : ''}
            ${this._renderDialog(detail)}
            <div class="operator-composer">${this._renderComposer(detail)}</div>
        `;
    }

    render() {
        const themeMode = this._themeSel.value;
        const themeIcon = themeMode === 'dark' ? 'sun' : 'moon';
        const themeTitle = themeMode === 'dark'
            ? this.t('operator.theme_to_light')
            : this.t('operator.theme_to_dark');
        return html`
            <div class="header">
                <a class="header-icon-btn" href="/flows" @click=${(e) => { e.preventDefault(); this.navigate('list', {}); }}>
                    <platform-icon name="arrow-left" size="16"></platform-icon>
                    <span>${this.t('flows_sidebar.back_to_flows')}</span>
                </a>
                <button class="header-icon-btn" type="button" title=${themeTitle} @click=${this._toggleTheme}>
                    <platform-icon name=${themeIcon} size="16"></platform-icon>
                </button>
                <span class="header-title">${this.t('operator.page_title')}</span>
            </div>
            <div class="queues-bar">${this._renderQueues()}</div>
            <div class="body">
                <div class="kanban">${this._renderKanban()}</div>
                ${this._selectedTaskId
                    ? html`<div class="detail-panel">${this._renderDetail()}</div>`
                    : ''}
            </div>
        `;
    }
}

customElements.define('operator-page', OperatorPage);
