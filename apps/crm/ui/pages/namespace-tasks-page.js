import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { resolveFileIconKey } from '@platform/services/icon.service.js';
import { CRMStore } from '../store/crm.store.js';
import { ensureKnowledgeImportPortalStyles } from '../styles/knowledge-import-portal-styles.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/file-text-preview-modal.js';
import '../modals/ai-analysis-modal.js';

const MAX_INLINE_TEXT = 100000;
const POLL_MS = 3000;

function namespaceNameFromStore() {
    const c = CRMStore.state.namespaces.current;
    if (typeof c === 'string' && c.trim()) {
        return c.trim();
    }
    if (c && typeof c === 'object' && typeof c.name === 'string' && c.name.trim()) {
        return c.name.trim();
    }
    return 'default';
}

export class NamespaceTasksPage extends PlatformElement {
    static properties = {
        _tasks: { state: true },
        _loading: { state: true },
        _taskTypeFilter: { state: true },
        _wizardOpen: { state: true },
        _wizardStep: { state: true },
        _selectedTypeIds: { state: true },
        _mode: { state: true },
        _pasteText: { state: true },
        _pendingFiles: { state: true },
        _uploadingFiles: { state: true },
        _dropzoneActive: { state: true },
        _resolvedSource: { state: true },
        _previewOpen: { state: true },
        _splitByHeadings: { state: true },
        _chunkMaxChars: { state: true },
        _starting: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; overflow: hidden; }
            .container {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                height: 100%;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
                overflow-y: auto;
                overflow-x: hidden;
                padding: var(--space-2);
            }
            .section {
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-xl);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .hero { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
            .hero-title { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-lg); font-weight: 700; }
            .back-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                background: none;
                border: none;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                padding: 0;
            }
            .back-btn:hover { color: var(--text-primary); }
            .save-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                border: 1px solid var(--accent);
                background: var(--accent);
                color: var(--platform-btn-primary-text);
                border-radius: var(--radius-md);
                padding: var(--space-2) var(--space-4);
                cursor: pointer;
            }
            .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .import-open-detail-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                border-radius: var(--radius-md);
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                font-size: var(--text-sm);
                font-weight: 600;
                border: 1px solid rgba(74, 222, 128, 0.65);
                color: #86efac;
                background: rgba(22, 101, 52, 0.42);
                box-shadow:
                    0 0 0 1px rgba(74, 222, 128, 0.22),
                    inset 0 0 12px rgba(34, 197, 94, 0.18);
                transition:
                    background-color 0.15s ease,
                    border-color 0.15s ease,
                    color 0.15s ease,
                    box-shadow 0.15s ease;
            }
            .import-open-detail-btn:hover {
                border-color: #4ade80;
                color: #bbf7d0;
                background: rgba(21, 128, 61, 0.52);
                box-shadow:
                    0 0 14px rgba(34, 197, 94, 0.45),
                    inset 0 0 16px rgba(22, 163, 74, 0.28);
            }
            .import-open-detail-btn platform-icon {
                flex-shrink: 0;
                color: inherit;
            }
            :host-context([data-theme='light']) .import-open-detail-btn {
                border-color: rgba(22, 163, 74, 0.55);
                color: #15803d;
                background: rgba(220, 252, 231, 0.9);
                box-shadow:
                    0 0 0 1px rgba(74, 222, 128, 0.35),
                    inset 0 0 10px rgba(187, 247, 208, 0.55);
            }
            :host-context([data-theme='light']) .import-open-detail-btn:hover {
                border-color: #16a34a;
                color: #166534;
                background: rgba(187, 247, 208, 0.96);
                box-shadow: 0 0 16px rgba(34, 197, 94, 0.35);
            }
            .imports-table-shell {
                width: 100%;
                border-radius: var(--radius-xl);
                border: 1px solid var(--crm-stroke);
                overflow: hidden;
                background: var(--crm-surface-elevated);
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
            }
            table.imports-table {
                width: 100%;
                border-collapse: collapse;
                font-size: var(--text-sm);
            }
            .imports-table thead th {
                text-align: left;
                padding: var(--space-3) var(--space-3);
                border-bottom: 1px solid var(--crm-stroke);
                color: var(--text-secondary);
                font-weight: 600;
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                background: var(--crm-surface-muted);
                vertical-align: middle;
            }
            .imports-table tbody td {
                text-align: left;
                padding: var(--space-3) var(--space-3);
                border-bottom: 1px solid var(--crm-stroke);
                vertical-align: middle;
                transition: background-color 0.22s ease;
            }
            .imports-table tbody tr:last-child td {
                border-bottom: none;
            }
            .imports-table tbody tr:hover td {
                background: var(--crm-surface-muted);
            }
            .imports-table th.th-num,
            .imports-table td.td-num {
                text-align: right;
                font-variant-numeric: tabular-nums;
            }
            .imports-table th.th-actions {
                text-align: center;
            }
            .imports-list-loading {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0 0 var(--space-2) 0;
                min-height: 1.35em;
            }
            .import-actions-cell {
                min-width: 0;
                text-align: center;
            }
            .import-actions-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                justify-content: center;
            }
            .import-icon-btn {
                width: 36px;
                height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                cursor: pointer;
                padding: 0;
                flex-shrink: 0;
                transition:
                    background-color 0.15s ease,
                    border-color 0.15s ease,
                    color 0.15s ease,
                    box-shadow 0.15s ease;
            }
            .import-icon-btn:hover {
                background: var(--crm-surface-elevated);
                color: var(--text-primary);
            }
            .import-icon-btn--cancel {
                border-color: rgba(251, 191, 36, 0.5);
                color: #fbbf24;
            }
            .import-icon-btn--cancel:hover {
                border-color: rgba(253, 224, 71, 0.85);
                color: #fcd34d;
                box-shadow: 0 0 0 1px rgba(251, 191, 36, 0.25);
            }
            .import-cancel-glyph {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 18px;
                height: 18px;
                flex-shrink: 0;
                color: inherit;
            }

            .import-cancel-glyph platform-icon {
                display: block;
            }
            .import-icon-btn--rollback {
                border-color: rgba(248, 113, 113, 0.65);
                color: #fca5a5;
                background: rgba(127, 29, 29, 0.35);
                box-shadow:
                    0 0 0 1px rgba(248, 113, 113, 0.2),
                    inset 0 0 12px rgba(220, 38, 38, 0.15);
            }
            .import-icon-btn--rollback:hover {
                border-color: #f87171;
                color: #fecaca;
                background: rgba(153, 27, 27, 0.45);
                box-shadow:
                    0 0 14px rgba(239, 68, 68, 0.45),
                    inset 0 0 16px rgba(185, 28, 28, 0.25);
            }
            .import-icon-btn--retry {
                border-color: rgba(99, 102, 241, 0.5);
                color: #a5b4fc;
                background: rgba(49, 46, 129, 0.3);
            }
            .import-icon-btn--retry:hover {
                border-color: #818cf8;
                color: #c7d2fe;
                background: rgba(67, 56, 202, 0.4);
            }
            .import-icon-btn--view-error {
                border-color: rgba(251, 191, 36, 0.5);
                color: #fde68a;
                background: rgba(120, 53, 15, 0.25);
            }
            .import-icon-btn--view-error:hover {
                border-color: #fbbf24;
                color: #fef3c7;
                background: rgba(146, 64, 14, 0.35);
            }
            :host-context([data-theme='light']) .import-icon-btn--cancel {
                border-color: rgba(217, 119, 6, 0.45);
                color: #b45309;
            }
            :host-context([data-theme='light']) .import-icon-btn--cancel:hover {
                border-color: rgba(180, 83, 9, 0.75);
                color: #92400e;
            }
            :host-context([data-theme='light']) .import-icon-btn--rollback {
                border-color: rgba(220, 38, 38, 0.55);
                color: #b91c1c;
                background: rgba(254, 226, 226, 0.85);
                box-shadow:
                    0 0 0 1px rgba(248, 113, 113, 0.35),
                    inset 0 0 10px rgba(254, 202, 202, 0.5);
            }
            :host-context([data-theme='light']) .import-icon-btn--rollback:hover {
                border-color: #dc2626;
                color: #991b1b;
                background: rgba(254, 202, 202, 0.95);
                box-shadow: 0 0 16px rgba(220, 38, 38, 0.35);
            }
            .mono { font-family: ui-monospace, monospace; font-size: var(--text-xs); }
            .ki-import-tag {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 5px 11px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                font-weight: 600;
                line-height: 1.2;
                white-space: nowrap;
                max-width: 100%;
                box-sizing: border-box;
            }
            .ki-import-tag--ok {
                background: rgba(34, 197, 94, 0.22);
                color: #86efac;
            }
            .ki-import-tag--bad {
                background: rgba(244, 63, 94, 0.2);
                color: #fda4af;
            }
            .ki-import-tag--warn {
                background: rgba(251, 191, 36, 0.22);
                color: #fde047;
            }
            .ki-import-tag--muted {
                background: rgba(148, 163, 184, 0.2);
                color: #cbd5e1;
            }
            .ki-import-tag--mode-accent {
                background: rgba(153, 166, 249, 0.22);
                color: #c7d2fe;
            }
            .ki-import-tag--mode-soft {
                background: rgba(148, 163, 184, 0.16);
                color: #e2e8f0;
            }
            :host-context([data-theme='light']) .ki-import-tag--ok {
                background: rgba(34, 197, 94, 0.14);
                color: #15803d;
            }
            :host-context([data-theme='light']) .ki-import-tag--bad {
                background: rgba(244, 63, 94, 0.1);
                color: #be123c;
            }
            :host-context([data-theme='light']) .ki-import-tag--warn {
                background: rgba(251, 191, 36, 0.2);
                color: #b45309;
            }
            :host-context([data-theme='light']) .ki-import-tag--muted {
                background: rgba(100, 116, 139, 0.12);
                color: #475569;
            }
            :host-context([data-theme='light']) .ki-import-tag--mode-accent {
                background: rgba(99, 102, 241, 0.14);
                color: #4f46e5;
            }
            :host-context([data-theme='light']) .ki-import-tag--mode-soft {
                background: rgba(100, 116, 139, 0.1);
                color: #64748b;
            }
            .review-badge { display: inline-block; padding: 4px 10px; border-radius: var(--radius-full); font-size: var(--text-xs); font-weight: 600; }
            .review-badge.pending { background: rgba(251, 191, 36, 0.22); color: #fde047; }
            .review-badge.done { background: rgba(34, 197, 94, 0.22); color: #86efac; }
            .review-badge.na { color: var(--text-tertiary); font-weight: 500; }
            .tasks-filter-bar { display: flex; gap: var(--space-1); flex-wrap: wrap; margin-bottom: var(--space-2); }
            .tasks-filter-btn { background: none; border: 1px solid var(--crm-stroke); border-radius: var(--radius-full); padding: 4px 14px; font-size: var(--text-sm); color: var(--text-secondary); cursor: pointer; transition: all 0.15s; }
            .tasks-filter-btn.active { background: var(--primary-soft); border-color: var(--primary); color: var(--primary); font-weight: 600; }
            .tasks-filter-btn:hover:not(.active) { border-color: var(--text-tertiary); }
            .task-progress-wrap { width: 100%; height: 4px; background: var(--crm-stroke); border-radius: 2px; margin-top: 4px; }
            .task-progress-bar { height: 4px; background: var(--primary); border-radius: 2px; transition: width 0.4s; }
            .task-stage-label { font-size: var(--text-xs); color: var(--text-tertiary); margin-top: 2px; }
            .task-type-badge { display: inline-block; padding: 2px 8px; border-radius: var(--radius-full); font-size: var(--text-xs); font-weight: 600; background: var(--crm-stroke); color: var(--text-secondary); }
            .task-name-cell { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--text-sm); }
            :host-context([data-theme='light']) .review-badge.pending {
                background: rgba(251, 191, 36, 0.2);
                color: #b45309;
            }
            :host-context([data-theme='light']) .review-badge.done {
                background: rgba(34, 197, 94, 0.14);
                color: #15803d;
            }

            /* Mobile cards */
            .task-cards { display: none; flex-direction: column; gap: var(--space-3); }
            .task-card {
                background: var(--crm-surface-elevated);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-xl);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .task-card-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .task-card-title {
                font-size: var(--text-base);
                font-weight: 600;
                color: var(--text-primary);
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .task-card-meta {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .task-card-progress {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            .task-card-stats {
                display: flex;
                gap: var(--space-4);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .task-card-stat { display: flex; flex-direction: column; gap: 2px; }
            .task-card-stat-label { font-size: var(--text-xs); color: var(--text-tertiary); }
            .task-card-stat-val { font-weight: 600; color: var(--text-primary); font-variant-numeric: tabular-nums; }
            .task-card-actions {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
                border-top: 1px solid var(--crm-stroke);
                padding-top: var(--space-3);
            }
            .task-card-action-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                transition: all 0.15s;
            }
            .task-card-action-btn:hover { background: var(--crm-surface-elevated); color: var(--text-primary); }
            .task-card-action-btn--stop { border-color: rgba(251,191,36,0.5); color: #fbbf24; }
            .task-card-action-btn--stop:hover { border-color: rgba(253,224,71,0.85); color: #fcd34d; }
            .task-card-action-btn--danger { border-color: rgba(239,68,68,0.4); color: #ef4444; }
            .task-card-action-btn--danger:hover { border-color: rgba(239,68,68,0.7); }

            @media (max-width: 700px) {
                .imports-table-shell { display: none; }
                .task-cards { display: flex; }
                .container { padding: var(--space-2); }
            }
        `,
    ];

    constructor() {
        super();
        this._tasks = [];
        this._loading = false;
        this._taskTypeFilter = null;
        this._wizardOpen = false;
        this._wizardStep = 0;
        this._selectedTypeIds = [];
        this._mode = 'graph';
        this._pasteText = '';
        this._pendingFiles = [];
        this._uploadingFiles = false;
        this._dropzoneActive = false;
        this._resolvedSource = null;
        this._previewOpen = false;
        this._splitByHeadings = false;
        this._chunkMaxChars = 50000;
        this._starting = false;
        this._pollTimer = null;
        this._unsub = null;
    }

    _getPendingFileIds() {
        return (this._pendingFiles || []).map((f) => f.file_id).filter((id) => typeof id === 'string' && id.trim());
    }

    _singlePendingFileId() {
        const ids = this._getPendingFileIds();
        return ids.length === 1 ? ids[0] : '';
    }

    _fileIconKeyForPending(entry) {
        const name = typeof entry?.original_name === 'string' ? entry.original_name : '';
        const mime = typeof entry?.content_type === 'string' ? entry.content_type : '';
        return resolveFileIconKey(name, mime);
    }

    connectedCallback() {
        super.connectedCallback();
        ensureKnowledgeImportPortalStyles();
        this._unsub = CRMStore.subscribe(() => this.requestUpdate());
        this._pollTimer = window.setInterval(() => {
            this._maybePoll();
        }, POLL_MS);
        this._handleTaskWsNotification = this._onTaskWsNotification.bind(this);
        window.addEventListener('platform-notification-received', this._handleTaskWsNotification);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsub?.();
        if (this._pollTimer) {
            window.clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
        if (this._handleTaskWsNotification) {
            window.removeEventListener('platform-notification-received', this._handleTaskWsNotification);
            this._handleTaskWsNotification = null;
        }
    }

    async firstUpdated() {
        await this._loadTasks();
    }

    _onTaskWsNotification(event) {
        const n = event.detail;
        if (!n || n.service !== 'crm') {
            return;
        }
        const ns = namespaceNameFromStore();
        if (
            (n.type === 'crm_task_updated' || n.type === 'crm_daily_summary_updated') &&
            n.data?.namespace === ns
        ) {
            this._loadTasks({ silent: true });
        }
    }

    _maybePoll() {
        const active =
            Array.isArray(this._tasks) &&
            this._tasks.some((r) => r.status === 'running' || r.status === 'pending');
        if (active) {
            this._loadTasks({ silent: true });
        }
    }

    async _loadTasks(options = {}) {
        const silent = Boolean(options.silent);
        const ns = namespaceNameFromStore();
        const crmApi = this.services.get('crmApi');
        if (!silent) {
            this._loading = true;
        }
        try {
            this._tasks = await crmApi.listTasks(ns, 100);
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        } finally {
            if (!silent) {
                this._loading = false;
            }
        }
    }

    _filteredTasks() {
        const tasks = Array.isArray(this._tasks) ? this._tasks : [];
        if (!this._taskTypeFilter) {
            return tasks;
        }
        return tasks.filter((r) => r.task_type === this._taskTypeFilter);
    }

    _openWizard() {
        this._wizardStep = 0;
        this._selectedTypeIds = [];
        this._mode = 'graph';
        this._pasteText = '';
        this._pendingFiles = [];
        this._uploadingFiles = false;
        this._dropzoneActive = false;
        this._resolvedSource = null;
        this._splitByHeadings = false;
        this._chunkMaxChars = 50000;
        this._wizardOpen = true;
    }

    _closeWizard() {
        this._wizardOpen = false;
        this._dropzoneActive = false;
    }

    _allowedEntityTypes() {
        const ns = namespaceNameFromStore();
        const types = CRMStore.state.entities.entityTypes || [];
        return types.filter((t) => {
            const ids = Array.isArray(t.namespace_ids) ? t.namespace_ids : [];
            return ids.includes(ns);
        });
    }

    _toggleType(typeId) {
        const id = String(typeId).trim();
        if (!id) {
            return;
        }
        const set = new Set(this._selectedTypeIds);
        if (set.has(id)) {
            set.delete(id);
        } else {
            set.add(id);
        }
        this._selectedTypeIds = Array.from(set);
    }

    /**
     * Иконка типа для мастера: из API или запасной маппинг (имена из platform-icon).
     */
    _importWizardIconForType(entityType) {
        const typeId = String(entityType?.type_id || '').trim();
        const byTypeId = {
            note: 'doc-detail',
            meeting: 'calendar-solid',
            call: 'phone-call',
            task: 'checklist',
            member: 'user-shield',
            contact: 'user',
            company: 'building',
            namespace: 'layers',
            organization: 'building-one',
            project: 'folder',
            topic: 'target',
        };
        if (typeId && byTypeId[typeId]) {
            return byTypeId[typeId];
        }
        const raw = typeof entityType?.icon === 'string' ? entityType.icon.trim() : '';
        const apiAliases = {
            users: 'avatar',
            phone: 'phone-call',
        };
        if (raw && apiAliases[raw]) {
            return apiAliases[raw];
        }
        if (raw) {
            return raw;
        }
        return 'box';
    }

    _wizardNext() {
        if (this._wizardStep < 4) {
            this._wizardStep += 1;
        }
    }

    _wizardBack() {
        if (this._wizardStep > 0) {
            this._wizardStep -= 1;
        }
    }

    async _onKiFileInputChange(ev) {
        const input = ev.target;
        const files = input.files ? Array.from(input.files) : [];
        input.value = '';
        if (files.length === 0) {
            return;
        }
        await this._uploadFilesArray(files);
    }

    async _uploadFilesArray(files) {
        const crmApi = this.services.get('crmApi');
        this._uploadingFiles = true;
        this._resolvedSource = null;
        try {
            const next = [...this._pendingFiles];
            for (const file of files) {
                const res = await crmApi.uploadFile(file);
                if (!res || typeof res.file_id !== 'string') {
                    throw new Error(this.i18n.t('knowledge_import.err_upload'));
                }
                const name =
                    typeof res.original_name === 'string' && res.original_name.trim()
                        ? res.original_name.trim()
                        : (typeof file.name === 'string' && file.name.trim() ? file.name.trim() : res.file_id);
                const ct =
                    typeof res.content_type === 'string' && res.content_type.trim()
                        ? res.content_type.trim()
                        : (typeof file.type === 'string' ? file.type : '');
                next.push({
                    file_id: res.file_id,
                    original_name: name,
                    content_type: ct,
                });
            }
            this._pendingFiles = next;
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        } finally {
            this._uploadingFiles = false;
        }
    }

    _openKiFilePicker(ev) {
        let input = null;
        if (ev && ev.currentTarget instanceof HTMLElement) {
            input = ev.currentTarget.querySelector('input.ki-import-file-input[type="file"]');
        }
        if (!(input instanceof HTMLInputElement) && typeof document !== 'undefined') {
            const host = document.querySelector('.crm-import-glass-content .ki-import-file-input[type="file"]');
            input = host instanceof HTMLInputElement ? host : null;
        }
        if (input instanceof HTMLInputElement) {
            input.click();
        }
    }

    _onDropzoneDragEnter(ev) {
        ev.preventDefault();
        this._dropzoneActive = true;
    }

    _onDropzoneDragOver(ev) {
        ev.preventDefault();
        if (ev.dataTransfer) {
            ev.dataTransfer.dropEffect = 'copy';
        }
    }

    _onDropzoneDragLeave(ev) {
        ev.preventDefault();
        const zone = ev.currentTarget;
        const rel = ev.relatedTarget;
        if (rel instanceof Node && zone.contains(rel)) {
            return;
        }
        this._dropzoneActive = false;
    }

    async _onDropzoneDrop(ev) {
        ev.preventDefault();
        this._dropzoneActive = false;
        const dt = ev.dataTransfer;
        const raw = dt && dt.files ? Array.from(dt.files) : [];
        if (raw.length === 0) {
            return;
        }
        await this._uploadFilesArray(raw);
    }

    _removePendingFile(index) {
        const next = [...this._pendingFiles];
        next.splice(index, 1);
        this._pendingFiles = next;
        this._resolvedSource = null;
    }

    _buildResolvedSourceFromFields(openPreviewForSingleFileOnly) {
        const t = (this._pasteText || '').trim();
        const fids = this._getPendingFileIds();
        if (fids.length === 0 && !t) {
            this.warning(this.i18n.t('knowledge_import.warn_need_text'));
            return false;
        }
        if (t.length > MAX_INLINE_TEXT) {
            this.error(this.i18n.t('knowledge_import.err_text_too_long', { max: String(MAX_INLINE_TEXT) }));
            return false;
        }
        if (fids.length === 1 && !t && openPreviewForSingleFileOnly) {
            this._previewOpen = true;
            return false;
        }
        const src = {};
        if (t) {
            src.source_text = this._pasteText;
        }
        if (fids.length === 1) {
            src.source_file_id = fids[0];
        } else if (fids.length > 1) {
            src.source_file_ids = fids;
        }
        this._resolvedSource = src;
        return true;
    }

    _namespaceSummaryLabel() {
        const c = CRMStore.state.namespaces.current;
        if (c && typeof c === 'object') {
            const desc = typeof c.description === 'string' && c.description.trim() ? c.description.trim() : '';
            if (desc) {
                return desc;
            }
            const name = typeof c.name === 'string' && c.name.trim() ? c.name.trim() : '';
            if (name === 'default' && c.is_default === true) {
                return this.i18n.t('knowledge_import.summary_namespace_default');
            }
            if (name) {
                return name;
            }
        }
        if (typeof c === 'string' && c.trim()) {
            const slug = c.trim();
            if (slug === 'default') {
                return this.i18n.t('knowledge_import.summary_namespace_default');
            }
            return slug;
        }
        return this.i18n.t('knowledge_import.summary_namespace_default');
    }

    _importModeSummaryLabel() {
        if (this._mode === 'graph') {
            return this.i18n.t('knowledge_import.mode_graph');
        }
        if (this._mode === 'notes_only') {
            return this.i18n.t('knowledge_import.mode_notes');
        }
        throw new Error(`Unknown import mode: ${this._mode}`);
    }

    _summaryTypesHumanLine(allowedTypes) {
        if (!this._selectedTypeIds.length) {
            return this.i18n.t('knowledge_import.all_types');
        }
        const labels = this._selectedTypeIds.map((id) => {
            const t = allowedTypes.find((x) => x.type_id === id);
            const label = typeof t?.name === 'string' && t.name.trim() ? t.name.trim() : '';
            if (!label) {
                throw new Error(`Entity type not in current space: ${id}`);
            }
            return label;
        });
        return labels.join(', ');
    }

    _resolvedSourceFileIds() {
        const r = this._resolvedSource;
        if (!r || typeof r !== 'object') {
            return [];
        }
        const ids = [];
        if (typeof r.source_file_id === 'string' && r.source_file_id.trim()) {
            ids.push(r.source_file_id.trim());
        }
        if (Array.isArray(r.source_file_ids)) {
            for (const id of r.source_file_ids) {
                const s = String(id).trim();
                if (s) {
                    ids.push(s);
                }
            }
        }
        return ids;
    }

    _summaryFileThumbEntries() {
        const pending = this._pendingFiles || [];
        return this._resolvedSourceFileIds().map((fileId) => {
            const entry = pending.find((p) => p.file_id === fileId);
            const name =
                entry && typeof entry.original_name === 'string' && entry.original_name.trim()
                    ? entry.original_name.trim()
                    : fileId;
            const mime = entry && typeof entry.content_type === 'string' ? entry.content_type : '';
            const iconKey = this._fileIconKeyForPending(
                entry || { original_name: name, content_type: mime, file_id: fileId },
            );
            return { iconKey, title: name };
        });
    }

    _summaryHasResolvedPastedText() {
        const r = this._resolvedSource;
        return Boolean(r && typeof r === 'object' && typeof r.source_text === 'string' && r.source_text.trim().length > 0);
    }

    _summarySourcesSection() {
        const thumbs = this._summaryFileThumbEntries();
        const hasText = this._summaryHasResolvedPastedText();
        if (thumbs.length === 0 && !hasText) {
            return '';
        }
        return html`
            <div class="ki-step4-card ki-step4-card--wide" role="listitem">
                <div class="ki-step4-card-label">${this.i18n.t('knowledge_import.summary_sources')}</div>
                <div class="ki-step4-sources-body">
                    ${thumbs.length > 0
                        ? html`
                              <div class="ki-step4-file-strip" role="list">
                                  ${thumbs.map(
                                      (item) => html`
                                          <span class="ki-step4-file-mini" role="listitem" title=${item.title}>
                                              <platform-icon
                                                  class="ki-step4-file-mini-icon"
                                                  file-icon
                                                  name=${item.iconKey}
                                                  size="20"
                                              ></platform-icon>
                                          </span>
                                      `,
                                  )}
                              </div>
                          `
                        : ''}
                    ${hasText
                        ? html`<div class="ki-step4-text-badge">${this.i18n.t('knowledge_import.summary_pasted_text')}</div>`
                        : ''}
                </div>
            </div>
        `;
    }

    _onWizardNextFromStep3() {
        if (!this._resolvedSource) {
            if (!this._buildResolvedSourceFromFields(true)) {
                return;
            }
        }
        this._wizardNext();
    }

    _onPreviewConfirm(ev) {
        const detail = ev.detail || {};
        const text = typeof detail.text === 'string' ? detail.text : '';
        const original = typeof detail.initialText === 'string' ? detail.initialText : '';
        const unchanged = text === original;
        const singleId = this._singlePendingFileId();
        if (!singleId) {
            this._previewOpen = false;
            return;
        }
        if (unchanged) {
            this._resolvedSource = { source_file_id: singleId };
        } else if (text.length > MAX_INLINE_TEXT) {
            this.error(this.i18n.t('knowledge_import.err_text_too_long', { max: String(MAX_INLINE_TEXT) }));
            this._resolvedSource = null;
            return;
        } else {
            this._resolvedSource = { source_text: text };
        }
        this._previewOpen = false;
        this._wizardStep = 4;
    }

    _onPreviewCancel() {
        this._previewOpen = false;
        this._pendingFiles = [];
    }

    async _startImport() {
        const ns = namespaceNameFromStore();
        if (!this._resolvedSource) {
            if (!this._buildResolvedSourceFromFields(false)) {
                return;
            }
        }
        const body = {
            namespace: ns,
            mode: this._mode,
            extract_entity_types: this._selectedTypeIds.length > 0 ? this._selectedTypeIds : null,
            split_by_headings: this._splitByHeadings,
            chunk_max_chars: this._chunkMaxChars,
            ...this._resolvedSource,
        };
        const crmApi = this.services.get('crmApi');
        this._starting = true;
        this._closeWizard();
        try {
            await crmApi.startKnowledgeImportTask(body);
            this.success(this.i18n.t('task_tracker.started'));
            await this._loadTasks({ silent: true });
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        } finally {
            this._starting = false;
        }
    }

    async _retryRow(taskId) {
        const crmApi = this.services.get('crmApi');
        try {
            await crmApi.retryTask(taskId);
            await this._loadTasks({ silent: true });
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        }
    }

    async _viewError(row) {
        const { platformConfirm } = await import('@platform/lib/components/platform-confirm-modal.js');
        const errorText = typeof row.error_message === 'string' ? row.error_message : String(row.error_message || '');
        await platformConfirm(errorText, {
            title: this.i18n.t('task_tracker.action_view_error'),
            confirmText: this.i18n.t('close', {}, 'common'),
            cancelText: null,
        });
    }

    async _cancelRow(id) {
        const crmApi = this.services.get('crmApi');
        try {
            await crmApi.cancelTask(id);
            await this._loadTasks({ silent: true });
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        }
    }

    async _rollbackRow(id) {
        const confirmed = await platformConfirm(this.i18n.t('knowledge_import.confirm_rollback'), {
            title: this.i18n.t('knowledge_import.rollback_modal_title'),
            confirmText: this.i18n.t('knowledge_import.action_rollback'),
            cancelText: this.i18n.t('cancel', {}, 'common'),
            variant: 'danger',
            confirmVariant: 'danger',
        });
        if (!confirmed) {
            return;
        }
        const crmApi = this.services.get('crmApi');
        try {
            await crmApi.rollbackTask(id);
            await this._loadTasks({ silent: true });
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        }
    }

    _spacesSettingsUrl() {
        return `${window.location.origin || ''}/crm/spaces`;
    }

    _canOpenImportDetail(row) {
        if (!row || typeof row !== 'object') {
            return false;
        }
        if (!['completed', 'failed', 'cancelled'].includes(row.status)) {
            return false;
        }
        const entN = Array.isArray(row.data?.created_entity_ids) ? row.data?.created_entity_ids.length : 0;
        const relN = Array.isArray(row.data?.created_relationship_ids) ? row.data?.created_relationship_ids.length : 0;
        return entN > 0 || relN > 0;
    }

    _importNeedsReview(row) {
        if (!this._canOpenImportDetail(row)) {
            return false;
        }
        return row.data?.review_completed_at == null || row.data?.review_completed_at === '';
    }

    _importJobStatusTheme(status) {
        const s = String(status || '').trim().toLowerCase();
        const map = {
            completed: 'ok',
            failed: 'bad',
            pending: 'warn',
            running: 'warn',
            cancelled: 'muted',
            rolled_back: 'muted',
        };
        const theme = map[s];
        if (!theme) {
            throw new Error(`Unknown knowledge import job status: ${status}`);
        }
        return theme;
    }

    _importJobStatusLabel(status) {
        const s = String(status || '').trim().toLowerCase();
        return this.i18n.t(`knowledge_import.job_status_${s}`);
    }

    _importJobStatusPill(status) {
        const theme = this._importJobStatusTheme(status);
        const label = this._importJobStatusLabel(status);
        return html`<span class="ki-import-tag ki-import-tag--${theme}">${label}</span>`;
    }

    _importListModeVariant(mode) {
        const m = String(mode || '').trim().toLowerCase();
        if (m === 'graph') {
            return 'accent';
        }
        if (m === 'notes_only') {
            return 'soft';
        }
        throw new Error(`Unknown knowledge import mode: ${mode}`);
    }

    _importListModeLabel(mode) {
        const m = String(mode || '').trim().toLowerCase();
        if (m === 'graph') {
            return this.i18n.t('knowledge_import.import_list_mode_graph');
        }
        if (m === 'notes_only') {
            return this.i18n.t('knowledge_import.import_list_mode_notes');
        }
        throw new Error(`Unknown knowledge import mode: ${mode}`);
    }

    _importListModePill(mode) {
        const variant = this._importListModeVariant(mode);
        const label = this._importListModeLabel(mode);
        return html`<span class="ki-import-tag ki-import-tag--mode-${variant}">${label}</span>`;
    }

    async _openImportReviewModal(importId) {
        const id = typeof importId === 'string' ? importId.trim() : '';
        if (!id) {
            return;
        }
        const crmApi = this.services.get('crmApi');
        let summary;
        try {
            summary = await crmApi.getTaskCreatedEntities(id);
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
            return;
        }
        const rows = Array.isArray(summary.entities) ? summary.entities : [];
        if (rows.length === 0) {
            const confirmed = await platformConfirm(
                this.i18n.t('knowledge_import.review_no_entities_body'),
                {
                    title: this.i18n.t('knowledge_import.review_no_entities_title'),
                    confirmText: this.i18n.t('knowledge_import.detail_approve'),
                },
            );
            if (confirmed) {
                await crmApi.completeTaskReview(id);
                this.success(this.i18n.t('knowledge_import.approve_success'));
                void this._loadTasks({ silent: true });
            }
            return;
        }
        try {
            await CRMStore.hydrateKnowledgeImportReview(crmApi, id, summary);
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
            return;
        }
        const analysisModal = document.createElement('ai-analysis-modal');
        document.body.appendChild(analysisModal);
        analysisModal.showModal();
        analysisModal.addEventListener('close', () => {
            CRMStore.clearKnowledgeImportReview();
            analysisModal.remove();
            void this._loadTasks({ silent: true });
        });
        analysisModal.addEventListener('saved', () => {
            this.success(this.i18n.t('knowledge_import.approve_success'));
            void this._loadTasks({ silent: true });
        });
    }

    render() {
        const ns = namespaceNameFromStore();
        const types = this._allowedEntityTypes();
        return html`
            <div class="container">
                <div class="section">
                    <button class="back-btn" type="button" @click=${() => CRMStore.setCurrentView('spaces')}>
                        <platform-icon name="arrow-left" size="14"></platform-icon>
                        ${this.i18n.t('task_tracker.back_spaces')}
                    </button>
                    <div class="hero">
                        <div class="hero-title">
                            <platform-icon name="tasks" size="18"></platform-icon>
                            ${this.i18n.t('task_tracker.title')}
                        </div>
                        <button class="save-btn" type="button" @click=${this._openWizard}>
                            <platform-icon name="plus" size="14"></platform-icon>
                            ${this.i18n.t('knowledge_import.cta_wizard')}
                        </button>
                    </div>
                    <div class="mono">${this.i18n.t('task_tracker.namespace_label')}: ${ns}</div>
                </div>

                <div class="section">
                    <div class="hero-title">${this.i18n.t('task_tracker.list_title')}</div>
                    <div class="tasks-filter-bar" role="group" aria-label=${this.i18n.t('task_tracker.filter_label')}>
                        ${[
                            { key: null, label: this.i18n.t('task_tracker.filter_all') },
                            { key: 'knowledge_import', label: this.i18n.t('task_tracker.filter_knowledge_import') },
                            { key: 'note_analyze', label: this.i18n.t('task_tracker.filter_note_analyze') },
                            { key: 'daily_summary', label: this.i18n.t('task_tracker.filter_daily_summary') },
                        ].map(({ key, label }) => html`
                            <button
                                type="button"
                                class="tasks-filter-btn ${this._taskTypeFilter === key ? 'active' : ''}"
                                @click=${() => { this._taskTypeFilter = key; }}
                            >${label}</button>
                        `)}
                    </div>
                    ${this._loading ? html`<div class="imports-list-loading">${this.i18n.t('task_tracker.loading')}</div>` : ''}
                    <div class="imports-table-shell">
                        <table class="imports-table">
                            <thead>
                                <tr>
                                    <th scope="col">${this.i18n.t('task_tracker.col_status')}</th>
                                    <th scope="col">${this.i18n.t('task_tracker.col_type')}</th>
                                    <th scope="col">${this.i18n.t('task_tracker.col_name')}</th>
                                    <th class="th-num" scope="col">${this.i18n.t('task_tracker.col_notes')}</th>
                                    <th class="th-num" scope="col">${this.i18n.t('task_tracker.col_entities')}</th>
                                    <th class="th-num" scope="col">${this.i18n.t('task_tracker.col_rels')}</th>
                                    <th scope="col">${this.i18n.t('task_tracker.col_review')}</th>
                                    <th class="th-actions" scope="col">${this.i18n.t('knowledge_import.col_actions')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${(this._filteredTasks()).map((row) => {
                                    const isImport = row.task_type === 'knowledge_import';
                                    const isAnalyze = row.task_type === 'note_analyze';
                                    const isSummary = row.task_type === 'daily_summary' || row.task_type === 'period_summary';
                                    const entN = isImport ? (Array.isArray(row.data?.created_entity_ids) ? row.data.created_entity_ids.length : 0) : (row.data?.result_entities_count ?? 0);
                                    const relN = isImport ? (Array.isArray(row.data?.created_relationship_ids) ? row.data.created_relationship_ids.length : 0) : (row.data?.result_relationships_count ?? 0);
                                    const canRollback =
                                        isImport && ['completed', 'failed', 'cancelled'].includes(row.status) && ((Array.isArray(row.data?.created_entity_ids) ? row.data.created_entity_ids.length : 0) > 0 || (Array.isArray(row.data?.created_relationship_ids) ? row.data.created_relationship_ids.length : 0) > 0);
                                    const canDetail = isImport && this._canOpenImportDetail(row);
                                    const needsRev = canDetail && this._importNeedsReview(row);
                                    const stageLabel = this.i18n.t(`task.stage.${row.stage}`, {}, 'crm') || row.stage;
                                    const typeLabel = this.i18n.t(`task.type.${row.task_type}`, {}, 'crm') || row.task_type;
                                    const nameLabel = isAnalyze
                                        ? (row.data?.note_name || row.data?.note_id || '')
                                        : isImport
                                            ? this._importListModeLabel(row.data?.mode)
                                            : isSummary
                                                ? (row.data?.date_str || row.data?.date_from || '')
                                                : '';
                                    return html`
                                        <tr>
                                            <td>
                                                ${this._importJobStatusPill(row.status)}
                                                ${(row.status === 'running' || row.status === 'pending') ? html`
                                                    <div class="task-progress-wrap">
                                                        <div class="task-progress-bar" style="width: ${row.progress_pct || 0}%"></div>
                                                    </div>
                                                    <div class="task-stage-label">${stageLabel}</div>
                                                ` : ''}
                                            </td>
                                            <td><span class="task-type-badge">${typeLabel}</span></td>
                                            <td class="task-name-cell">${nameLabel}</td>
                                            <td class="td-num">${isImport ? (row.data?.notes_created_count ?? 0) : '—'}</td>
                                            <td class="td-num">${entN !== null && entN !== undefined ? entN : '—'}</td>
                                            <td class="td-num">${relN !== null && relN !== undefined ? relN : '—'}</td>
                                            <td>
                                                ${canDetail
                                                    ? html`<span class="review-badge ${needsRev ? 'pending' : 'done'}">${needsRev ? this.i18n.t('knowledge_import.review_pending') : this.i18n.t('knowledge_import.review_done')}</span>`
                                                    : html`<span class="review-badge na">—</span>`}
                                            </td>
                                            <td class="import-actions-cell">
                                                <div class="import-actions-row">
                                                    ${canDetail
                                                        ? html`<button
                                                              type="button"
                                                              class="import-open-detail-btn"
                                                              @click=${() => this._openImportReviewModal(row.task_id)}
                                                          >
                                                              <platform-icon name="doc-detail" size="16"></platform-icon>
                                                              <span>${this.i18n.t('knowledge_import.action_open_detail')}</span>
                                                          </button>`
                                                        : null}
                                                    ${row.status === 'running' || row.status === 'pending'
                                                        ? html`<button
                                                              type="button"
                                                              class="import-icon-btn import-icon-btn--cancel"
                                                              title=${this.i18n.t('knowledge_import.action_cancel')}
                                                              aria-label=${this.i18n.t('knowledge_import.action_cancel')}
                                                              @click=${() => this._cancelRow(row.task_id)}
                                                          >
                                                              <span class="import-cancel-glyph" aria-hidden="true">
                                                                  <platform-icon name="stop" size="16"></platform-icon>
                                                              </span>
                                                          </button>`
                                                        : null}
                                                    ${canRollback
                                                        ? html`<button
                                                              type="button"
                                                              class="import-icon-btn import-icon-btn--rollback"
                                                              title=${this.i18n.t('knowledge_import.action_rollback')}
                                                              aria-label=${this.i18n.t('knowledge_import.action_rollback')}
                                                              @click=${() => this._rollbackRow(row.task_id)}
                                                          >
                                                              <platform-icon name="undo" size="18"></platform-icon>
                                                          </button>`
                                                        : null}
                                                    ${(row.status === 'failed' || row.status === 'cancelled')
                                                        ? html`<button
                                                              type="button"
                                                              class="import-icon-btn import-icon-btn--retry"
                                                              title=${this.i18n.t('task_tracker.action_retry')}
                                                              aria-label=${this.i18n.t('task_tracker.action_retry')}
                                                              @click=${() => this._retryRow(row.task_id)}
                                                          >
                                                              <platform-icon name="refresh" size="16"></platform-icon>
                                                          </button>`
                                                        : null}
                                                    ${row.status === 'failed' && row.error_message
                                                        ? html`<button
                                                              type="button"
                                                              class="import-icon-btn import-icon-btn--view-error"
                                                              title=${this.i18n.t('task_tracker.action_view_error')}
                                                              aria-label=${this.i18n.t('task_tracker.action_view_error')}
                                                              @click=${() => this._viewError(row)}
                                                          >
                                                              <platform-icon name="alert-triangle" size="16"></platform-icon>
                                                          </button>`
                                                        : null}
                                                </div>
                                            </td>
                                        </tr>
                                    `;
                                })}
                            </tbody>
                        </table>
                    </div>
                    <div class="task-cards">
                        ${(this._filteredTasks()).map((row) => {
                            const isImport = row.task_type === 'knowledge_import';
                            const isAnalyze = row.task_type === 'note_analyze';
                            const isSummary = row.task_type === 'daily_summary' || row.task_type === 'period_summary';
                            const entN = isImport ? (Array.isArray(row.data?.created_entity_ids) ? row.data.created_entity_ids.length : 0) : (row.data?.result_entities_count ?? 0);
                            const relN = isImport ? (Array.isArray(row.data?.created_relationship_ids) ? row.data.created_relationship_ids.length : 0) : (row.data?.result_relationships_count ?? 0);
                            const canRollback = isImport && ['completed', 'failed', 'cancelled'].includes(row.status) && ((Array.isArray(row.data?.created_entity_ids) ? row.data.created_entity_ids.length : 0) > 0 || (Array.isArray(row.data?.created_relationship_ids) ? row.data.created_relationship_ids.length : 0) > 0);
                            const canDetail = isImport && this._canOpenImportDetail(row);
                            const needsRev = canDetail && this._importNeedsReview(row);
                            const stageLabel = this.i18n.t(`task.stage.${row.stage}`, {}, 'crm') || row.stage;
                            const typeLabel = this.i18n.t(`task.type.${row.task_type}`, {}, 'crm') || row.task_type;
                            const nameLabel = isAnalyze
                                ? (row.data?.note_name || row.data?.note_id || '')
                                : isImport
                                    ? this._importListModeLabel(row.data?.mode)
                                    : isSummary
                                        ? (row.data?.date_str || row.data?.date_from || '')
                                        : '';
                            const isActive = row.status === 'running' || row.status === 'pending';
                            return html`
                                <div class="task-card">
                                    <div class="task-card-header">
                                        <div class="task-card-title">${nameLabel || typeLabel}</div>
                                        <div class="task-card-meta">
                                            <span class="task-type-badge">${typeLabel}</span>
                                            ${this._importJobStatusPill(row.status)}
                                        </div>
                                    </div>
                                    ${isActive ? html`
                                        <div class="task-card-progress">
                                            <div class="task-progress-wrap">
                                                <div class="task-progress-bar" style="width: ${row.progress_pct || 0}%"></div>
                                            </div>
                                            <div class="task-stage-label">${stageLabel}</div>
                                        </div>
                                    ` : ''}
                                    <div class="task-card-stats">
                                        ${entN > 0 || relN > 0 ? html`
                                            <div class="task-card-stat">
                                                <span class="task-card-stat-label">${this.i18n.t('task_tracker.col_entities')}</span>
                                                <span class="task-card-stat-val">${entN}</span>
                                            </div>
                                            <div class="task-card-stat">
                                                <span class="task-card-stat-label">${this.i18n.t('task_tracker.col_rels')}</span>
                                                <span class="task-card-stat-val">${relN}</span>
                                            </div>
                                        ` : ''}
                                        ${needsRev ? html`
                                            <span class="review-badge pending">${this.i18n.t('knowledge_import.review_pending')}</span>
                                        ` : ''}
                                    </div>
                                    <div class="task-card-actions">
                                        ${canDetail ? html`
                                            <button type="button" class="task-card-action-btn"
                                                @click=${() => this._openImportReviewModal(row.task_id)}>
                                                <platform-icon name="doc-detail" size="14"></platform-icon>
                                                ${this.i18n.t('knowledge_import.action_open_detail')}
                                            </button>
                                        ` : ''}
                                        ${isActive ? html`
                                            <button type="button" class="task-card-action-btn task-card-action-btn--stop"
                                                @click=${() => this._cancelRow(row.task_id)}>
                                                <platform-icon name="stop" size="14"></platform-icon>
                                                ${this.i18n.t('knowledge_import.action_cancel')}
                                            </button>
                                        ` : ''}
                                        ${canRollback ? html`
                                            <button type="button" class="task-card-action-btn task-card-action-btn--danger"
                                                @click=${() => this._rollbackRow(row.task_id)}>
                                                <platform-icon name="undo" size="14"></platform-icon>
                                                ${this.i18n.t('knowledge_import.action_rollback')}
                                            </button>
                                        ` : ''}
                                        ${(row.status === 'failed' || row.status === 'cancelled') ? html`
                                            <button type="button" class="task-card-action-btn"
                                                @click=${() => this._retryRow(row.task_id)}>
                                                <platform-icon name="refresh" size="14"></platform-icon>
                                                ${this.i18n.t('task_tracker.action_retry')}
                                            </button>
                                        ` : ''}
                                        ${row.status === 'failed' && row.error_message ? html`
                                            <button type="button" class="task-card-action-btn task-card-action-btn--danger"
                                                @click=${() => this._viewError(row)}>
                                                <platform-icon name="alert-triangle" size="14"></platform-icon>
                                                ${this.i18n.t('task_tracker.action_view_error')}
                                            </button>
                                        ` : ''}
                                    </div>
                                </div>
                            `;
                        })}
                    </div>
                </div>
            </div>

            ${this._wizardOpen ? html`
                <glass-modal
                    .open=${true}
                    size="lg"
                    .heading=${this.i18n.t('knowledge_import.wizard_title')}
                    @modal-closed=${this._closeWizard}
                >
                    <div slot="content" class="wizard-body import-wizard crm-import-glass-content">
                        ${this._wizardStep === 0 ? html`
                            <p>${this.i18n.t('knowledge_import.step0_text')}</p>
                        ` : ''}
                        ${this._wizardStep === 1 ? html`
                            <div class="form-label">${this.i18n.t('knowledge_import.step1_types')}</div>
                            <div class="ki-step1-settings-row">
                                <a
                                    class="ki-step1-settings-link"
                                    href=${this._spacesSettingsUrl()}
                                >${this.i18n.t('knowledge_import.link_namespace_settings')}</a>
                                <platform-help-hint
                                    strategy="local"
                                    label=${this.i18n.t('knowledge_import.hint_types_label')}
                                    .text=${this.i18n.t('knowledge_import.hint_types_body')}
                                ></platform-help-hint>
                            </div>
                            ${types.length === 0
                                ? html`<p>${this.i18n.t('knowledge_import.step1_no_types')}</p>`
                                : html`
                                <div
                                    class="type-card-grid"
                                    role="group"
                                    aria-label=${this.i18n.t('knowledge_import.step1_types')}
                                >
                                    ${types.map((t) => {
                                        const selected = this._selectedTypeIds.includes(t.type_id);
                                        const iconName = this._importWizardIconForType(t);
                                        return html`
                                            <button
                                                type="button"
                                                class="type-card ${selected ? 'selected' : ''}"
                                                aria-pressed=${selected ? 'true' : 'false'}
                                                @click=${() => this._toggleType(t.type_id)}
                                            >
                                                <span class="type-card-check" aria-hidden="true">
                                                    <platform-icon name="check" size="12"></platform-icon>
                                                </span>
                                                <span class="type-card-icon-wrap">
                                                    <platform-icon name=${iconName} size="22"></platform-icon>
                                                </span>
                                                <span class="type-card-title">${t.name}</span>
                                            </button>
                                        `;
                                    })}
                                </div>
                            `}
                        ` : ''}
                        ${this._wizardStep === 2 ? html`
                            <section class="nw-block" aria-labelledby="ki-step2-mode">
                                <h3 class="nw-block-title" id="ki-step2-mode">${this.i18n.t('knowledge_import.step2_mode')}</h3>
                                <div class="nw-switch-row">
                                    <div class="nw-switch-text">
                                        <div class="nw-switch-head">
                                            ${this._mode === 'graph'
                                                ? this.i18n.t('knowledge_import.mode_graph')
                                                : this.i18n.t('knowledge_import.mode_notes')}
                                        </div>
                                        <div class="nw-switch-sub">${this.i18n.t('knowledge_import.mode_switch_hint')}</div>
                                    </div>
                                    <platform-switch
                                        .checked=${this._mode === 'graph'}
                                        @change=${(e) => {
                                            const on = Boolean(e.detail?.value);
                                            this._mode = on ? 'graph' : 'notes_only';
                                        }}
                                    ></platform-switch>
                                </div>
                            </section>
                            <section class="nw-block" aria-labelledby="ki-step2-chunk">
                                <h3 class="nw-block-title" id="ki-step2-chunk">${this.i18n.t('knowledge_import.chunk_heading')}</h3>
                                <div class="nw-switch-row">
                                    <div class="nw-switch-text">
                                        <div class="nw-switch-head">${this.i18n.t('knowledge_import.split_headings')}</div>
                                        <div class="nw-switch-sub">${this.i18n.t('knowledge_import.split_headings_hint')}</div>
                                    </div>
                                    <platform-switch
                                        .checked=${this._splitByHeadings}
                                        @change=${(e) => {
                                            this._splitByHeadings = Boolean(e.detail?.value);
                                        }}
                                    ></platform-switch>
                                </div>
                                <div>
                                    <div class="form-label">${this.i18n.t('knowledge_import.chunk_max')}</div>
                                    <input
                                        type="number"
                                        class="nw-input-number"
                                        min="2000"
                                        max="500000"
                                        step="1000"
                                        .value=${String(this._chunkMaxChars)}
                                        @input=${(e) => {
                                            this._chunkMaxChars = Number(e.target.value) || 50000;
                                        }}
                                    />
                                </div>
                            </section>
                        ` : ''}
                        ${this._wizardStep === 3 ? html`
                            <section class="nw-block" aria-labelledby="ki-step3-text">
                                <h3 class="nw-block-title" id="ki-step3-text">${this.i18n.t('knowledge_import.step3_source')}</h3>
                                <textarea
                                    class="nw-textarea"
                                    .value=${this._pasteText}
                                    @input=${(e) => {
                                        this._pasteText = e.target.value;
                                        this._resolvedSource = null;
                                    }}
                                ></textarea>
                            </section>
                            <section class="nw-block ki-step3-files-block" aria-labelledby="ki-step3-files">
                                <div class="ki-step3-files-heading-row">
                                    <h3 class="nw-block-title ki-step3-files-title" id="ki-step3-files">
                                        ${this.i18n.t('knowledge_import.or_files')}
                                    </h3>
                                    <platform-help-hint
                                        strategy="local"
                                        label=${this.i18n.t('knowledge_import.hint_files_label')}
                                        .text=${this.i18n.t('knowledge_import.hint_formats_body')}
                                    ></platform-help-hint>
                                </div>
                                <div
                                    class="dropzone ${this._dropzoneActive ? 'dropzone--active' : ''}"
                                    role="button"
                                    tabindex="0"
                                    aria-label=${this.i18n.t('knowledge_import.dropzone_aria')}
                                    @click=${(e) => this._openKiFilePicker(e)}
                                    @keydown=${(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            this._openKiFilePicker(e);
                                        }
                                    }}
                                    @dragenter=${this._onDropzoneDragEnter}
                                    @dragover=${this._onDropzoneDragOver}
                                    @dragleave=${this._onDropzoneDragLeave}
                                    @drop=${this._onDropzoneDrop}
                                >
                                    <input
                                        class="dropzone-input ki-import-file-input"
                                        type="file"
                                        multiple
                                        @change=${this._onKiFileInputChange}
                                    />
                                    <div class="dropzone-title">${this.i18n.t('knowledge_import.dropzone_title')}</div>
                                    <p class="dropzone-sub">${this.i18n.t('knowledge_import.dropzone_sub')}</p>
                                </div>
                                ${this._uploadingFiles ? html`<div class="form-label">${this.i18n.t('knowledge_import.uploading')}</div>` : ''}
                                ${this._pendingFiles.length > 0 ? html`
                                    <div class="form-label">${this.i18n.t('knowledge_import.files_attached', { count: String(this._pendingFiles.length) })}</div>
                                    <div class="file-chips" role="list">
                                        ${this._pendingFiles.map((entry, i) => html`
                                            <div class="file-chip" role="listitem">
                                                <platform-icon
                                                    class="file-chip-icon"
                                                    file-icon
                                                    name=${this._fileIconKeyForPending(entry)}
                                                    size="22"
                                                ></platform-icon>
                                                <div class="file-chip-meta">
                                                    <span class="file-chip-name" title=${entry.original_name}>${entry.original_name}</span>
                                                    <span class="file-chip-id" title=${entry.file_id}>${entry.file_id}</span>
                                                </div>
                                                <button
                                                    type="button"
                                                    class="file-chip-remove"
                                                    title=${this.i18n.t('knowledge_import.remove_file')}
                                                    aria-label=${this.i18n.t('knowledge_import.remove_file')}
                                                    @click=${(e) => {
                                                        e.stopPropagation();
                                                        this._removePendingFile(i);
                                                    }}
                                                >
                                                    <platform-icon name="trash" size="18"></platform-icon>
                                                </button>
                                            </div>
                                        `)}
                                    </div>
                                ` : ''}
                                ${this._pendingFiles.length === 1 && !(this._pasteText || '').trim()
                                    ? html`<p class="nw-switch-sub">${this.i18n.t('knowledge_import.file_preview_hint')}</p>`
                                    : ''}
                            </section>
                        ` : ''}
                        ${this._wizardStep === 4 ? html`
                            <p class="ki-step4-intro">${this.i18n.t('knowledge_import.step4_summary')}</p>
                            <div class="ki-step4-grid" role="list">
                                <div class="ki-step4-card" role="listitem">
                                    <div class="ki-step4-card-label">${this.i18n.t('knowledge_import.summary_namespace')}</div>
                                    <div class="ki-step4-card-value">${this._namespaceSummaryLabel()}</div>
                                </div>
                                <div class="ki-step4-card" role="listitem">
                                    <div class="ki-step4-card-label">${this.i18n.t('knowledge_import.summary_mode')}</div>
                                    <div class="ki-step4-card-value">${this._importModeSummaryLabel()}</div>
                                </div>
                                <div class="ki-step4-card ki-step4-card--wide" role="listitem">
                                    <div class="ki-step4-card-label">${this.i18n.t('knowledge_import.summary_types')}</div>
                                    <div class="ki-step4-card-value">${this._summaryTypesHumanLine(types)}</div>
                                </div>
                                ${this._summarySourcesSection()}
                            </div>
                        ` : ''}
                    </div>
                    <div slot="actions" class="wizard-nav crm-import-glass-actions">
                        ${this._wizardStep > 0 ? html`<platform-button variant="secondary" @click=${this._wizardBack}>${this.i18n.t('knowledge_import.back')}</platform-button>` : ''}
                        ${this._wizardStep < 4 ? html`
                            <platform-button
                                variant="primary"
                                ?disabled=${this._wizardStep === 3 && this._uploadingFiles}
                                @click=${() => {
                                    if (this._wizardStep === 3) {
                                        this._onWizardNextFromStep3();
                                        return;
                                    }
                                    this._wizardNext();
                                }}
                            >${this.i18n.t('knowledge_import.next')}</platform-button>
                        ` : html`
                            <platform-button variant="primary" ?disabled=${this._starting} @click=${this._startImport}>
                                ${this.i18n.t('knowledge_import.run')}
                            </platform-button>
                        `}
                    </div>
                </glass-modal>
            ` : ''}

            <file-text-preview-modal
                .open=${this._previewOpen}
                .fileId=${this._singlePendingFileId()}
                .modalHeading=${this.i18n.t('knowledge_import.preview_heading')}
                @file-text-preview-confirm=${this._onPreviewConfirm}
                @file-text-preview-cancel=${this._onPreviewCancel}
            ></file-text-preview-modal>

        `;
    }
}

customElements.define('namespace-tasks-page', NamespaceTasksPage);
