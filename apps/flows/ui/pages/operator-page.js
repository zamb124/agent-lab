/**
 * OperatorPage — рабочее место оператора.
 *
 * Состав:
 *   - Шапка: ссылка обратно в /flows, переключатель темы, заголовок.
 *   - Полоса очередей: chips с join/leave, форма создания (admin/owner).
 *   - Канбан задач по статусам STATUSES (open/claimed/user_dialog/awaiting_agent/completed/cancelled).
 *   - Панель деталей выбранной задачи: history (a2a messages) + dialog_log
 *     (operator dialog), composer с аттачем файлов и smart-кнопками.
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
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
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
                border-radius: var(--radius-md);
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
                flex: 1; min-width: 0; overflow-x: auto;
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
            .task-card-title { font-weight: var(--font-medium); }
            .task-card-meta { font-size: var(--text-xs); color: var(--text-tertiary); margin-top: 2px; }
            .detail-panel {
                width: 420px; min-width: 420px; max-width: 50%;
                display: flex; flex-direction: column;
                border-left: 1px solid var(--border-subtle);
                padding: var(--space-3);
                overflow-y: auto; gap: var(--space-3);
            }
            .panel-title { font-size: var(--text-xs); font-weight: var(--font-semibold); text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-tertiary); }
            .dialog-entry {
                display: flex; flex-direction: column; gap: 2px;
                padding: var(--space-2); border-radius: var(--radius-md);
                background: var(--glass-solid-subtle); margin-bottom: var(--space-1);
            }
            .dialog-entry--user { background: var(--accent-subtle); }
            .dialog-entry--operator { background: var(--glass-solid-medium); }
            .dialog-role { font-size: var(--text-xs); color: var(--text-tertiary); font-weight: var(--font-semibold); }
            .composer { display: flex; flex-direction: column; gap: var(--space-2); margin-top: auto; }
            .composer-row { display: flex; gap: var(--space-2); align-items: center; }
            .composer-row glass-input { flex: 1; }
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
        this._refreshTasks();
    }

    _selectTask(taskId) {
        this._selectedTaskId = taskId;
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
            if (result?.file_id) {
                uploaded.push({ file_id: result.file_id, name: file.name });
            }
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
                        <input
                            type="text"
                            placeholder=${this.t('operator.queue_name_placeholder')}
                            .value=${this._queueName}
                            @input=${(e) => { this._queueName = e.target.value; }}
                        />
                        <input
                            type="text"
                            placeholder=${this.t('operator.queue_slug_placeholder')}
                            .value=${this._queueSlug}
                            @input=${(e) => { this._queueSlug = e.target.value; }}
                        />
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
                    : byStatus[status].map((task) => html`
                        <div
                            class="task-card"
                            ?active=${this._selectedTaskId === task.id}
                            @click=${() => this._selectTask(task.id)}
                        >
                            <div class="task-card-title">${
                                typeof task.handoff_title === 'string' && task.handoff_title.length > 0
                                    ? task.handoff_title
                                    : (typeof task.flow_display_name === 'string' && task.flow_display_name.length > 0
                                        ? task.flow_display_name
                                        : task.id)
                            }</div>
                            <div class="task-card-meta">${asString(task.handoff_message_preview)}</div>
                            <div class="task-card-meta"><code>${task.flow_id}</code> / ${
                                typeof task.skill_id === 'string' && task.skill_id.length > 0 ? task.skill_id : 'base'
                            }</div>
                        </div>
                    `)}
            </div>
        `)}`;
    }

    _detailHandoffMode(detail) {
        const taskMeta = isPlainObject(detail?.task) && isPlainObject(detail.task.metadata) ? detail.task.metadata : null;
        const directMeta = isPlainObject(detail?.metadata) ? detail.metadata : null;
        const meta = taskMeta !== null ? taskMeta : (directMeta !== null ? directMeta : {});
        const mode = meta.handoff_mode;
        return mode === 'takeover' ? 'takeover' : 'single_reply';
    }

    _renderDialog(detail) {
        const dialogMessages = isPlainObject(detail) && Array.isArray(detail.dialog_messages) ? detail.dialog_messages : [];
        const history = dialogMessages
            .filter((m) => (m.role === 'user' || m.role === 'agent'))
            .map((m) => ({
                role: m.role,
                text: asArray(m.parts).filter((p) => p.kind === 'text' && p.text).map((p) => p.text).join('\n'),
            }))
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
        const status = detail?.task?.status;
        if (status === 'open') {
            return html`<glass-button @click=${this._onClaim}>${this.t('operator.btn_claim')}</glass-button>`;
        }
        const mode = this._detailHandoffMode(detail);
        return html`
            ${this._pendingFiles.length > 0
                ? html`
                    <div class="pending-files">
                        ${this._pendingFiles.map((f, i) => html`
                            <span class="pending-file">
                                <platform-icon name="file" size="12"></platform-icon>
                                <span>${f.name}</span>
                                <button type="button" @click=${() => this._removePendingFile(i)}>
                                    <platform-icon name="close" size="10"></platform-icon>
                                </button>
                            </span>
                        `)}
                    </div>
                `
                : ''}
            <input type="file" id="op-file-input" multiple hidden @change=${this._onFilesSelected} />
            <div class="composer-row">
                <glass-button title=${this.t('operator.tooltip_attach_file')} @click=${() => this.shadowRoot.getElementById('op-file-input').click()}>
                    <platform-icon name="paperclip" size="16"></platform-icon>
                </glass-button>
                <glass-input
                    .value=${this._composerDraft}
                    placeholder=${mode === 'takeover'
                        ? this.t('operator.placeholder_composer')
                        : this.t('operator.placeholder_single_reply')}
                    @input=${(e) => { this._composerDraft = asString(e.target.value); }}
                    @keydown=${(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            void this._onSendMessage();
                        }
                    }}
                ></glass-input>
                <glass-button @click=${() => void this._onSendMessage()}>${this.t('operator.btn_send')}</glass-button>
                <glass-button variant="primary" @click=${() => void this._onComplete()}>
                    ${mode === 'takeover'
                        ? this.t('operator.tooltip_reply_and_close')
                        : this.t('operator.btn_complete')}
                </glass-button>
            </div>
        `;
    }

    _renderDetail() {
        if (!this._selectedTaskId) {
            return html`<div class="empty">${this.t('operator.select_task')}</div>`;
        }
        const detail = this._taskGet.lastResult;
        if (this._taskGet.busy && !detail) {
            return html`<div class="empty"><glass-spinner></glass-spinner></div>`;
        }
        if (!detail) {
            return html`<div class="empty">${this.t('operator.no_detail')}</div>`;
        }
        return html`
            <div class="panel-title">${
                isPlainObject(detail.task) && typeof detail.task.handoff_title === 'string' && detail.task.handoff_title.length > 0
                    ? detail.task.handoff_title
                    : (isPlainObject(detail.task) ? detail.task.id : '')
            }</div>
            ${this._renderDialog(detail)}
            <div class="composer">${this._renderComposer(detail)}</div>
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
                <div class="detail-panel">${this._renderDetail()}</div>
            </div>
        `;
    }
}

customElements.define('operator-page', OperatorPage);
