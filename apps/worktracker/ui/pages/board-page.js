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
import { reorderByInsertIndex } from '../utils/board-column-reorder.js';

const WORK_ITEM_MIME = 'application/x-worktracker-work-item-id';
const BOARD_COLUMN_MIME = 'application/x-worktracker-board-column-id';
const BOARD_COLUMN_INDEX_MIME = 'application/x-worktracker-board-column-index';

export class WorktrackerBoardPage extends PlatformPage {
    static i18nNamespace = 'worktracker';

    static properties = {
        _activeBoardId: { state: true },
        _dragOverColumnId: { state: true },
        _draggingColumnId: { state: true },
        _columnInsertIndex: { state: true },
    };

    static styles = [
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
        this.useEvent(this._boards.resource.events.CREATED, (event) => {
            const payload = event.payload;
            if (!payload || typeof payload !== 'object' || !('item' in payload)) {
                return;
            }
            const item = payload.item;
            if (!item || typeof item !== 'object' || typeof item.board_id !== 'string') {
                return;
            }
            this._selectBoard(item.board_id);
        });
        this.useEvent(this._boards.resource.events.UPDATED, () => {
            this._boards.load({});
        });
        this.useEvent(this._workItems.resource.events.CREATED, (event) => {
            const payload = event.payload;
            if (!payload || typeof payload !== 'object' || !('item' in payload)) {
                return;
            }
            const item = payload.item;
            if (!item || typeof item !== 'object' || typeof item.board_id !== 'string') {
                return;
            }
            if (this._activeBoardId !== item.board_id) {
                this._selectBoard(item.board_id);
                return;
            }
            this._workItems.load({ board_id: item.board_id });
        });
    }

    connectedCallback() {
        super.connectedCallback();
        const urlBoardId = this._readBoardIdFromUrl();
        if (urlBoardId.length > 0) {
            this._activeBoardId = urlBoardId;
            this._boards.get(urlBoardId);
            this._workItems.load({ board_id: urlBoardId });
        }
        this._boards.load({});
    }

    updated(changed) {
        super.updated(changed);
        const boards = this._boards.items;
        if (!Array.isArray(boards) || boards.length === 0) {
            return;
        }
        const urlBoardId = this._readBoardIdFromUrl();
        if (!this._activeBoardId) {
            const initialId = urlBoardId.length > 0 && boards.some((b) => b.board_id === urlBoardId)
                ? urlBoardId
                : boards[0].board_id;
            this._selectBoard(initialId);
            return;
        }
        const stillExists = boards.some((b) => b.board_id === this._activeBoardId);
        if (!stillExists) {
            this._selectBoard(boards[0].board_id);
        }
    }

