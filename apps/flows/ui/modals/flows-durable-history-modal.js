/**
 * flows-durable-history-modal — durable workflow ledger, branches and time-travel commands.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/editors/flows-code-editor.js';

const NODE_FAILED_EVENT_TYPE = 'NodeFailed';

function isRecord(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function requireRecord(value, context) {
    if (!isRecord(value)) {
        throw new Error(`flows-durable-history-modal: ${context} object required`);
    }
    return value;
}

function optionalResultRecord(value, context) {
    if (value === null || value === undefined) {
        return null;
    }
    return requireRecord(value, context);
}

function optionalRecord(value, context) {
    if (value === null || value === undefined) {
        return {};
    }
    return requireRecord(value, context);
}

function requireString(value, context) {
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`flows-durable-history-modal: ${context} string required`);
    }
    return value;
}

function optionalString(value, context) {
    if (value === null || value === undefined) {
        return '';
    }
    if (typeof value !== 'string') {
        throw new Error(`flows-durable-history-modal: ${context} string required`);
    }
    return value;
}

function requireInteger(value, context) {
    if (!Number.isInteger(value) || value < 0) {
        throw new Error(`flows-durable-history-modal: ${context} non-negative integer required`);
    }
    return value;
}

function optionalHash(value, context) {
    if (value === null || value === undefined) {
        return null;
    }
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`flows-durable-history-modal: ${context} string hash required`);
    }
    return value;
}

function durableEvent(value) {
    const row = requireRecord(value, 'durable event');
    return {
        event_id: requireString(row.event_id, 'event_id'),
        execution_branch_id: requireString(row.execution_branch_id, 'execution_branch_id'),
        sequence: requireInteger(row.sequence, 'sequence'),
        event_type: requireString(row.event_type, 'event_type'),
        created_at: optionalString(row.created_at, 'created_at'),
        prev_state_hash: optionalHash(row.prev_state_hash, 'prev_state_hash'),
        next_state_hash: requireString(row.next_state_hash, 'next_state_hash'),
        payload: optionalRecord(row.payload, 'payload'),
        state_delta: optionalRecord(row.state_delta, 'state_delta'),
    };
}

function durableBranch(value) {
    const row = requireRecord(value, 'durable branch');
    return {
        execution_branch_id: requireString(row.execution_branch_id, 'branch execution_branch_id'),
        base_sequence: requireInteger(row.base_sequence, 'branch base_sequence'),
        reason: optionalString(row.reason, 'branch reason'),
        is_active: row.is_active === true,
    };
}

function durableEventArray(value, context) {
    if (value === undefined || value === null) {
        return [];
    }
    if (!Array.isArray(value)) {
        throw new Error(`flows-durable-history-modal: ${context} array required`);
    }
    return value.map((item) => durableEvent(item));
}

function durableBranchArray(value, context) {
    if (value === undefined || value === null) {
        return [];
    }
    if (!Array.isArray(value)) {
        throw new Error(`flows-durable-history-modal: ${context} array required`);
    }
    return value.map((item) => durableBranch(item));
}

function commandExecutionBranchId(value) {
    const record = optionalResultRecord(value, 'command result');
    if (record === null) {
        return '';
    }
    return optionalString(record.execution_branch_id, 'command execution_branch_id');
}

function formatBranchLabel(branchId) {
    if (branchId.length <= 14) {
        return branchId;
    }
    return `${branchId.slice(0, 8)}...${branchId.slice(-4)}`;
}

function nonEmptyField(source, keys) {
    for (const key of keys) {
        const value = source[key];
        if (typeof value === 'string' && value.length > 0) {
            return value;
        }
        if (Number.isInteger(value)) {
            return String(value);
        }
    }
    return '';
}

export class FlowsDurableHistoryModal extends PlatformModal {
    static modalKind = 'flows.durable_history';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        sessionId: { type: String },
        _selectedBranchId: { type: String, state: true },
        _selectedEventId: { type: String, state: true },
        _selectedTab: { type: String, state: true },
        _stateJson: { type: Object, state: true },
        _stateEditText: { type: String, state: true },
        _lastCommandResult: { type: Object, state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            :host {
                --modal-width: min(1480px, calc(100vw - 24px));
            }
            :host .modal.full .modal-content,
            :host .modal.fullscreen .modal-content {
                display: flex;
                flex-direction: column;
                min-height: 0;
                overflow: hidden;
            }
            .durable-history-body {
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                overflow: hidden;
            }
            .durable-history-loading,
            .durable-history-empty,
            .durable-history-error {
                min-height: 240px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-4);
            }
            .durable-history-error {
                color: var(--error);
                white-space: pre-wrap;
                overflow-wrap: anywhere;
            }
            .durable-toolbar {
                display: grid;
                grid-template-columns: minmax(0, 1fr) auto;
                gap: var(--space-3);
                align-items: start;
                min-width: 0;
            }
            .branch-strip {
                display: flex;
                align-items: center;
                flex-wrap: wrap;
                gap: var(--space-2);
                min-width: 0;
            }
            .branch-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                max-width: 240px;
                min-height: 32px;
                padding: 0 var(--space-2);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                font-family: var(--font-mono);
                font-size: var(--text-xs);
            }
            .branch-chip:hover,
            .branch-chip--selected {
                border-color: var(--accent);
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 11%, var(--glass-solid-subtle));
            }
            .branch-chip__label {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .branch-chip__meta {
                color: var(--text-tertiary);
                font-family: var(--font-sans);
            }
            .branch-chip__active {
                width: 7px;
                height: 7px;
                border-radius: var(--radius-full);
                background: var(--success);
                flex: 0 0 auto;
            }
            .durable-summary {
                display: flex;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-align: right;
                min-width: 0;
            }
            .durable-main {
                flex: 1 1 auto;
                min-height: 0;
                display: grid;
                grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.35fr);
                gap: var(--space-3);
                overflow: hidden;
            }
            .timeline-panel,
            .detail-panel {
                min-width: 0;
                min-height: 0;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                overflow: hidden;
            }
            .timeline-panel {
                display: flex;
                flex-direction: column;
            }
            .timeline-head,
            .detail-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                background: var(--glass-solid-medium);
                min-width: 0;
            }
            .panel-title {
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .panel-meta {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                white-space: nowrap;
            }
            .timeline-list {
                flex: 1 1 auto;
                min-height: 0;
                overflow: auto;
            }
            .event-row {
                width: 100%;
                display: grid;
                grid-template-columns: 58px minmax(0, 1fr);
                gap: var(--space-2);
                padding: 10px var(--space-3);
                border: none;
                border-bottom: 1px solid var(--border-subtle);
                background: transparent;
                color: inherit;
                text-align: left;
                cursor: pointer;
            }
            .event-row:hover,
            .event-row--selected {
                background: var(--glass-tint-subtle);
            }
            .event-row--selected {
                box-shadow: inset 3px 0 0 var(--accent);
            }
            .event-row--failed {
                box-shadow: inset 3px 0 0 var(--error);
            }
            .event-row--selected.event-row--failed {
                box-shadow: inset 3px 0 0 var(--accent);
            }
            .event-seq {
                color: var(--text-tertiary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                line-height: 1.4;
            }
            .event-main {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }
            .event-type {
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                line-height: 1.35;
                overflow-wrap: anywhere;
            }
            .event-subtitle {
                color: var(--text-secondary);
                font-size: var(--text-xs);
                line-height: 1.35;
                overflow-wrap: anywhere;
            }
            .event-created {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.3;
            }
            .detail-panel {
                display: flex;
                flex-direction: column;
            }
            .detail-actions {
                display: inline-flex;
                flex-wrap: wrap;
                justify-content: flex-end;
                gap: var(--space-2);
            }
            .detail-actions platform-button {
                --platform-button-icon-size: 34px;
                --platform-button-icon-radius: var(--radius-full);
            }
            .detail-tabs {
                display: flex;
                gap: var(--space-1);
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                overflow-x: auto;
            }
            .detail-tab {
                min-height: 30px;
                padding: 0 var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                font-size: var(--text-xs);
                white-space: nowrap;
            }
            .detail-tab--selected {
                border-color: var(--accent);
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 10%, transparent);
            }
            .detail-content {
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .state-empty {
                flex: 1 1 auto;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-4);
            }
            flows-code-editor {
                flex: 1 1 auto;
                min-height: 0;
            }
            .mono {
                font-family: var(--font-mono);
            }
            @media (max-width: 920px) {
                .durable-toolbar {
                    grid-template-columns: 1fr;
                }
                .durable-summary {
                    justify-content: flex-start;
                    text-align: left;
                }
                .durable-main {
                    grid-template-columns: 1fr;
                }
            }
            @media (max-width: 620px) {
                .event-row {
                    grid-template-columns: 44px minmax(0, 1fr);
                    padding: 9px var(--space-2);
                }
                .detail-head {
                    flex-direction: column;
                    align-items: stretch;
                }
                .detail-actions {
                    justify-content: flex-start;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this.sessionId = '';
        this._selectedBranchId = '';
        this._selectedEventId = '';
        this._selectedTab = 'payload';
        this._stateJson = null;
        this._stateEditText = '';
        this._lastCommandResult = null;
        this._historyOp = this.useOp('flows/durable_history');
        this._branchesOp = this.useOp('flows/durable_branches');
        this._stateAtOp = this.useOp('flows/durable_state_at');
        this._forkOp = this.useOp('flows/durable_fork');
        this._rewindOp = this.useOp('flows/durable_rewind');
        this._retryOp = this.useOp('flows/durable_retry_from_failure');
        this._manualPatchOp = this.useOp('flows/durable_manual_patch');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('open') && !this.open) {
            return;
        }
        if (this.open && (changed.has('open') || changed.has('sessionId'))) {
            this._selectedBranchId = '';
            this._selectedEventId = '';
            this._selectedTab = 'payload';
            this._stateJson = null;
            this._stateEditText = '';
            this._lastCommandResult = null;
            void this._loadAll();
        }
    }

    _sessionId() {
        return typeof this.sessionId === 'string' ? this.sessionId : '';
    }

    _historyEvents() {
        const result = optionalResultRecord(this._historyOp.lastResult, 'history result');
        return result === null ? [] : durableEventArray(result.events, 'history events');
    }

    _branches() {
        const result = optionalResultRecord(this._branchesOp.lastResult, 'branches result');
        return result === null ? [] : durableBranchArray(result.branches, 'branches');
    }

    _historyTotal(events) {
        const result = optionalResultRecord(this._historyOp.lastResult, 'history result');
        if (result === null || result.total === null || result.total === undefined) {
            return events.length;
        }
        return requireInteger(result.total, 'history total');
    }

    _activeBranchId() {
        const branches = this._branches();
        for (const branch of branches) {
            if (branch.is_active === true) {
                return branch.execution_branch_id;
            }
        }
        return '';
    }

    _selectedBranchOrActive() {
        if (this._selectedBranchId.length > 0) {
            return this._selectedBranchId;
        }
        return this._activeBranchId();
    }

    async _loadAll() {
        const sessionId = this._sessionId();
        if (sessionId.length === 0) {
            return;
        }
        const branchesResult = await this._branchesOp.run({ session_id: sessionId });
        const branches = durableBranchArray(requireRecord(branchesResult, 'branches result').branches, 'branches');
        if (this._selectedBranchId.length === 0) {
            for (const branch of branches) {
                if (branch.is_active === true) {
                    this._selectedBranchId = branch.execution_branch_id;
                    break;
                }
            }
        }
        await this._loadHistory();
    }

    async _loadHistory() {
        const sessionId = this._sessionId();
        if (sessionId.length === 0) {
            return;
        }
        const payload = {
            session_id: sessionId,
            limit: 1000,
            offset: 0,
        };
        const branchId = this._selectedBranchOrActive();
        if (branchId.length > 0) {
            payload.execution_branch_id = branchId;
        }
        await this._historyOp.run(payload);
    }

    _busy() {
        return (
            this._historyOp.busy
            || this._branchesOp.busy
            || this._stateAtOp.busy
            || this._forkOp.busy
            || this._rewindOp.busy
            || this._retryOp.busy
            || this._manualPatchOp.busy
        );
    }

    _commandBusy() {
        return this._forkOp.busy || this._rewindOp.busy || this._retryOp.busy || this._manualPatchOp.busy;
    }

    _selectedEvent() {
        const events = this._historyEvents();
        if (events.length === 0) {
            return null;
        }
        if (this._selectedEventId.length > 0) {
            for (const event of events) {
                if (event.event_id === this._selectedEventId) {
                    return event;
                }
            }
        }
        return events[events.length - 1];
    }

    _selectEvent(event) {
        const row = durableEvent(event);
        this._selectedEventId = row.event_id;
        this._selectedTab = 'payload';
        this._stateJson = null;
        this._stateEditText = '';
    }

    _eventSubtitle(event) {
        return nonEmptyField(event.payload, [
            'node_id',
            'node_type',
            'activity_id',
            'activity_type',
            'child_session_id',
            'handoff_command_id',
            'operator_task_id',
            'source_execution_branch_id',
        ]);
    }

    _formatCreatedAt(event) {
        const raw = event.created_at;
        if (raw.length === 0) {
            return '';
        }
        const date = new Date(raw);
        if (!Number.isFinite(date.getTime())) {
            return raw;
        }
        return new Intl.DateTimeFormat(undefined, {
            dateStyle: 'short',
            timeStyle: 'medium',
        }).format(date);
    }

    _eventClass(event, selectedEventId) {
        const eventType = event.event_type;
        const eventId = event.event_id;
        let cls = 'event-row';
        if (eventId.length > 0 && eventId === selectedEventId) {
            cls += ' event-row--selected';
        }
        if (eventType.endsWith('Failed') || eventType === NODE_FAILED_EVENT_TYPE) {
            cls += ' event-row--failed';
        }
        return cls;
    }

    _isRetryableEvent(event) {
        return event.event_type === NODE_FAILED_EVENT_TYPE;
    }

    async _loadSelectedState() {
        const event = this._selectedEvent();
        if (event === null) {
            return;
        }
        const sequence = event.sequence;
        const executionBranchId = event.execution_branch_id;
        const result = await this._stateAtOp.run({
            session_id: this._sessionId(),
            sequence,
            execution_branch_id: executionBranchId,
        });
        const state = requireRecord(result, 'state projection');
        this._stateJson = state;
        this._stateEditText = JSON.stringify(state, null, 2);
        this._selectedTab = 'state';
    }

    _onStateEdit(e) {
        const detail = e.detail;
        if (!isRecord(detail) || typeof detail.value !== 'string') {
            throw new Error('flows-durable-history-modal: state editor change requires detail.value');
        }
        this._stateEditText = detail.value;
    }

    _anchorFor(event) {
        return {
            session_id: this._sessionId(),
            execution_branch_id: event.execution_branch_id,
            sequence: event.sequence,
            event_id: event.event_id,
            event_type: event.event_type,
        };
    }

    async _copySelectedAnchor() {
        const event = this._selectedEvent();
        if (event === null) {
            return;
        }
        try {
            await navigator.clipboard.writeText(JSON.stringify(this._anchorFor(event), null, 2));
            this.toast('flows:durable_history_modal.toast_anchor_copied', { type: 'success' });
        } catch (err) {
            this.toast('flows:durable_history_modal.toast_copy_failed', {
                type: 'error',
                vars: { detail: err instanceof Error ? err.message : String(err) },
            });
        }
    }

    async _forkSelected() {
        const event = this._selectedEvent();
        if (event === null) {
            return;
        }
        const ok = await platformConfirm(
            this.t('durable_history_modal.confirm_fork_message', {
                sequence: String(event.sequence),
            }),
            {
                title: this.t('durable_history_modal.confirm_fork_title'),
                confirmText: this.t('durable_history_modal.action_fork'),
                cancelText: this.t('durable_history_modal.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        const result = await this._forkOp.run({
            session_id: this._sessionId(),
            sequence: event.sequence,
            execution_branch_id: event.execution_branch_id,
            activate: false,
        });
        this._lastCommandResult = result;
        const branchId = commandExecutionBranchId(result);
        if (branchId.length > 0) {
            this._selectedBranchId = branchId;
        }
        this._selectedTab = 'command';
        await this._loadAll();
        this.toast('flows:durable_history_modal.toast_fork_created', { type: 'success' });
    }

    async _rewindSelected() {
        const event = this._selectedEvent();
        if (event === null) {
            return;
        }
        const ok = await platformConfirm(
            this.t('durable_history_modal.confirm_rewind_message', {
                sequence: String(event.sequence),
            }),
            {
                title: this.t('durable_history_modal.confirm_rewind_title'),
                variant: 'warning',
                confirmVariant: 'danger',
                confirmText: this.t('durable_history_modal.action_rewind'),
                cancelText: this.t('durable_history_modal.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        const result = await this._rewindOp.run({
            session_id: this._sessionId(),
            sequence: event.sequence,
            execution_branch_id: event.execution_branch_id,
        });
        this._lastCommandResult = result;
        const branchId = commandExecutionBranchId(result);
        if (branchId.length > 0) {
            this._selectedBranchId = branchId;
        }
        this._selectedTab = 'command';
        await this._loadAll();
        this.toast('flows:durable_history_modal.toast_rewind_done', { type: 'success' });
    }

    async _retrySelectedFailure() {
        const event = this._selectedEvent();
        if (event === null || !this._isRetryableEvent(event)) {
            return;
        }
        const ok = await platformConfirm(
            this.t('durable_history_modal.confirm_retry_message', {
                sequence: String(event.sequence),
            }),
            {
                title: this.t('durable_history_modal.confirm_retry_title'),
                confirmText: this.t('durable_history_modal.action_retry'),
                cancelText: this.t('durable_history_modal.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        const result = await this._retryOp.run({
            session_id: this._sessionId(),
            failed_sequence: event.sequence,
            execution_branch_id: event.execution_branch_id,
        });
        this._lastCommandResult = result;
        const branchId = commandExecutionBranchId(result);
        if (branchId.length > 0) {
            this._selectedBranchId = branchId;
        }
        this._selectedTab = 'command';
        await this._loadAll();
        this.toast('flows:durable_history_modal.toast_retry_created', { type: 'success' });
    }

    async _manualPatchSelected() {
        const event = this._selectedEvent();
        if (event === null || this._stateJson === null) {
            return;
        }
        let state;
        try {
            state = JSON.parse(this._stateEditText);
        } catch (err) {
            this.toast('flows:durable_history_modal.toast_patch_invalid', {
                type: 'error',
                vars: { detail: err instanceof Error ? err.message : String(err) },
            });
            return;
        }
        if (!isRecord(state)) {
            this.toast('flows:durable_history_modal.toast_patch_invalid', {
                type: 'error',
                vars: { detail: this.t('durable_history_modal.patch_requires_object') },
            });
            return;
        }
        const ok = await platformConfirm(
            this.t('durable_history_modal.confirm_patch_message', {
                sequence: String(event.sequence),
            }),
            {
                title: this.t('durable_history_modal.confirm_patch_title'),
                variant: 'warning',
                confirmText: this.t('durable_history_modal.action_patch'),
                cancelText: this.t('durable_history_modal.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        const result = await this._manualPatchOp.run({
            session_id: this._sessionId(),
            sequence: event.sequence,
            execution_branch_id: event.execution_branch_id,
            state,
            activate: true,
        });
        this._lastCommandResult = result;
        const branchId = commandExecutionBranchId(result);
        if (branchId.length > 0) {
            this._selectedBranchId = branchId;
        }
        this._selectedTab = 'command';
        await this._loadAll();
        this.toast('flows:durable_history_modal.toast_patch_applied', { type: 'success' });
    }

    _setBranch(branch) {
        const branchId = durableBranch(branch).execution_branch_id;
        this._selectedBranchId = branchId;
        this._selectedEventId = '';
        this._selectedTab = 'payload';
        this._stateJson = null;
        this._stateEditText = '';
        void this._loadHistory();
    }

    _renderBranches() {
        const branches = this._branches();
        const selectedBranchId = this._selectedBranchOrActive();
        if (branches.length === 0) {
            return nothing;
        }
        return html`
            <div class="branch-strip">
                ${branches.map((branch) => {
                    const selected = branch.execution_branch_id === selectedBranchId;
                    return html`
                        <button
                            type="button"
                            class=${selected ? 'branch-chip branch-chip--selected' : 'branch-chip'}
                            title=${branch.execution_branch_id}
                            @click=${() => this._setBranch(branch)}
                        >
                            ${branch.is_active === true ? html`<span class="branch-chip__active"></span>` : nothing}
                            <span class="branch-chip__label">${formatBranchLabel(branch.execution_branch_id)}</span>
                            <span class="branch-chip__meta">${branch.reason} @${branch.base_sequence}</span>
                        </button>
                    `;
                })}
            </div>
        `;
    }

    _renderTimeline() {
        const events = this._historyEvents();
        const selected = this._selectedEvent();
        const selectedEventId = selected === null ? '' : selected.event_id;
        if (events.length === 0) {
            return html`<div class="durable-history-empty">${this.t('durable_history_modal.empty')}</div>`;
        }
        return html`
            <div class="timeline-list">
                ${events.map((event) => {
                    const subtitle = this._eventSubtitle(event);
                    return html`
                        <button
                            type="button"
                            class=${this._eventClass(event, selectedEventId)}
                            @click=${() => this._selectEvent(event)}
                        >
                            <div class="event-seq">#${event.sequence}</div>
                            <div class="event-main">
                                <div class="event-type">${event.event_type}</div>
                                ${subtitle.length > 0 ? html`<div class="event-subtitle">${subtitle}</div>` : nothing}
                                <div class="event-created">${this._formatCreatedAt(event)}</div>
                            </div>
                        </button>
                    `;
                })}
            </div>
        `;
    }

    _detailJsonValue() {
        const event = this._selectedEvent();
        if (this._selectedTab === 'state') {
            return this._stateJson;
        }
        if (this._selectedTab === 'command') {
            return this._lastCommandResult;
        }
        if (event === null) {
            return null;
        }
        if (this._selectedTab === 'delta') {
            return event.state_delta;
        }
        return {
            event_id: event.event_id,
            session_id: this._sessionId(),
            execution_branch_id: event.execution_branch_id,
            sequence: event.sequence,
            event_type: event.event_type,
            created_at: event.created_at,
            prev_state_hash: event.prev_state_hash,
            next_state_hash: event.next_state_hash,
            payload: event.payload,
        };
    }

    _renderTabButton(tab, labelKey) {
        return html`
            <button
                type="button"
                class=${this._selectedTab === tab ? 'detail-tab detail-tab--selected' : 'detail-tab'}
                @click=${() => { this._selectedTab = tab; }}
            >
                ${this.t(labelKey)}
            </button>
        `;
    }

    _renderDetailContent() {
        if (this._selectedTab === 'state' && this._stateJson === null) {
            if (this._stateAtOp.busy) {
                return html`<div class="state-empty"><glass-spinner></glass-spinner></div>`;
            }
            return html`
                <div class="state-empty">
                    <platform-button
                        variant="primary"
                        @click=${() => this._loadSelectedState()}
                    >
                        ${this.t('durable_history_modal.action_load_state')}
                    </platform-button>
                </div>
            `;
        }
        if (this._selectedTab === 'state') {
            return html`
                <flows-code-editor
                    language="json"
                    fill-parent
                    .showToolbar=${false}
                    .readonly=${false}
                    .value=${this._stateEditText}
                    @change=${this._onStateEdit}
                ></flows-code-editor>
            `;
        }
        const value = this._detailJsonValue();
        const json = value === null ? '' : JSON.stringify(value, null, 2);
        return html`
            <flows-code-editor
                language="json"
                readonly
                fill-parent
                .showToolbar=${false}
                .value=${json}
            ></flows-code-editor>
        `;
    }

    _renderDetail() {
        const event = this._selectedEvent();
        if (event === null) {
            return html`<div class="durable-history-empty">${this.t('durable_history_modal.empty')}</div>`;
        }
        const canRetry = this._isRetryableEvent(event);
        const commandBusy = this._commandBusy();
        const canPatch = this._stateJson !== null;
        return html`
            <section class="detail-panel">
                <div class="detail-head">
                    <div class="panel-title">
                        ${event.event_type}
                        <span class="mono">#${event.sequence}</span>
                    </div>
                    <div class="detail-actions">
                        <platform-button
                            icon-only
                            variant="secondary"
                            title=${this.t('durable_history_modal.action_state')}
                            aria-label=${this.t('durable_history_modal.action_state')}
                            ?disabled=${this._stateAtOp.busy}
                            @click=${() => this._loadSelectedState()}
                        >
                            <platform-icon name="trace-json" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            icon-only
                            variant="secondary"
                            title=${this.t('durable_history_modal.action_patch')}
                            aria-label=${this.t('durable_history_modal.action_patch')}
                            ?disabled=${!canPatch || commandBusy}
                            @click=${() => this._manualPatchSelected()}
                        >
                            <platform-icon name="save" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            icon-only
                            variant="secondary"
                            title=${this.t('durable_history_modal.action_copy_anchor')}
                            aria-label=${this.t('durable_history_modal.action_copy_anchor')}
                            @click=${() => this._copySelectedAnchor()}
                        >
                            <platform-icon name="copy" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            icon-only
                            variant="secondary"
                            title=${this.t('durable_history_modal.action_fork')}
                            aria-label=${this.t('durable_history_modal.action_fork')}
                            ?disabled=${commandBusy}
                            @click=${() => this._forkSelected()}
                        >
                            <platform-icon name="git-branch" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            icon-only
                            variant="danger"
                            title=${this.t('durable_history_modal.action_rewind')}
                            aria-label=${this.t('durable_history_modal.action_rewind')}
                            ?disabled=${commandBusy}
                            @click=${() => this._rewindSelected()}
                        >
                            <platform-icon name="rotate-ccw" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            icon-only
                            variant="primary"
                            title=${this.t('durable_history_modal.action_retry')}
                            aria-label=${this.t('durable_history_modal.action_retry')}
                            ?disabled=${!canRetry || commandBusy}
                            @click=${() => this._retrySelectedFailure()}
                        >
                            <platform-icon name="play" size="16"></platform-icon>
                        </platform-button>
                    </div>
                </div>
                <div class="detail-tabs">
                    ${this._renderTabButton('payload', 'durable_history_modal.tab_payload')}
                    ${this._renderTabButton('delta', 'durable_history_modal.tab_delta')}
                    ${this._renderTabButton('state', 'durable_history_modal.tab_state')}
                    ${this._renderTabButton('command', 'durable_history_modal.tab_command')}
                </div>
                <div class="detail-content">${this._renderDetailContent()}</div>
            </section>
        `;
    }

    renderHeader() {
        const sessionId = this._sessionId();
        return sessionId.length > 0
            ? this.t('durable_history_modal.title_with_session', { sessionId })
            : this.t('durable_history_modal.title');
    }

    renderHeaderActions() {
        return html`
            <button
                type="button"
                class="header-btn"
                title=${this.t('durable_history_modal.action_refresh')}
                aria-label=${this.t('durable_history_modal.action_refresh')}
                ?disabled=${this._busy()}
                @click=${() => this._loadAll()}
            >
                ${this._busy()
                    ? html`<glass-spinner></glass-spinner>`
                    : html`<platform-icon name="refresh" size="16"></platform-icon>`}
            </button>
        `;
    }

    renderBody() {
        const sessionId = this._sessionId();
        if (sessionId.length === 0) {
            return html`<div class="durable-history-empty">${this.t('durable_history_modal.session_required')}</div>`;
        }
        const error = this._historyOp.error || this._branchesOp.error || this._stateAtOp.error || this._forkOp.error || this._rewindOp.error || this._retryOp.error || this._manualPatchOp.error;
        if (error) {
            return html`<div class="durable-history-error">${String(error)}</div>`;
        }
        const events = this._historyEvents();
        if (this._historyOp.busy && events.length === 0) {
            return html`<div class="durable-history-loading"><glass-spinner></glass-spinner></div>`;
        }
        const totalLabel = String(this._historyTotal(events));
        return html`
            <div class="durable-history-body">
                <div class="durable-toolbar">
                    ${this._renderBranches()}
                    <div class="durable-summary">
                        <span>${this.t('durable_history_modal.summary_events', { count: totalLabel })}</span>
                        <span class="mono">${this._selectedBranchOrActive()}</span>
                    </div>
                </div>
                <div class="durable-main">
                    <section class="timeline-panel">
                        <div class="timeline-head">
                            <div class="panel-title">${this.t('durable_history_modal.timeline_title')}</div>
                            <div class="panel-meta">${events.length}</div>
                        </div>
                        ${this._renderTimeline()}
                    </section>
                    ${this._renderDetail()}
                </div>
            </div>
        `;
    }
}

customElements.define('flows-durable-history-modal', FlowsDurableHistoryModal);
registerModalKind(FlowsDurableHistoryModal.modalKind, 'flows-durable-history-modal');
