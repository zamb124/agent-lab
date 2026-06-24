/**
 * BoardSettingsModal — название доски, колонки и маппинг на статусы WorkItem.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-icon.js';
import '../components/worktracker-icon-action.js';
import { reorderByInsertIndex } from '../utils/board-column-reorder.js';

const BOARDS_NAME = 'worktracker/boards';
const BOARD_COLUMN_INDEX_MIME = 'application/x-worktracker-board-column-index';

const BOARD_COLUMN_STATES = [
    'open',
    'in_progress',
    'blocked',
    'done',
    'cancelled',
    'failed',
];

export class WorktrackerBoardSettingsModal extends PlatformFormModal {
    static modalKind = 'worktracker.board_settings';
    static i18nNamespace = 'worktracker';

    static properties = {
        boardId: { type: String },
        _boardName: { state: true },
        _columns: { state: true },
        _loading: { state: true },
        _saving: { state: true },
        _dragColumnIndex: { state: true },
        _columnInsertIndex: { state: true },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-4); }
            .columns-section {
                display: grid;
                gap: var(--space-3);
                padding-top: var(--space-2);
                border-top: 1px solid var(--glass-border-subtle);
            }
            .columns-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .columns-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--text-tertiary);
            }
            .column-row {
                display: grid;
                gap: var(--space-3);
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-tint-subtle);
            }
            .column-row.row-dragging {
                opacity: 0.55;
            }
            .row-insert {
                position: relative;
                height: 12px;
                margin: calc(-1 * var(--space-1)) 0;
            }
            .row-insert.active::before {
                content: '';
                position: absolute;
                left: var(--space-3);
                right: var(--space-3);
                top: 50%;
                height: 3px;
                transform: translateY(-50%);
                border-radius: var(--radius-full);
                background: var(--accent);
                box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent);
            }
            .column-row-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .column-row-lead {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                cursor: grab;
            }
            .column-row-lead:active { cursor: grabbing; }
            .drag-handle {
                flex-shrink: 0;
                color: var(--text-tertiary);
            }
            .column-index {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .column-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }
            .column-fields {
                display: grid;
                gap: var(--space-3);
            }
            @media (min-width: 640px) {
                .column-fields {
                    grid-template-columns: 1fr 1fr;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.headerSavePrimary = true;
        this.boardId = '';
        this._boardName = '';
        this._columns = [];
        this._loading = false;
        this._saving = false;
        this._dragColumnIndex = -1;
        this._columnInsertIndex = -1;
        this._boards = this.useResource(BOARDS_NAME);
        this._snapshotName = '';
        this._snapshotColumns = [];
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(this._boards.resource.events.ITEM_LOADED, (event) => {
            const payload = event.payload;
            if (!payload || typeof payload !== 'object' || !('item' in payload)) {
                return;
            }
            const item = payload.item;
            if (!item || typeof item !== 'object' || item.board_id !== this.boardId) {
                return;
            }
            this._applyBoard(item);
        });
        this.useEvent(this._boards.resource.events.UPDATED, () => {
            this._saving = false;
            this.closeAfterSave();
        });
        this.useEvent(this._boards.resource.events.UPDATE_FAILED, () => {
            this._saving = false;
        });
        this._resetAndLoad();
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('boardId') && typeof this.boardId === 'string' && this.boardId.length > 0) {
            this._resetAndLoad();
        }
    }

    _resetAndLoad() {
        if (typeof this.boardId !== 'string' || this.boardId.length === 0) {
            throw new Error('WorktrackerBoardSettingsModal: boardId required');
        }
        this._boardName = '';
        this._columns = [];
        this._snapshotName = '';
        this._snapshotColumns = [];
        this._loading = true;
        this._boards.get(this.boardId);
    }

    _applyBoard(board) {
        if (typeof board.name !== 'string' || board.name.length === 0) {
            throw new Error('WorktrackerBoardSettingsModal: board.name required');
        }
        if (!Array.isArray(board.columns)) {
            throw new Error('WorktrackerBoardSettingsModal: board.columns required');
        }
        this._boardName = board.name;
        this._snapshotName = board.name;
        this._columns = board.columns
            .slice()
            .sort((left, right) => left.position - right.position)
            .map((column) => ({
                board_column_id: column.board_column_id,
                label: column.label,
                state: column.state,
                position: column.position,
            }));
        this._snapshotColumns = this._columns.map((column) => ({ ...column }));
        this._loading = false;
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        const nameChanged = this._boardName !== this._snapshotName;
        const columnsChanged = JSON.stringify(this._columns) !== JSON.stringify(this._snapshotColumns);
        this.isDirty = nameChanged || columnsChanged;
    }

    _stateConfig() {
        return {
            values: BOARD_COLUMN_STATES.map((state) => ({
                value: state,
                label: this.t(`state.${state}`),
            })),
        };
    }

    _onNameChange(event) {
        const value = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._boardName = value;
    }

    _onColumnLabelChange(index, event) {
        const value = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._columns = this._columns.map((column, i) => (
            i === index ? { ...column, label: value } : column
        ));
    }

    _onColumnStateChange(index, event) {
        const value = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        if (!BOARD_COLUMN_STATES.includes(value)) {
            throw new Error(`WorktrackerBoardSettingsModal: unsupported state ${value}`);
        }
        this._columns = this._columns.map((column, i) => (
            i === index ? { ...column, state: value } : column
        ));
    }

    _nextColumnId() {
        let index = this._columns.length;
        let boardColumnId = `col_${index}`;
        while (this._columns.some((column) => column.board_column_id === boardColumnId)) {
            index += 1;
            boardColumnId = `col_${index}`;
        }
        return boardColumnId;
    }

    _addColumn() {
        const position = this._columns.length;
        this._columns = [
            ...this._columns,
            {
                board_column_id: this._nextColumnId(),
                label: this.t('board_settings_modal.new_column_label'),
                state: 'open',
                position,
            },
        ];
    }

    _removeColumn(index) {
        if (this._columns.length <= 1) {
            return;
        }
        this._columns = this._columns
            .filter((_, i) => i !== index)
            .map((column, position) => ({ ...column, position }));
    }

    _moveColumnToInsert(fromIndex, insertIndex) {
        this._columns = reorderByInsertIndex(this._columns, fromIndex, insertIndex)
            .map((column, position) => ({ ...column, position }));
    }

    _onColumnRowDragStart(event, index) {
        event.stopPropagation();
        event.dataTransfer.setData(BOARD_COLUMN_INDEX_MIME, String(index));
        event.dataTransfer.effectAllowed = 'move';
        this._dragColumnIndex = index;
    }

    _onColumnRowDragEnd() {
        this._dragColumnIndex = -1;
        this._columnInsertIndex = -1;
    }

    _onColumnInsertDragOver(event, insertIndex) {
        if (!event.dataTransfer.types.includes(BOARD_COLUMN_INDEX_MIME)) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = 'move';
        if (this._columnInsertIndex !== insertIndex) {
            this._columnInsertIndex = insertIndex;
        }
    }

    _onColumnInsertDrop(event, insertIndex) {
        event.preventDefault();
        event.stopPropagation();
        this._columnInsertIndex = -1;
        this._dragColumnIndex = -1;
        const rawIndex = event.dataTransfer.getData(BOARD_COLUMN_INDEX_MIME);
        if (typeof rawIndex !== 'string' || rawIndex.length === 0) {
            return;
        }
        const sourceIndex = Number(rawIndex);
        if (Number.isNaN(sourceIndex)) {
            throw new Error('WorktrackerBoardSettingsModal: invalid column drag index');
        }
        this._moveColumnToInsert(sourceIndex, insertIndex);
    }

    _resolveRowInsertIndexFromPointer(event, rowIndex) {
        const target = event.currentTarget;
        if (!(target instanceof HTMLElement)) {
            return rowIndex;
        }
        const rect = target.getBoundingClientRect();
        const insertBefore = event.clientY < rect.top + rect.height / 2;
        return insertBefore ? rowIndex : rowIndex + 1;
    }

    _onColumnRowLeadDragOver(event, rowIndex) {
        if (!event.dataTransfer.types.includes(BOARD_COLUMN_INDEX_MIME)) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = 'move';
        const insertIndex = this._resolveRowInsertIndexFromPointer(event, rowIndex);
        if (this._columnInsertIndex !== insertIndex) {
            this._columnInsertIndex = insertIndex;
        }
    }

    _onColumnRowLeadDrop(event, rowIndex) {
        if (!event.dataTransfer.types.includes(BOARD_COLUMN_INDEX_MIME)) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        this._columnInsertIndex = -1;
        this._dragColumnIndex = -1;
        const rawIndex = event.dataTransfer.getData(BOARD_COLUMN_INDEX_MIME);
        if (typeof rawIndex !== 'string' || rawIndex.length === 0) {
            return;
        }
        const sourceIndex = Number(rawIndex);
        if (Number.isNaN(sourceIndex)) {
            throw new Error('WorktrackerBoardSettingsModal: invalid column drag index');
        }
        const insertIndex = this._resolveRowInsertIndexFromPointer(event, rowIndex);
        this._moveColumnToInsert(sourceIndex, insertIndex);
    }

    _renderColumnInsertMarker(index) {
        const columnReorderActive = this._dragColumnIndex >= 0;
        const active = columnReorderActive && this._columnInsertIndex === index;
        return html`
            <div
                class="row-insert ${active ? 'active' : ''}"
                @dragover=${(event) => this._onColumnInsertDragOver(event, index)}
                @drop=${(event) => this._onColumnInsertDrop(event, index)}
            ></div>
        `;
    }

    _renderColumnRow(column, index) {
        return html`
            <div class="column-row ${this._dragColumnIndex === index ? 'row-dragging' : ''}">
                <div class="column-row-head">
                    <div
                        class="column-row-lead"
                        draggable="true"
                        title=${this.t('board_settings_modal.reorder_column')}
                        @dragstart=${(event) => this._onColumnRowDragStart(event, index)}
                        @dragend=${() => this._onColumnRowDragEnd()}
                        @dragover=${(event) => this._onColumnRowLeadDragOver(event, index)}
                        @drop=${(event) => this._onColumnRowLeadDrop(event, index)}
                    >
                        <platform-icon class="drag-handle" name="drag-handle" size="14"></platform-icon>
                        <span class="column-index">${this.t('board_settings_modal.column_index', { index: index + 1 })}</span>
                    </div>
                    <div class="column-actions">
                        <worktracker-icon-action
                            icon="trash"
                            .title=${this.t('board_settings_modal.remove_column')}
                            ?disabled=${this._saving || this._columns.length <= 1}
                            @action=${() => this._removeColumn(index)}
                        ></worktracker-icon-action>
                    </div>
                </div>
                <div class="column-fields">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('board_settings_modal.column_label')}
                        .value=${column.label}
                        ?disabled=${this._saving}
                        @change=${(e) => this._onColumnLabelChange(index, e)}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('board_settings_modal.column_state')}
                        .value=${column.state}
                        .config=${this._stateConfig()}
                        ?disabled=${this._saving}
                        @change=${(e) => this._onColumnStateChange(index, e)}
                    ></platform-field>
                </div>
            </div>
        `;
    }

    async _performSave() {
        const name = this._boardName.trim();
        if (name.length === 0) {
            return;
        }
        const columns = this._columns.map((column, position) => {
            if (typeof column.board_column_id !== 'string' || column.board_column_id.length === 0) {
                throw new Error('WorktrackerBoardSettingsModal: board_column_id required');
            }
            if (typeof column.label !== 'string' || column.label.trim().length === 0) {
                throw new Error('WorktrackerBoardSettingsModal: column label required');
            }
            if (typeof column.state !== 'string' || !BOARD_COLUMN_STATES.includes(column.state)) {
                throw new Error('WorktrackerBoardSettingsModal: column state required');
            }
            return {
                board_column_id: column.board_column_id,
                label: column.label.trim(),
                state: column.state,
                position,
            };
        });
        this._saving = true;
        this._boards.update(this.boardId, { name, columns });
    }

    renderHeader() {
        return this.t('board_settings_modal.header');
    }

    renderSaveHeaderButton() {
        const hasName = this._boardName.trim().length > 0;
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._saving || this._loading || !hasName,
            title: this.t('board_settings_modal.submit'),
        });
    }

    renderBody() {
        if (this._loading) {
            return html`<div>${this.t('board_settings_modal.loading')}</div>`;
        }
        return html`
            <form class="form-grid" @submit=${(e) => { e.preventDefault(); this._performSave(); }}>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('board_settings_modal.label_name')}
                    .value=${this._boardName}
                    ?disabled=${this._saving}
                    @change=${this._onNameChange}
                ></platform-field>
                <div class="columns-section">
                    <div class="columns-head">
                        <div class="columns-title">${this.t('board_settings_modal.columns')}</div>
                        <worktracker-icon-action
                            icon="plus"
                            .title=${this.t('board_settings_modal.add_column')}
                            ?disabled=${this._saving}
                            @action=${() => this._addColumn()}
                        ></worktracker-icon-action>
                    </div>
                    ${this._columns.flatMap((column, index) => [
                        this._renderColumnInsertMarker(index),
                        this._renderColumnRow(column, index),
                    ])}
                    ${this._renderColumnInsertMarker(this._columns.length)}
                </div>
            </form>
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('board_settings_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._saving || this._loading}
                        @click=${() => this._performSave()}>
                    ${this._saving
                        ? this.t('board_settings_modal.saving')
                        : this.t('board_settings_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('worktracker-board-settings-modal', WorktrackerBoardSettingsModal);
registerModalKind(WorktrackerBoardSettingsModal.modalKind, 'worktracker-board-settings-modal');
