/**
 * flows-durable-history-modal — журнал durable workflow, lineage веток и time-travel.
 */

import type { OpController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-work-item-badge.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import '../components/editors/flows-code-editor.js';
import { formatJsonPretty } from '@platform/lib/utils/json-format.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import {
    durableBranchReasonKey,
    durableEventPhase,
    durableEventSubtitleFromPayload,
    durableEventTitleKey,
    formatDurableBranchLabel,
    isDurableFailedEventType,
    isDurableTerminalEventType,
} from '../_helpers/flows-durable-event-copy.js';

const NODE_FAILED_EVENT_TYPE = 'NodeFailed';

function isRecord(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function requireRecord(value: unknown, context: string) {
    if (!isRecord(value)) {
        throw new Error(`flows-durable-history-modal: ${context} object required`);
    }
    return value;
}

function optionalResultRecord(value: unknown, context: string) {
    if (value === null || value === undefined) {
        return null;
    }
    return requireRecord(value, context);
}

function optionalRecord(value: unknown, context: string) {
    if (value === null || value === undefined) {
        return {};
    }
    return requireRecord(value, context);
}

function requireString(value: unknown, context: string) {
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`flows-durable-history-modal: ${context} string required`);
    }
    return value;
}

function optionalString(value: unknown, context: string) {
    if (value === null || value === undefined) {
        return '';
    }
    if (typeof value !== 'string') {
        throw new Error(`flows-durable-history-modal: ${context} string required`);
    }
    return value;
}

function requireInteger(value: unknown, context: string) {
    if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
        throw new Error(`flows-durable-history-modal: ${context} non-negative integer required`);
    }
    return value;
}

function optionalHash(value: unknown, context: string) {
    if (value === null || value === undefined) {
        return null;
    }
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`flows-durable-history-modal: ${context} string hash required`);
    }
    return value;
}

function optionalParentBranchId(value: unknown) {
    if (value === null || value === undefined) {
        return null;
    }
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error('flows-durable-history-modal: parent_execution_branch_id string or null required');
    }
    return value;
}