    _readBoardIdFromUrl() {
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

    _persistBoardId(boardId) {
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

    _selectBoard(boardId) {
        if (typeof boardId !== 'string' || boardId.length === 0) {
            throw new Error('WorktrackerBoardPage: boardId required');
        }
        this._activeBoardId = boardId;
        this._persistBoardId(boardId);
        this._boards.get(boardId);
        this._workItems.load({ board_id: boardId });
    }

    _openCreateTask() {
        this.openModal('worktracker.work_item_create', { boardId: this._activeBoardId });
    }

    _openCreateBoard() {
        this.openModal('worktracker.board_create', {});
    }

    _openBoardSettings() {
        if (typeof this._activeBoardId !== 'string' || this._activeBoardId.length === 0) {
            return;
        }
        this.openModal('worktracker.board_settings', { boardId: this._activeBoardId });
    }

    _activeBoard() {
        const boards = this._boards.items || [];
        const fromList = boards.find((b) => b.board_id === this._activeBoardId);
        if (fromList) {
            return fromList;
        }
        const byId = this._boards.byId;
        if (byId && typeof byId === 'object' && byId[this._activeBoardId]) {
            return byId[this._activeBoardId];
        }
        return null;
    }

    _sortedColumns(columns) {
        if (!Array.isArray(columns)) {
            throw new Error('WorktrackerBoardPage: columns must be an array');
        }
        return columns.slice().sort((left, right) => left.position - right.position);
    }

    _itemsForColumn(columnId) {
        const items = this._workItems.items || [];
        return items.filter((i) => i.board_column_id === columnId);
    }

    _onDragStart(e, workItemId) {
        e.dataTransfer.setData(WORK_ITEM_MIME, workItemId);
        e.dataTransfer.effectAllowed = 'move';
    }

    _onDragOver(e, columnId) {
        if (e.dataTransfer.types.includes(BOARD_COLUMN_MIME)) {
            return;
        }
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (this._dragOverColumnId !== columnId) {
            this._dragOverColumnId = columnId;
        }
    }

    _onColumnHeadDragStart(e, columnId) {
        e.stopPropagation();
        e.dataTransfer.setData(BOARD_COLUMN_MIME, columnId);
        e.dataTransfer.effectAllowed = 'move';
        this._draggingColumnId = columnId;
    }

    _onColumnHeadDragEnd() {
        this._draggingColumnId = '';
        this._columnInsertIndex = -1;
    }

    _onColumnInsertDragOver(event, insertIndex) {
        if (!event.dataTransfer.types.includes(BOARD_COLUMN_MIME)) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = 'move';
        if (this._columnInsertIndex !== insertIndex) {
            this._columnInsertIndex = insertIndex;
        }
    }

    _resolveColumnInsertIndexFromPointer(event, columnIndex) {
        const target = event.currentTarget;
        if (!(target instanceof HTMLElement)) {
            return columnIndex;
        }
        const rect = target.getBoundingClientRect();
        const insertBefore = event.clientX < rect.left + rect.width / 2;
        return insertBefore ? columnIndex : columnIndex + 1;
    }

    _onColumnHeadDragOver(event, columnIndex) {
        if (!event.dataTransfer.types.includes(BOARD_COLUMN_MIME)) {
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

    _onColumnHeadDrop(event, columnIndex) {
        if (!event.dataTransfer.types.includes(BOARD_COLUMN_MIME)) {
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

    _onColumnInsertDrop(event, insertIndex) {
        event.preventDefault();
        event.stopPropagation();
        this._columnInsertIndex = -1;
        this._draggingColumnId = '';
        const sourceColumnId = event.dataTransfer.getData(BOARD_COLUMN_MIME);
        if (typeof sourceColumnId !== 'string' || sourceColumnId.length === 0) {
            return;
        }
        this._persistColumnOrderToInsert(sourceColumnId, insertIndex);
    }

    _persistColumnOrderToInsert(sourceColumnId, insertIndex) {
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

    _onDrop(e, columnId) {
        e.preventDefault();
        this._dragOverColumnId = '';
        const workItemId = e.dataTransfer.getData(WORK_ITEM_MIME);
        if (!workItemId) {
            return;
        }
        this._moveOp.run({ work_item_id: workItemId, board_column_id: columnId });
    }

    _renderColumnInsertMarker(index) {
        const columnReorderActive = typeof this._draggingColumnId === 'string' && this._draggingColumnId.length > 0;
        const active = columnReorderActive && this._columnInsertIndex === index;
        return html`
            <div
                class="column-insert ${active ? 'active' : ''}"
                @dragover=${(event) => this._onColumnInsertDragOver(event, index)}
                @drop=${(event) => this._onColumnInsertDrop(event, index)}
            ></div>
        `;
    }

    _renderColumn(column, columnIndex) {
        const items = this._itemsForColumn(column.board_column_id);
        const isOver = this._dragOverColumnId === column.board_column_id;
        const isDragging = this._draggingColumnId === column.board_column_id;
        return html`
            <div
                class="column ${isOver ? 'drag-over' : ''} ${isDragging ? 'column-dragging' : ''}"
                @dragover=${(e) => this._onDragOver(e, column.board_column_id)}
                @drop=${(e) => this._onDrop(e, column.board_column_id)}
            >
                <div
                    class="column-head"
                    draggable="true"
                    title=${this.t('board_page.reorder_column')}
                    @dragstart=${(e) => this._onColumnHeadDragStart(e, column.board_column_id)}
                    @dragend=${() => this._onColumnHeadDragEnd()}
                    @dragover=${(e) => this._onColumnHeadDragOver(e, columnIndex)}
                    @drop=${(e) => this._onColumnHeadDrop(e, columnIndex)}
                >
                    <span class="column-head-left">
                        <platform-icon class="drag-handle" name="drag-handle" size="14"></platform-icon>
                        <span>${column.label}</span>
                    </span>
                    <span class="count">${items.length}</span>
                </div>
                <div class="cards wt-kanban-column-body">
                    ${items.map((item) => html`
                        <div
                            class="card-wrap"
                            draggable="true"
                            @dragstart=${(e) => this._onDragStart(e, item.work_item_id)}
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

    render() {
        const board = this._activeBoard();
        const boards = this._boards.items || [];
        const hasBoard = board && Array.isArray(board.columns) && board.columns.length > 0;

        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <div class="wt-board-toolbar">
                <worktracker-board-picker
                    .boards=${boards}
                    active-board-id=${this._activeBoardId}
                    ?loading=${this._boards.loading}
                    @board-select=${(e) => {
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
