/**
 * platform-work-item-board — канбан по WorkItem.state (open / in_progress / blocked / done).
 * DnD между колонками → platform/work_item_move { work_item_id, state }.
 */

import { html, css } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import './platform-work-item-row.js';

const COLUMNS = Object.freeze([
    Object.freeze({ state: 'open', labelKey: 'work_item_badge.state.open' }),
    Object.freeze({ state: 'in_progress', labelKey: 'work_item_badge.state.in_progress' }),
    Object.freeze({ state: 'blocked', labelKey: 'work_item_badge.state.blocked' }),
    Object.freeze({ state: 'done', labelKey: 'work_item_badge.state.done' }),
]);

const WORK_ITEM_MIME = 'application/x-platform-work-item-id';
const COLUMN_STATES = Object.freeze(COLUMNS.map((col) => col.state));

export class PlatformWorkItemBoard extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        items: { attribute: false },
        selectedWorkItemId: { type: String, attribute: 'selected-work-item-id' },
        _dragOverState: { state: true },
        _pendingById: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                overflow-x: auto;
            }
            .board {
                display: grid;
                grid-auto-flow: column;
                grid-auto-columns: minmax(260px, 1fr);
                gap: var(--space-4);
                min-height: 320px;
                padding-bottom: var(--space-2);
            }
            .column {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-3);
                transition: outline-color 120ms ease, border-color 120ms ease;
            }
            .column.drag-over {
                outline: 2px dashed var(--accent);
                border-color: color-mix(in srgb, var(--accent) 40%, transparent);
            }
            .column-title {
                display: flex;
                align-items: center;
                justify-content: space-between;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                padding: 0 var(--space-1) var(--space-2);
            }
            .count {
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
            }
            .list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-height: 80px;
                flex: 1;
            }
            .empty {
                padding: var(--space-4);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            .card-wrap {
                cursor: grab;
            }
            .card-wrap:active {
                cursor: grabbing;
            }
            .card-wrap.dragging {
                opacity: 0.55;
            }
            platform-work-item-row {
                background: var(--bg-elevated, var(--glass-solid-medium));
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
            }
        `,
    ];

    constructor() {
        super();
        this.items = [];
        this.selectedWorkItemId = '';
        this._dragOverState = '';
        this._pendingById = Object.freeze({});
        this._draggingId = '';
        this._moveOp = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._moveOp = this.useOp('platform/work_item_move');
    }

    updated(changed) {
        super.updated(changed);
        if (!changed.has('items') || !Array.isArray(this.items)) {
            return;
        }
        const pendingIds = Object.keys(this._pendingById);
        if (pendingIds.length === 0) {
            return;
        }
        const next = { ...this._pendingById };
        let dirty = false;
        for (const workItemId of pendingIds) {
            const item = this.items.find((row) => row && row.work_item_id === workItemId);
            if (!item || item.state === next[workItemId]) {
                delete next[workItemId];
                dirty = true;
            }
        }
        if (dirty) {
            this._pendingById = Object.freeze(next);
        }
    }

    _effectiveState(item) {
        if (!item || typeof item.work_item_id !== 'string') {
            throw new Error('platform-work-item-board: item.work_item_id required');
        }
        const pending = this._pendingById[item.work_item_id];
        if (typeof pending === 'string' && pending.length > 0) {
            return pending;
        }
        if (typeof item.state !== 'string' || item.state.length === 0) {
            throw new Error('platform-work-item-board: item.state required');
        }
        return item.state;
    }

    _itemsForState(state) {
        if (!Array.isArray(this.items)) {
            return [];
        }
        return this.items.filter((item) => item && this._effectiveState(item) === state);
    }

    _onDragStart(event, workItemId) {
        if (!(event.dataTransfer instanceof DataTransfer)) {
            throw new Error('platform-work-item-board: DataTransfer required');
        }
        if (typeof workItemId !== 'string' || workItemId.length === 0) {
            throw new Error('platform-work-item-board: work_item_id required');
        }
        event.dataTransfer.setData(WORK_ITEM_MIME, workItemId);
        event.dataTransfer.effectAllowed = 'move';
        this._draggingId = workItemId;
    }

    _onDragEnd() {
        this._draggingId = '';
        this._dragOverState = '';
    }

    _onDragOver(event, state) {
        if (typeof this._draggingId !== 'string' || this._draggingId.length === 0) {
            return;
        }
        event.preventDefault();
        if (event.dataTransfer instanceof DataTransfer) {
            event.dataTransfer.dropEffect = 'move';
        }
        if (this._dragOverState !== state) {
            this._dragOverState = state;
        }
    }

    _onDragLeave(event, state) {
        const current = event.currentTarget;
        const related = event.relatedTarget;
        if (current instanceof Node && related instanceof Node && current.contains(related)) {
            return;
        }
        if (this._dragOverState === state) {
            this._dragOverState = '';
        }
    }

    async _onDrop(event, state) {
        event.preventDefault();
        this._dragOverState = '';
        if (!(event.dataTransfer instanceof DataTransfer)) {
            throw new Error('platform-work-item-board: DataTransfer required');
        }
        if (!COLUMN_STATES.includes(state)) {
            throw new Error(`platform-work-item-board: unsupported state ${state}`);
        }
        const workItemId = event.dataTransfer.getData(WORK_ITEM_MIME);
        if (typeof workItemId !== 'string' || workItemId.length === 0) {
            return;
        }
        const source = Array.isArray(this.items)
            ? this.items.find((item) => item && item.work_item_id === workItemId)
            : null;
        if (!source) {
            return;
        }
        const currentState = this._effectiveState(source);
        if (currentState === state) {
            return;
        }
        if (!this._moveOp) {
            throw new Error('platform-work-item-board: move op not ready');
        }
        this._pendingById = Object.freeze({ ...this._pendingById, [workItemId]: state });
        const result = await this._moveOp.run({ work_item_id: workItemId, state });
        if (result === null) {
            const next = { ...this._pendingById };
            delete next[workItemId];
            this._pendingById = Object.freeze(next);
            return;
        }
        this.emit('work-item-changed', { work_item_id: workItemId, state });
    }

    render() {
        return html`
            <div class="board">
                ${COLUMNS.map((col) => {
                    const colItems = this._itemsForState(col.state);
                    const isOver = this._dragOverState === col.state;
                    return html`
                        <section
                            class="column ${isOver ? 'drag-over' : ''}"
                            data-state=${col.state}
                            @dragover=${(e) => this._onDragOver(e, col.state)}
                            @dragleave=${(e) => this._onDragLeave(e, col.state)}
                            @drop=${(e) => this._onDrop(e, col.state)}
                        >
                            <div class="column-title">
                                <span>${this.t(col.labelKey)}</span>
                                <span class="count">${colItems.length}</span>
                            </div>
                            <div class="list">
                                ${colItems.length === 0
                                    ? html`<div class="empty">${this.t('work_item.board_empty')}</div>`
                                    : colItems.map(
                                        (item) => html`
                                            <div
                                                class="card-wrap ${this._draggingId === item.work_item_id ? 'dragging' : ''}"
                                                draggable="true"
                                                @dragstart=${(e) => this._onDragStart(e, item.work_item_id)}
                                                @dragend=${() => this._onDragEnd()}
                                            >
                                                <platform-work-item-row
                                                    data-no-default-nav
                                                    .item=${item}
                                                    ?selected=${item.work_item_id === this.selectedWorkItemId}
                                                    ?show-preview=${false}
                                                    @work-item-open=${(e) => this.emit('work-item-open', e.detail)}
                                                ></platform-work-item-row>
                                            </div>
                                        `,
                                    )}
                            </div>
                        </section>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('platform-work-item-board', PlatformWorkItemBoard);