function durableEvent(value: unknown) {
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

function durableBranch(value: unknown) {
    const row = requireRecord(value, 'durable branch');
    return {
        execution_branch_id: requireString(row.execution_branch_id, 'branch execution_branch_id'),
        parent_execution_branch_id: optionalParentBranchId(row.parent_execution_branch_id),
        base_sequence: requireInteger(row.base_sequence, 'branch base_sequence'),
        reason: optionalString(row.reason, 'branch reason'),
        is_active: row.is_active === true,
    };
}

function durableEventArray(value: unknown, context: string) {
    if (value === undefined || value === null) {
        return [];
    }
    if (!Array.isArray(value)) {
        throw new Error(`flows-durable-history-modal: ${context} array required`);
    }
    return value.map((item) => durableEvent(item));
}

function durableBranchArray(value: unknown, context: string) {
    if (value === undefined || value === null) {
        return [];
    }
    if (!Array.isArray(value)) {
        throw new Error(`flows-durable-history-modal: ${context} array required`);
    }
    return value.map((item) => durableBranch(item));
}

type DurableEventRow = ReturnType<typeof durableEvent>;
type DurableBranchRow = ReturnType<typeof durableBranch>;

function commandExecutionBranchId(value: unknown) {
    const record = optionalResultRecord(value, 'command result');
    if (record === null) {
        return '';
    }
    return optionalString(record.execution_branch_id, 'command execution_branch_id');
}

function commandEffect(value: unknown) {
    const record = optionalResultRecord(value, 'command result');
    if (record === null) {
        return null;
    }
    const effect = record.effect;
    if (effect === null || effect === undefined) {
        return null;
    }
    const row = requireRecord(effect, 'command effect');
    return {
        activates_head: row.activates_head === true,
        source_execution_branch_id: requireString(
            row.source_execution_branch_id,
            'effect source_execution_branch_id',
        ),
        source_sequence: requireInteger(row.source_sequence, 'effect source_sequence'),
        source_events_after_base: requireInteger(
            row.source_events_after_base,
            'effect source_events_after_base',
        ),
        instance_status: optionalString(row.instance_status, 'effect instance_status'),
        auto_resumes_run: row.auto_resumes_run === true,
    };
}

/**
 * Order branches as a forest walk: roots first, then children by created order in list.
 * @param {ReturnType<typeof durableBranch>[]} branches
 */
function orderBranchesLineage(branches: DurableBranchRow[]) {
    const byId = new Map();
    for (const branch of branches) {
        byId.set(branch.execution_branch_id, branch);
    }
    const children = new Map<string, DurableBranchRow[]>();
    const roots: DurableBranchRow[] = [];
    for (const branch of branches) {
        const parentId = branch.parent_execution_branch_id;
        if (parentId === null || !byId.has(parentId)) {
            roots.push(branch);
            continue;
        }
        const list = children.get(parentId);
        if (list === undefined) {
            children.set(parentId, [branch]);
        } else {
            list.push(branch);
        }
    }
    const ordered: { branch: DurableBranchRow; depth: number }[] = [];
    const visit = (branch: DurableBranchRow, depth: number) => {
        ordered.push({ branch, depth });
        const kids = children.get(branch.execution_branch_id);
        if (kids === undefined) {
            return;
        }
        for (const child of kids) {
            visit(child, depth + 1);
        }
    };
    for (const root of roots) {
        visit(root, 0);
    }
    for (const branch of branches) {
        if (!ordered.some((row) => row.branch.execution_branch_id === branch.execution_branch_id)) {
            ordered.push({ branch, depth: 0 });
        }
    }
    return ordered;
}

export class FlowsDurableHistoryModal extends PlatformModal {
    static modalKind = 'flows.durable_history';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        sessionId: { type: String },
        _selectedBranchId: { type: String, state: true },
        _selectedEventId: { type: String, state: true },
        _selectedTab: { type: String, state: true },
        _stateJson: { type: Object, state: true },
        _stateEditText: { type: String, state: true },
        _lastCommandResult: { type: Object, state: true },
        _showOutcome: { type: Boolean, state: true },
    }
    declare sessionId: string;
    declare _selectedBranchId: string;
    declare _selectedEventId: string;
    declare _selectedTab: string;
    declare _stateJson: Record<string, unknown> | null;
    declare _stateEditText: string;
    declare _lastCommandResult: Record<string, unknown> | null;
    declare _showOutcome: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        css`
            :host {
                --modal-width: min(1480px, calc(100vw - 24px));
                --durable-json-min-height: min(560px, 55vh);
                --durable-main-min-height: min(720px, 70vh);
            }
            :host .modal.full .modal-content,
            :host .modal.fullscreen .modal-content {
                display: block;
                min-height: 0;
                overflow-x: hidden;
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
            }
            .durable-history-body {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-height: 0;
                overflow: visible;
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
            .lineage-panel {
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
            }
            .lineage-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .lineage-list {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                min-width: 0;
            }
            article.branch-chip,
            article.event-row {
                margin: 0;
                font: inherit;
                box-sizing: border-box;
            }
            .branch-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                max-width: 280px;
                min-height: 34px;
                padding: 0 var(--space-2);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                cursor: pointer;
                font-size: var(--text-xs);
            }
            .branch-chip:hover,
            .branch-chip--selected {
                border-color: var(--accent);
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent) 11%, var(--glass-solid-subtle));
            }
            .branch-chip__indent {
                color: var(--text-tertiary);
                font-family: var(--font-mono);
                letter-spacing: -0.04em;
            }
            .branch-chip__label {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-family: var(--font-mono);
            }
            .branch-chip__meta {
                color: var(--text-tertiary);
                font-family: var(--font-sans);
                white-space: nowrap;
            }
            .branch-chip__active {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 0 6px;
                min-height: 18px;
                border-radius: var(--radius-full);
                background: color-mix(in srgb, var(--success) 22%, transparent);
                color: var(--success);
                font-size: 10px;
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .branch-chip__active-dot {
                width: 6px;
                height: 6px;
                border-radius: var(--radius-full);
                background: var(--success);
            }
            .durable-summary {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                white-space: nowrap;
            }
            .durable-main {
                display: grid;
                grid-template-columns: minmax(300px, 0.85fr) minmax(0, 1.4fr);
                gap: var(--space-3);
                align-items: start;
                min-height: var(--durable-main-min-height);
                overflow: visible;
            }
            .timeline-panel,
            .detail-panel {
                min-width: 0;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                overflow: visible;
                display: flex;
                flex-direction: column;
            }
            .timeline-panel {
                position: sticky;
                top: 0;
                max-height: calc(100vh - 120px);
                overflow: hidden;
            }
            .detail-panel {
                min-height: var(--durable-main-min-height);
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
                grid-template-columns: 52px minmax(0, 1fr);
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
            .event-title-row {
                display: flex;
                align-items: baseline;
                gap: var(--space-2);
                min-width: 0;
                flex-wrap: wrap;
            }
            .event-title {
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                line-height: 1.35;
            }
            .event-type-tech {
                color: var(--text-tertiary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
            }
            .event-phase {
                display: inline-flex;
                align-items: center;
                min-height: 18px;
                padding: 0 6px;
                border-radius: var(--radius-sm);
                background: var(--glass-tint-subtle);
                color: var(--text-secondary);
                font-size: 10px;
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.03em;
            }
            .event-phase--fail {
                color: var(--error);
                background: color-mix(in srgb, var(--error) 14%, transparent);
            }
            .event-phase--terminal {
                color: var(--success);
                background: color-mix(in srgb, var(--success) 14%, transparent);
            }
            .event-phase--branch {
                color: var(--accent);
                background: color-mix(in srgb, var(--accent) 14%, transparent);
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
            .inspector-scroll {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                overflow: visible;
            }
            .info-card {
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .info-card--warning {
                border-color: color-mix(in srgb, var(--warning) 45%, var(--border-subtle));
                background: color-mix(in srgb, var(--warning) 8%, var(--glass-solid-medium));
            }
            .info-card--success {
                border-color: color-mix(in srgb, var(--success) 40%, var(--border-subtle));
            }
            .info-card__title {
                color: var(--text-primary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .info-card__body {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.45;
                white-space: pre-wrap;
            }
            .info-card__list {
                margin: 0;
                padding-left: 1.1em;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.5;
            }
            .action-rail {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .action-rail__row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: stretch;
            }
            .action-rail platform-button {
                flex: 0 1 auto;
            }
            .action-hint {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.35;
            }
            .advanced-block {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-height: var(--durable-json-min-height);
                flex: 1 1 auto;
            }
            .advanced-block__title {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .detail-content {
                flex: 1 1 auto;
                min-height: var(--durable-json-min-height);
                height: var(--durable-json-min-height);
                display: flex;
                flex-direction: column;
                overflow: hidden;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
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
                .durable-main {
                    grid-template-columns: 1fr;
                    min-height: 0;
                }
                .timeline-panel {
                    position: static;
                    max-height: min(420px, 45vh);
                }
                .detail-panel {
                    min-height: 0;
                }
            }
            @media (max-width: 620px) {
                .event-row {
                    grid-template-columns: 44px minmax(0, 1fr);
                    padding: 9px var(--space-2);
                }
            }
        `,
    ];
    private _historyOp: OpController;
    private _branchesOp: OpController;
    private _stateAtOp: OpController;
    private _forkOp: OpController;
    private _rewindOp: OpController;
    private _retryOp: OpController;
    private _manualPatchOp: OpController;

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
        this._showOutcome = false;
        this._historyOp = this.useOp('flows/durable_history');
        this._branchesOp = this.useOp('flows/durable_branches');
        this._stateAtOp = this.useOp('flows/durable_state_at');
        this._forkOp = this.useOp('flows/durable_fork');
        this._rewindOp = this.useOp('flows/durable_rewind');
        this._retryOp = this.useOp('flows/durable_retry_from_failure');
        this._manualPatchOp = this.useOp('flows/durable_manual_patch');
    }

    override updated(changed: PropertyValues<this>): void {
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
            this._showOutcome = false;
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

    _historyTotal(events: readonly DurableEventRow[]) {
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

    _eventsAfterSelected() {
        const event = this._selectedEvent();
        if (event === null) {
            return 0;
        }
        let count = 0;
        for (const row of this._historyEvents()) {
            if (row.sequence > event.sequence) {
                count += 1;
            }
        }
        return count;
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
        const payload: Record<string, unknown> = {
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
        const lastEvent = events[events.length - 1];
        return lastEvent === undefined ? null : lastEvent;
    }

    _onSelectableKeydown(event: KeyboardEvent, handler: () => void) {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        event.preventDefault();
        handler.call(this);
    }

    _selectEvent(event: DurableEventRow) {
        const row = durableEvent(event);
        this._selectedEventId = row.event_id;
        this._selectedTab = 'payload';
        this._stateJson = null;
        this._stateEditText = '';
        this._showOutcome = false;
    }

    _setBranch(branch: unknown) {
        const row = durableBranch(branch);
        this._selectedBranchId = row.execution_branch_id;
        this._selectedEventId = '';
        this._selectedTab = 'payload';
        this._stateJson = null;
        this._stateEditText = '';
        this._showOutcome = false;
        void this._loadHistory();
    }

    _eventWorkItemId(event: DurableEventRow) {
        const payload = event.payload;
        if (!isRecord(payload)) {
            return '';
        }
        const workItemId = payload.work_item_id;
        return typeof workItemId === 'string' ? workItemId : '';
    }

    _eventSubtitle(event: DurableEventRow) {
        return durableEventSubtitleFromPayload(event.payload);
    }

    _formatCreatedAt(event: DurableEventRow) {
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

    _eventClass(event: DurableEventRow, selectedEventId: string) {
        let cls = 'event-row';
        if (event.event_id.length > 0 && event.event_id === selectedEventId) {
            cls += ' event-row--selected';
        }
        if (isDurableFailedEventType(event.event_type)) {
            cls += ' event-row--failed';
        }
        return cls;
    }

    _phaseClass(phase: string) {
        let cls = 'event-phase';
        if (phase === 'fail') {
            cls += ' event-phase--fail';
        } else if (phase === 'terminal') {
            cls += ' event-phase--terminal';
        } else if (phase === 'branch') {
            cls += ' event-phase--branch';
        }
        return cls;
    }

    _isRetryableEvent(event: DurableEventRow) {
        return event.event_type === NODE_FAILED_EVENT_TYPE;
    }

    _isLastEvent(event: DurableEventRow) {
        const events = this._historyEvents();
        if (events.length === 0) {
            return false;
        }
        return events[events.length - 1]?.event_id === event.event_id;
    }

    async _loadSelectedState() {
        const event = this._selectedEvent();
        if (event === null) {
            return;
        }
        const result = await this._stateAtOp.run({
            session_id: this._sessionId(),
            sequence: event.sequence,
            execution_branch_id: event.execution_branch_id,
        });
        const state = requireRecord(result, 'state projection');
        this._stateJson = state;
        this._stateEditText = formatJsonPretty(state);
        this._selectedTab = 'state';
        this._showOutcome = false;
    }

    _onStateEdit(e: CustomEvent) {
        const detail = e.detail;
        if (!isRecord(detail) || typeof detail.value !== 'string') {
            throw new Error('flows-durable-history-modal: state editor change requires detail.value');
        }
        this._stateEditText = detail.value;
    }

    _anchorFor(event: DurableEventRow) {
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
            await navigator.clipboard.writeText(formatJsonPretty(this._anchorFor(event)));
            this.toast('flows:durable_history_modal.toast_anchor_copied', { type: 'success' });
        } catch (err) {
            this.toast('flows:durable_history_modal.toast_copy_failed', {
                type: 'error',
                vars: { detail: err instanceof Error ? err.message : String(err) },
            });
        }
    }

    async _applyCommandResult(result: unknown, toastKey: string) {
        if (result !== null && !isRecord(result)) {
            throw new Error('flows-durable-history-modal: command result object required');
        }
        this._lastCommandResult = result;
        this._showOutcome = true;
        this._selectedTab = 'command';
        const branchId = commandExecutionBranchId(result);
        if (branchId.length > 0) {
            this._selectedBranchId = branchId;
        }
        await this._loadAll();
        this.toast(toastKey, { type: 'success' });
    }

    async _forkSelected() {
        const event = this._selectedEvent();
        if (event === null) {
            return;
        }
        const eventsAfter = this._eventsAfterSelected();
        const ok = await platformConfirm(
            this.t('durable_history_modal.confirm_fork_message', {
                sequence: String(event.sequence),
                eventsAfter: String(eventsAfter),
            }),
            {
                title: this.t('durable_history_modal.confirm_fork_title'),
                confirmText: this.t('durable_history_modal.action_fork'),
                cancelText: this.t('common.action_cancel'),
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
        await this._applyCommandResult(result, 'flows:durable_history_modal.toast_fork_created');
    }

    async _rewindSelected() {
        const event = this._selectedEvent();
        if (event === null) {
            return;
        }
        const eventsAfter = this._eventsAfterSelected();
        const terminalWarning = isDurableTerminalEventType(event.event_type) && this._isLastEvent(event)
            ? this.t('durable_history_modal.confirm_rewind_terminal_warning')
            : '';
        const ok = await platformConfirm(
            this.t('durable_history_modal.confirm_rewind_message', {
                sequence: String(event.sequence),
                sequencePlus: String(event.sequence + 1),
                eventsAfter: String(eventsAfter),
                terminalWarning,
            }),
            {
                title: this.t('durable_history_modal.confirm_rewind_title'),
                variant: 'warning',
                confirmVariant: 'danger',
                confirmText: this.t('durable_history_modal.action_rewind'),
                cancelText: this.t('common.action_cancel'),
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
        await this._applyCommandResult(result, 'flows:durable_history_modal.toast_rewind_done');
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
                cancelText: this.t('common.action_cancel'),
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
        await this._applyCommandResult(result, 'flows:durable_history_modal.toast_retry_created');
    }

    async _manualPatchSelected() {
        const event = this._selectedEvent();
        if (event === null || this._stateJson === null) {
            return;
        }
        let parsed;
        try {
            parsed = JSON.parse(this._stateEditText);
        } catch (err) {
            this.toast('flows:durable_history_modal.toast_patch_invalid', {
                type: 'error',
                vars: { detail: err instanceof Error ? err.message : String(err) },
            });
            return;
        }
        if (!isRecord(parsed)) {
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
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        const result = await this._manualPatchOp.run({
            session_id: this._sessionId(),
            sequence: event.sequence,
            execution_branch_id: event.execution_branch_id,
            state: parsed,
            activate: true,
        });
        await this._applyCommandResult(result, 'flows:durable_history_modal.toast_patch_applied');
    }

    _detailTabItems() {
        return [
            { value: 'payload', label: this.t('durable_history_modal.tab_payload') },
            { value: 'delta', label: this.t('durable_history_modal.tab_delta') },
            { value: 'state', label: this.t('durable_history_modal.tab_state') },
            { value: 'hashes', label: this.t('durable_history_modal.tab_hashes') },
            { value: 'command', label: this.t('durable_history_modal.tab_command') },
        ];
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
        if (this._selectedTab === 'hashes') {
            return {
                prev_state_hash: event.prev_state_hash,
                next_state_hash: event.next_state_hash,
                execution_branch_id: event.execution_branch_id,
                sequence: event.sequence,
            };
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

    _renderLineage() {
        const branches = this._branches();
        const selectedBranchId = this._selectedBranchOrActive();
        if (branches.length === 0) {
            return '';
        }
        const ordered = orderBranchesLineage(branches);
        return html`
            <section class="lineage-panel" aria-label=${this.t('durable_history_modal.lineage_title')}>
                <div class="lineage-head">
                    <div class="panel-title">${this.t('durable_history_modal.lineage_title')}</div>
                    <div class="durable-summary">
                        ${this.t('durable_history_modal.summary_events', {
                            count: String(this._historyTotal(this._historyEvents())),
                        })}
                    </div>
                </div>
                <div class="lineage-list">
                    ${ordered.map(({ branch, depth }) => {
                        const selected = branch.execution_branch_id === selectedBranchId;
                        const reasonKey = durableBranchReasonKey(branch.reason);
                        const indent = depth > 0 ? `${'·'.repeat(Math.min(depth, 4))} ` : '';
                        return html`
                            <article
                                tabindex="0"
                                role="button"
                                class=${selected ? 'branch-chip branch-chip--selected' : 'branch-chip'}
                                title=${branch.execution_branch_id}
                                @click=${() => this._setBranch(branch)}
                                @keydown=${(event: KeyboardEvent) => this._onSelectableKeydown(event, () => this._setBranch(branch))}
                            >
                                ${branch.is_active === true
                                    ? html`<span class="branch-chip__active">
                                        <span class="branch-chip__active-dot"></span>
                                        ${this.t('durable_history_modal.active_badge')}
                                    </span>`
                                    : nothing}
                                ${indent.length > 0
                                    ? html`<span class="branch-chip__indent">${indent}</span>`
                                    : nothing}
                                <span class="branch-chip__label">${formatDurableBranchLabel(branch.execution_branch_id)}</span>
                                <span class="branch-chip__meta"
                                    >${this.t(reasonKey)} @${branch.base_sequence}</span
                                >
                            </article>
                        `;
                    })}
                </div>
            </section>
        `;
    }

    _renderTimeline() {
        const events = this._historyEvents();
        const selected = this._selectedEvent();
        const selectedEventId = selected === null ? '' : selected.event_id;
        if (events.length === 0) {
            return html`<platform-empty-state icon="scroll-text" title=${this.t('durable_history_modal.empty')}></platform-empty-state>`;
        }
        return html`
            <div class="timeline-list">
                ${events.map((event) => {
                    const subtitle = this._eventSubtitle(event);
                    const workItemId = this._eventWorkItemId(event);
                    const phase = durableEventPhase(event.event_type);
                    const titleKey = durableEventTitleKey(event.event_type);
                    return html`
                        <article
                            tabindex="0"
                            role="button"
                            class=${this._eventClass(event, selectedEventId)}
                            @click=${() => this._selectEvent(event)}
                            @keydown=${(eventKey: KeyboardEvent) => this._onSelectableKeydown(eventKey, () => this._selectEvent(event))}
                        >
                            <div class="event-seq">#${event.sequence}</div>
                            <div class="event-main">
                                <div class="event-title-row">
                                    <span class=${this._phaseClass(phase)}
                                        >${this.t(`durable_history_modal.phase_${phase}`)}</span
                                    >
                                    <span class="event-title">${this.t(titleKey)}</span>
                                    <span class="event-type-tech">${event.event_type}</span>
                                </div>
                                ${workItemId.length > 0
                                    ? html`<platform-work-item-badge
                                        work-item-id=${workItemId}
                                        variant="chip"
                                        size="sm"
                                        interactive
                                        ?show-preview=${false}
                                    ></platform-work-item-badge>`
                                    : (subtitle.length > 0
                                        ? html`<div class="event-subtitle">${subtitle}</div>`
                                        : nothing)}
                                <div class="event-created">${this._formatCreatedAt(event)}</div>
                            </div>
                        </article>
                    `;
                })}
            </div>
        `;
    }

    _renderSummaryCard(event: DurableEventRow) {
        const titleKey = durableEventTitleKey(event.event_type);
        const subtitle = this._eventSubtitle(event);
        return html`
            <section class="info-card">
                <div class="info-card__title">${this.t('durable_history_modal.summary_heading')}</div>
                <div class="info-card__body">
                    <strong>${this.t(titleKey)}</strong>
                    <span class="mono"> #${event.sequence}</span>
                    · <span class="mono">${event.event_type}</span>
                    ${subtitle.length > 0 ? html`<div>${subtitle}</div>` : nothing}
                </div>
            </section>
        `;
    }

    _renderConsequencesCard(event: DurableEventRow) {
        const eventsAfter = this._eventsAfterSelected();
        const terminalPoint = isDurableTerminalEventType(event.event_type) && this._isLastEvent(event);
        return html`
            <section class=${terminalPoint ? 'info-card info-card--warning' : 'info-card'}>
                <div class="info-card__title">${this.t('durable_history_modal.consequences_heading')}</div>
                <ul class="info-card__list">
                    <li>
                        ${this.t('durable_history_modal.consequence_fork', {
                            sequence: String(event.sequence),
                        })}
                    </li>
                    <li>
                        ${this.t('durable_history_modal.consequence_rewind', {
                            sequence: String(event.sequence),
                            eventsAfter: String(eventsAfter),
                        })}
                    </li>
                    ${this._isRetryableEvent(event)
                        ? html`<li>${this.t('durable_history_modal.consequence_retry')}</li>`
                        : nothing}
                    ${terminalPoint
                        ? html`<li>${this.t('durable_history_modal.consequence_terminal_point')}</li>`
                        : nothing}
                </ul>
            </section>
        `;
    }

    _renderOutcomeCard() {
        if (!this._showOutcome || this._lastCommandResult === null) {
            return '';
        }
        const effect = commandEffect(this._lastCommandResult);
        const branchId = commandExecutionBranchId(this._lastCommandResult);
        return html`
            <section class="info-card info-card--success">
                <div class="info-card__title">${this.t('durable_history_modal.outcome_heading')}</div>
                <ul class="info-card__list">
                    ${effect === null
                        ? nothing
                        : html`
                            <li>
                                ${effect.activates_head
                                    ? this.t('durable_history_modal.outcome_activates_yes')
                                    : this.t('durable_history_modal.outcome_activates_no')}
                            </li>
                            <li>
                                ${this.t('durable_history_modal.outcome_base', {
                                    sequence: String(effect.source_sequence),
                                })}
                            </li>
                            <li>
                                ${this.t('durable_history_modal.outcome_events_after', {
                                    count: String(effect.source_events_after_base),
                                })}
                            </li>
                            ${effect.instance_status.length > 0
                                ? html`<li>
                                    ${this.t('durable_history_modal.outcome_status', {
                                        status: effect.instance_status,
                                    })}
                                </li>`
                                : nothing}
                            <li>${this.t('durable_history_modal.outcome_no_auto_resume')}</li>
                        `}
                    ${branchId.length > 0
                        ? html`<li class="mono">
                            ${this.t('durable_history_modal.outcome_branch_id', {
                                branchId: formatDurableBranchLabel(branchId),
                            })}
                        </li>`
                        : nothing}
                </ul>
                <div class="action-rail__row">
                    <platform-button variant="primary" @click=${() => this.close()}>
                        ${this.t('durable_history_modal.action_continue_chat')}
                    </platform-button>
                </div>
            </section>
        `;
    }

    _renderActionRail(event: DurableEventRow) {
        const canRetry = this._isRetryableEvent(event);
        const commandBusy = this._commandBusy();
        const canPatch = this._stateJson !== null;
        return html`
            <section class="action-rail">
                <div class="action-rail__row">
                    <platform-button
                        variant="secondary"
                        title=${this.t('durable_history_modal.action_fork_help')}
                        ?disabled=${commandBusy}
                        @click=${() => this._forkSelected()}
                    >
                        <platform-icon name="git-branch" size="16"></platform-icon>
                        ${this.t('durable_history_modal.action_fork')}
                    </platform-button>
                    <platform-button
                        variant="danger"
                        title=${this.t('durable_history_modal.action_rewind_help')}
                        ?disabled=${commandBusy}
                        @click=${() => this._rewindSelected()}
                    >
                        <platform-icon name="rotate-ccw" size="16"></platform-icon>
                        ${this.t('durable_history_modal.action_rewind')}
                    </platform-button>
                    <platform-button
                        variant="primary"
                        title=${canRetry
                            ? this.t('durable_history_modal.action_retry_help')
                            : this.t('durable_history_modal.action_retry_disabled')}
                        ?disabled=${!canRetry || commandBusy}
                        @click=${() => this._retrySelectedFailure()}
                    >
                        <platform-icon name="play" size="16"></platform-icon>
                        ${this.t('durable_history_modal.action_retry')}
                    </platform-button>
                </div>
                <div class="action-hint">${this.t('durable_history_modal.action_fork_help')}</div>
                <div class="action-hint">${this.t('durable_history_modal.action_rewind_help')}</div>
                <div class="action-rail__row">
                    <platform-button
                        variant="secondary"
                        title=${this.t('durable_history_modal.action_state_help')}
                        ?disabled=${this._stateAtOp.busy}
                        @click=${() => this._loadSelectedState()}
                    >
                        <platform-icon name="trace-json" size="16"></platform-icon>
                        ${this.t('durable_history_modal.action_state')}
                    </platform-button>
                    <platform-button
                        variant="secondary"
                        title=${canPatch
                            ? this.t('durable_history_modal.action_patch_help')
                            : this.t('durable_history_modal.action_patch_disabled')}
                        ?disabled=${!canPatch || commandBusy}
                        @click=${() => this._manualPatchSelected()}
                    >
                        <platform-icon name="save" size="16"></platform-icon>
                        ${this.t('durable_history_modal.action_patch')}
                    </platform-button>
                    <platform-button
                        variant="ghost"
                        title=${this.t('durable_history_modal.action_copy_anchor_help')}
                        @click=${() => this._copySelectedAnchor()}
                    >
                        <platform-icon name="copy" size="16"></platform-icon>
                        ${this.t('durable_history_modal.action_copy_anchor')}
                    </platform-button>
                </div>
            </section>
        `;
    }

    _renderDetailContent() {
        if (this._selectedTab === 'state' && this._stateJson === null) {
            return html`
                <div class="state-empty">
                    <platform-button variant="secondary" @click=${() => this._loadSelectedState()}>
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
                    .value=${this._stateEditText}
                    @change=${this._onStateEdit}
                ></flows-code-editor>
            `;
        }
        const value = this._detailJsonValue();
        const json = value === null ? '' : formatJsonPretty(value);
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
            return html`<platform-empty-state icon="scroll-text" title=${this.t('durable_history_modal.empty')}></platform-empty-state>`;
        }
        return html`
            <section class="detail-panel">
                <div class="detail-head">
                    <div class="panel-title">${this.t('durable_history_modal.inspector_title')}</div>
                    <div class="panel-meta mono">#${event.sequence}</div>
                </div>
                <div class="inspector-scroll">
                    ${this._renderSummaryCard(event)}
                    ${this._renderConsequencesCard(event)}
                    ${this._renderOutcomeCard()}
                    ${this._renderActionRail(event)}
                    <div class="advanced-block">
                        <div class="advanced-block__title">${this.t('durable_history_modal.advanced_heading')}</div>
                        <platform-segmented-control
                            density="compact"
                            .value=${this._selectedTab}
                            .items=${this._detailTabItems()}
                            aria-label=${this.t('durable_history_modal.detail_tabs_aria')}
                            @change=${(e: CustomEvent) => { this._selectedTab = e.detail.value; }}
                        ></platform-segmented-control>
                        <div class="detail-content">${this._renderDetailContent()}</div>
                    </div>
                </div>
            </section>
        `;
    }

    override renderHeader() {
        const sessionId = this._sessionId();
        return sessionId.length > 0
            ? this.t('durable_history_modal.title_with_session', { sessionId })
            : this.t('durable_history_modal.title');
    }

    override renderHeaderActions() {
        return html`
            <platform-button
                variant="ghost"
                icon-only
                density="dense"
                aria-label=${this.t('durable_history_modal.action_refresh')}
                ?disabled=${this._busy()}
                @click=${() => this._loadAll()}
            >
                ${this._busy()
                    ? html`<platform-spinner></platform-spinner>`
                    : html`<platform-icon name="refresh" size="16"></platform-icon>`}
            </platform-button>
        `;
    }

    override renderBody() {
        const sessionId = this._sessionId();
        if (sessionId.length === 0) {
            return html`<platform-empty-state icon="info" title=${this.t('durable_history_modal.session_required')}></platform-empty-state>`;
        }
        const error = this._historyOp.error || this._branchesOp.error || this._stateAtOp.error || this._forkOp.error || this._rewindOp.error || this._retryOp.error || this._manualPatchOp.error;
        if (error) {
            return html`<div class="durable-history-error">${String(error)}</div>`;
        }
        const events = this._historyEvents();
        if (this._historyOp.busy && events.length === 0) {
            return html`<div class="durable-history-loading"><platform-spinner></platform-spinner></div>`;
        }
        return html`
            <div class="durable-history-body">
                ${this._renderLineage()}
                <div class="durable-main">
                    <section class="timeline-panel">
                        <div class="timeline-head">
                            <div class="panel-title">${this.t('durable_history_modal.timeline_title')}</div>
                        </div>
                        ${this._renderTimeline()}
                    </section>
                    ${this._renderDetail()}
                </div>
            </div>
        `;
    }
}

registerModalKind(FlowsDurableHistoryModal.modalKind, 'flows-durable-history-modal');

customElements.define('flows-durable-history-modal', FlowsDurableHistoryModal);
