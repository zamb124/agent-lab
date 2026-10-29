/**
 * BoardPage — канбан-доска задач WorkItem.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { worktrackerKanbanStyles } from '../styles/worktracker-kanban.styles.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '../components/worktracker-work-item-card.js';
import '../components/worktracker-icon-action.js';
import '../components/worktracker-board-picker.js';
import '../components/worktracker-page-header.js';
import { reorderByInsertIndex } from '@platform/lib/utils/reorder-by-insert-index.js';
import type { PropertyValues } from 'lit';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { isJsonObject } from '@platform/lib/utils/json-object.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';

interface BoardColumn {
    board_column_id?: string;
    label?: string;
    state?: string;
    position?: number;
    [key: string]: unknown;
}

interface BoardRecord {
    board_id?: string;
    name?: string;
    columns?: BoardColumn[];
    [key: string]: unknown;
}

const WORK_ITEM_MIME = 'application/x-worktracker-work-item-id';
const BOARD_COLUMN_MIME = 'application/x-worktracker-board-column-id';
const BOARD_COLUMN_INDEX_MIME = 'application/x-worktracker-board-column-index';

function missingAsEmpty(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

function optionalZero(value: unknown): number {
    if (value === undefined || value === null) return 0;
    return Number(value);
}

function isBoardRecord(value: unknown): value is BoardRecord {
    return isJsonObject(value);
}

function isBoardColumn(value: unknown): value is BoardColumn {
    return isJsonObject(value);
}

function boardRecords(items: readonly unknown[]): BoardRecord[] {
    const rows: BoardRecord[] = [];
    for (const item of items) {
        if (!isBoardRecord(item)) {
            throw new Error('WorktrackerBoardPage: board must be an object');
        }
        rows.push(item);
    }
    return rows;
}

function createdBoardId(event: PlatformEvent): string | null {
    if (!isJsonObject(event.payload)) {
        return null;
    }
    const item = event.payload.item;
    if (!isBoardRecord(item) || typeof item.board_id !== 'string') {
        return null;
    }
    return item.board_id;
}

function dragText(transfer: DataTransfer | null, mime: string): string {
    if (transfer === null) return '';
    return transfer.getData(mime);
}

export class WorktrackerBoardPage extends PlatformPage {
    static i18nNamespace = 'worktracker';
    declare _activeBoardId: string;
    declare _dragOverColumnId: string;
    declare _draggingColumnId: string;
    declare _columnInsertIndex: number;
    private _boards: ResourceController;
    private _workItems: ResourceController;
    private _moveOp: OpController;


    static override properties = {
        _activeBoardId: { state: true },
        _dragOverColumnId: { state: true },
        _draggingColumnId: { state: true },
        _columnInsertIndex: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        worktrackerKanbanStyles,
        css`
            :host { display: flex; flex-direction: column; min-height: 0; flex: 1; width: 100%; }
            .toolbar-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
            }
            .column-insert {
                flex: 0 0 12px;
                align-self: stretch;
                position: relative;
                margin: 0 -6px;
                z-index: 2;
            }
            .column-insert.active::before {
                content: '';
                position: absolute;
                top: var(--space-2);
                bottom: var(--space-2);
                left: 50%;
                width: 3px;
                transform: translateX(-50%);
                border-radius: var(--radius-full);
                background: var(--accent);
                box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent);
            }
            .column {
                display: flex;
                flex-direction: column;
                min-width: 300px;
                max-width: 300px;
                flex: 0 0 auto;
                background: var(--glass-tint-subtle);
                border: var(--worktracker-divider);
                border-radius: var(--radius-lg);
                padding: 0;
            }
            .column.drag-over { outline: 2px dashed var(--accent); }
            .column.column-dragging { opacity: 0.55; }
            .column-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                font-weight: 600;
                font-size: var(--text-sm);
                padding: var(--space-2);
                border-radius: var(--radius-md);
                cursor: grab;
            }
            .column-head:active { cursor: grabbing; }
            .column-head-left {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }
            .column-head-left span {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .drag-handle {
                flex-shrink: 0;
                color: var(--text-tertiary);
            }
            .count { color: var(--text-tertiary); font-weight: 500; }
            .cards { display: flex; flex-direction: column; gap: var(--space-2); min-height: 40px; }
            .card-wrap { cursor: grab; }
            .card-wrap:active { cursor: grabbing; }
            .empty {
                padding: var(--space-8) var(--space-4);
                color: var(--text-tertiary);
                text-align: center;
                font-size: var(--text-sm);
            }
            .empty-actions {
                display: flex;
                justify-content: center;
                gap: var(--space-2);
                margin-top: var(--space-4);
            }
        `,
    ];

    constructor() {
        super();
        this._activeBoardId = '';
        this._dragOverColumnId = '';
        this._draggingColumnId = '';
        this._columnInsertIndex = -1;
        this._boards = this.useResource('worktracker/boards');
        this._workItems = this.useResource('worktracker/work_items');
        this._moveOp = this.useOp('worktracker/work_item_move');
        this.useEvent(this._boards.resource.events.CREATED, (event: PlatformEvent) => {
            const boardId = createdBoardId(event);
            if (boardId === null) {
                return;
            }
            this._selectBoard(boardId);
        });
        // Созданная задача уже смержена коллекцией; страница лишь переключается на её доску.
        this.useEvent(this._workItems.resource.events.CREATED, (event: PlatformEvent) => {
            const boardId = createdBoardId(event);
            if (boardId === null) {
                return;
            }
            if (this._activeBoardId !== boardId) {
                this._selectBoard(boardId);
            }
        });
    }

    override connectedCallback() {
        super.connectedCallback();
        const urlBoardId = this._readBoardIdFromUrl();
        if (urlBoardId.length > 0) {
            this._activeBoardId = urlBoardId;
        }
        this._boards.load({});
    }

    override updated(changed: PropertyValues<this>) {
        super.updated(changed);
        // Загрузка привязана к выбранной доске, а не к событиям: смена `_activeBoardId` —
        // единственная точка, где читаются доска и её задачи.
        if (changed.has('_activeBoardId') && this._activeBoardId) {
            this._boards.get(this._activeBoardId);
            this._workItems.load({ board_id: this._activeBoardId });
        }
        const boards = boardRecords(this._boards.items);
        if (boards.length === 0) {
            return;
        }
        const urlBoardId = this._readBoardIdFromUrl();
        const first = boards[0];
        if (first === undefined) {
            throw new Error('WorktrackerBoardPage: board missing');
        }
        const firstBoardId = missingAsEmpty(first.board_id);
        if (!this._activeBoardId) {
            const initialId = urlBoardId.length > 0 && boards.some((b) => b.board_id === urlBoardId)
                ? urlBoardId
                : firstBoardId;
            this._selectBoard(initialId);
            return;
        }
        const stillExists = boards.some((b) => b.board_id === this._activeBoardId);
        if (!stillExists) {
            this._selectBoard(firstBoardId);
        }
    }

    private _readBoardIdFromUrl() {
        if (typeof window === 'undefined' || typeof window.location === 'undefined') {
            return '';
        }
        const boardId = new URLSearchParams(window.location.search).get('board_id');
        if (boardId === null) {
            return '';
        }
        if (typeof boardId !== 'string' || boardId.length === 0) {
            throw new Error('WorktrackerBoardPage: board_id must be non-empty string');
        }
        return boardId;
    }

    private _persistBoardId(boardId: string) {
        if (typeof window === 'undefined' || typeof window.location === 'undefined') {
            return;
        }
        const url = new URL(window.location.href);
        if (typeof boardId === 'string' && boardId.length > 0) {
            url.searchParams.set('board_id', boardId);
        } else {
            url.searchParams.delete('board_id');
        }
        const next = `${url.pathname}${url.search}${url.hash}`;
        window.history.replaceState(window.history.state, '', next);
    }

    private _selectBoard(boardId: string) {
        if (typeof boardId !== 'string' || boardId.length === 0) {
            throw new Error('WorktrackerBoardPage: boardId required');
        }
        this._activeBoardId = boardId;
        this._persistBoardId(boardId);
    }

    private _openCreateTask() {
        this.openModal('worktracker.work_item_create', { boardId: this._activeBoardId });
    }

    private _openCreateBoard() {
        this.openModal('worktracker.board_create', {});
    }

    private _openBoardSettings() {
        if (typeof this._activeBoardId !== 'string' || this._activeBoardId.length === 0) {
            return;
        }
        this.openModal('worktracker.board_settings', { boardId: this._activeBoardId });
    }

    private _activeBoard(): BoardRecord | null {
        const boards = boardRecords(this._boards.items);
        const fromList = boards.find((b) => b.board_id === this._activeBoardId);
        if (fromList) {
            return fromList;
        }
        const byId = this._boards.byId;
        if (!isJsonObject(byId)) {
            return null;
        }
        const cached = byId[this._activeBoardId];
        return isBoardRecord(cached) ? cached : null;
    }

    private _sortedColumns(columns: unknown): BoardColumn[] {
        if (!Array.isArray(columns)) {
            throw new Error('WorktrackerBoardPage: columns must be an array');
        }
        const rows: BoardColumn[] = [];
        for (const item of columns) {
            if (!isBoardColumn(item)) {
                throw new Error('WorktrackerBoardPage: column must be an object');
            }
            rows.push(item);
        }
        return rows.slice().sort((left, right) => optionalZero(left.position) - optionalZero(right.position));
    }

    private _itemsForColumn(columnId: string) {
        const items = this._workItems.items;
        return items.filter((i) => i.board_column_id === columnId);
    }

    private _onDragStart(e: DragEvent, workItemId: string) {
        e.dataTransfer?.setData(WORK_ITEM_MIME, workItemId);
        if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
    }

    private _onDragOver(e: DragEvent, columnId: string) {
        if (!e.dataTransfer || e.dataTransfer.types.includes(BOARD_COLUMN_MIME)) {
            return;
        }
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (this._dragOverColumnId !== columnId) {
            this._dragOverColumnId = columnId;
        }
    }

    private _onColumnHeadDragStart(e: DragEvent, columnId: string) {
        e.stopPropagation();
        e.dataTransfer?.setData(BOARD_COLUMN_MIME, columnId);
        if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
        this._draggingColumnId = columnId;
    }

    private _onColumnHeadDragEnd() {
        this._draggingColumnId = '';
        this._columnInsertIndex = -1;
    }

    private _onColumnInsertDragOver(event: DragEvent, insertIndex: number) {
        if (!event.dataTransfer || !event.dataTransfer.types.includes(BOARD_COLUMN_MIME)) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = 'move';
        if (this._columnInsertIndex !== insertIndex) {
            this._columnInsertIndex = insertIndex;
        }
    }

    private _resolveColumnInsertIndexFromPointer(event: DragEvent, columnIndex: number) {
        const target = event.currentTarget;
        if (!(target instanceof HTMLElement)) {
            return columnIndex;
        }
        const rect = target.getBoundingClientRect();
        const insertBefore = event.clientX < rect.left + rect.width / 2;
        return insertBefore ? columnIndex : columnIndex + 1;
    }

    private _onColumnHeadDragOver(event: DragEvent, columnIndex: number) {
        if (!event.dataTransfer || !event.dataTransfer.types.includes(BOARD_COLUMN_MIME)) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = 'move';
        const insertIndex = this._resolveColumnInsertIndexFromPointer(event, columnIndex);
        if (this._columnInsertIndex !== insertIndex) {
            this._columnInsertIndex = insertIndex;
        }
    }

    private _onColumnHeadDrop(event: DragEvent, columnIndex: number) {
        if (!event.dataTransfer || !event.dataTransfer.types.includes(BOARD_COLUMN_MIME)) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        this._columnInsertIndex = -1;
        this._draggingColumnId = '';
        const sourceColumnId = event.dataTransfer.getData(BOARD_COLUMN_MIME);
        if (typeof sourceColumnId !== 'string' || sourceColumnId.length === 0) {
            return;
        }
        const insertIndex = this._resolveColumnInsertIndexFromPointer(event, columnIndex);
        this._persistColumnOrderToInsert(sourceColumnId, insertIndex);
    }

    private _onColumnInsertDrop(event: DragEvent, insertIndex: number) {
        event.preventDefault();
        event.stopPropagation();
        this._columnInsertIndex = -1;
        this._draggingColumnId = '';
        const sourceColumnId = dragText(event.dataTransfer, BOARD_COLUMN_MIME);
        if (typeof sourceColumnId !== 'string' || sourceColumnId.length === 0) {
            return;
        }
        this._persistColumnOrderToInsert(sourceColumnId, insertIndex);
    }

    private _persistColumnOrderToInsert(sourceColumnId: string, insertIndex: number) {
        const board = this._activeBoard();
        if (!board || !Array.isArray(board.columns)) {
            throw new Error('WorktrackerBoardPage: active board required for column reorder');
        }
        const columns = this._sortedColumns(board.columns);
        const fromIndex = columns.findIndex((column) => column.board_column_id === sourceColumnId);
        if (fromIndex === -1) {
            return;
        }
        const next = reorderByInsertIndex(columns, fromIndex, insertIndex);
        const payload = next.map((column, position) => {
            if (typeof column.board_column_id !== 'string' || column.board_column_id.length === 0) {
                throw new Error('WorktrackerBoardPage: board_column_id required');
            }
            if (typeof column.label !== 'string' || column.label.length === 0) {
                throw new Error('WorktrackerBoardPage: column label required');
            }
            if (typeof column.state !== 'string' || column.state.length === 0) {
                throw new Error('WorktrackerBoardPage: column state required');
            }
            return {
                board_column_id: column.board_column_id,
                label: column.label,
                state: column.state,
                position,
            };
        });
        this._boards.update(this._activeBoardId, { columns: payload });
    }

    private _onDrop(e: DragEvent, columnId: string) {
        e.preventDefault();
        this._dragOverColumnId = '';
        const workItemId = dragText(e.dataTransfer, WORK_ITEM_MIME);
        if (!workItemId) {
            return;
        }
        this._moveOp.run({ work_item_id: workItemId, board_column_id: columnId });
    }

    private _renderColumnInsertMarker(index: number) {
        const columnReorderActive = typeof this._draggingColumnId === 'string' && this._draggingColumnId.length > 0;
        const active = columnReorderActive && this._columnInsertIndex === index;
        return html`
            <div
                class="column-insert ${active ? 'active' : ''}"
                @dragover=${(event: DragEvent) => this._onColumnInsertDragOver(event, index)}
                @drop=${(event: DragEvent) => this._onColumnInsertDrop(event, index)}
            ></div>
        `;
    }

    private _renderColumn(column: BoardColumn, columnIndex: number) {
        const columnId = missingAsEmpty(column.board_column_id);
        const items = this._itemsForColumn(columnId);
        const isOver = this._dragOverColumnId === columnId;
        const isDragging = this._draggingColumnId === columnId;
        return html`
            <div
                class="column ${isOver ? 'drag-over' : ''} ${isDragging ? 'column-dragging' : ''}"
                @dragover=${(e: DragEvent) => this._onDragOver(e, columnId)}
                @drop=${(e: DragEvent) => this._onDrop(e, columnId)}
            >
                <div
                    class="column-head"
                    draggable="true"
                    title=${this.t('board_page.reorder_column')}
                    @dragstart=${(e: DragEvent) => this._onColumnHeadDragStart(e, columnId)}
                    @dragend=${() => this._onColumnHeadDragEnd()}
                    @dragover=${(e: DragEvent) => this._onColumnHeadDragOver(e, columnIndex)}
                    @drop=${(e: DragEvent) => this._onColumnHeadDrop(e, columnIndex)}
                >
                    <span class="column-head-left">
                        <platform-icon class="drag-handle" name="drag-handle" size="14"></platform-icon>
                        <span>${column.label}</span>
                    </span>
                    <span class="count">${items.length}</span>
                </div>
                <div class="cards wt-kanban-column-body">
                    ${items.map((item: Record<string, unknown>) => html`
                        <div
                            class="card-wrap"
                            draggable="true"
                            @dragstart=${(e: DragEvent) => this._onDragStart(e, missingAsEmpty(item.work_item_id))}
                        >
                            <worktracker-work-item-card
                                .item=${item}
                                variant="card"
                                show-preview
                                @changed=${() => this._workItems.load({ board_id: this._activeBoardId })}
                            ></worktracker-work-item-card>
                        </div>
                    `)}
                </div>
            </div>
        `;
    }

    override render() {
        const board = this._activeBoard();
        const boards = this._boards.items;
        const hasBoard = board && Array.isArray(board.columns) && board.columns.length > 0;

        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <div class="wt-board-toolbar">
                <worktracker-board-picker
                    .boards=${boards}
                    active-board-id=${this._activeBoardId}
                    ?loading=${this._boards.loading}
                    @board-select=${(e: CustomEvent<{ board_id?: unknown }>) => {
                        const detail = e.detail;
                        if (!detail || typeof detail.board_id !== 'string') {
                            throw new Error('WorktrackerBoardPage: board-select requires board_id');
                        }
                        this._selectBoard(detail.board_id);
                    }}
                    @create-board=${() => this._openCreateBoard()}
                ></worktracker-board-picker>
                <div class="wt-board-toolbar-spacer"></div>
                <div class="toolbar-actions">
                    <worktracker-icon-action
                        icon="plus"
                        .title=${this.t('board_page.create_task')}
                        ?disabled=${!this._activeBoardId}
                        @action=${() => this._openCreateTask()}
                    ></worktracker-icon-action>
                    <worktracker-icon-action
                        icon="layers"
                        .title=${this.t('board_page.create_board')}
                        @action=${() => this._openCreateBoard()}
                    ></worktracker-icon-action>
                    <worktracker-icon-action
                        icon="settings"
                        .title=${this.t('board_page.settings')}
                        ?disabled=${!this._activeBoardId}
                        @action=${() => this._openBoardSettings()}
                    ></worktracker-icon-action>
                </div>
            </div>
            ${hasBoard ? (() => {
                const columns = this._sortedColumns(board.columns);
                return html`
                <div class="wt-kanban board">
                    ${columns.flatMap((column, index) => [
                        this._renderColumnInsertMarker(index),
                        this._renderColumn(column, index),
                    ])}
                    ${this._renderColumnInsertMarker(columns.length)}
                </div>
                `;
            })() : html`
                <div class="empty">
                    ${this.t('board_page.empty')}
                    <div class="empty-actions">
                        <worktracker-icon-action
                            icon="layers"
                            .title=${this.t('board_page.create_board')}
                            @action=${() => this._openCreateBoard()}
                        ></worktracker-icon-action>
                    </div>
                </div>
            `}
        `;
    }
}

customElements.define('worktracker-board-page', WorktrackerBoardPage);
