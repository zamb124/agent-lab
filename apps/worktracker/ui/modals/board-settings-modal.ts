/**
 * BoardSettingsModal — название доски, колонки и маппинг на статусы WorkItem.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/worktracker-icon-action.js';
import { reorderByInsertIndex } from '@platform/lib/utils/reorder-by-insert-index.js';
import type { CSSResultGroup, PropertyValues, TemplateResult } from 'lit';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import type { ResourceController } from '@platform/lib/base/use-resource.js';

function missingAsEmpty(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

function optionalZero(value: unknown): number {
    if (value === undefined || value === null) return 0;
    return Number(value);
}

function dragText(transfer: DataTransfer | null, mime: string): string {
    if (transfer === null) return '';
    return transfer.getData(mime);
}

interface BoardColumnRecord {
    board_column_id?: string;
    label?: string;
    state?: string;
    position?: number;
    [key: string]: unknown;
}

interface BoardRecord {
    board_id?: string;
    name?: string;
    columns?: BoardColumnRecord[];
    [key: string]: unknown;
}

interface BoardColumnDraft {
    board_column_id: string;
    label: string;
    state: string;
    position: number;
}

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
    declare boardId: string;
    declare _boardName: string;
    declare _columns: BoardColumnDraft[];
    declare _loading: boolean;
    declare _saving: boolean;
    declare _dragColumnIndex: number;
    declare _columnInsertIndex: number;
    private _boards: ResourceController;
    private _snapshotName: string;
    private _snapshotColumns: BoardColumnDraft[];


    static override properties = {
        boardId: { type: String },
        _boardName: { state: true },
        _columns: { state: true },
        _loading: { state: true },
        _saving: { state: true },
        _dragColumnIndex: { state: true },
        _columnInsertIndex: { state: true },
    };

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
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

    override connectedCallback() {
        super.connectedCallback();
        this.useEvent(this._boards.resource.events.ITEM_LOADED, (event: PlatformEvent) => {
            const payload = event.payload as { item?: BoardRecord } | null;
            const item = payload && payload.item;
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

    override updated(changed: PropertyValues<this>) {
        super.updated(changed);
        if (changed.has('boardId') && typeof this.boardId === 'string' && this.boardId.length > 0) {
            this._resetAndLoad();
        }
    }

    private _resetAndLoad() {
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

    private _applyBoard(board: BoardRecord) {
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
            .sort((left, right) => optionalZero(left.position) - optionalZero(right.position))
            .map((column) => ({
                board_column_id: missingAsEmpty(column.board_column_id),
                label: missingAsEmpty(column.label),
                state: missingAsEmpty(column.state),
                position: optionalZero(column.position),
            }));
        this._snapshotColumns = this._columns.map((column) => ({ ...column }));
        this._loading = false;
    }

    override willUpdate(changed: PropertyValues<this>) {
        super.willUpdate(changed);
        const nameChanged = this._boardName !== this._snapshotName;
        const columnsChanged = JSON.stringify(this._columns) !== JSON.stringify(this._snapshotColumns);
        this.isDirty = nameChanged || columnsChanged;
    }

    private _stateConfig() {
        return {
            values: BOARD_COLUMN_STATES.map((state) => ({
                value: state,
                label: this.t(`state.${state}`),
            })),
        };
    }

    private _onNameChange(event: CustomEvent<{ value?: unknown }>) {
        const value = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._boardName = value;
    }

    private _onColumnLabelChange(index: number, event: CustomEvent<{ value?: unknown }>) {
        const value = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._columns = this._columns.map((column, i) => (
            i === index ? { ...column, label: value } : column
        ));
    }

    private _onColumnStateChange(index: number, event: CustomEvent<{ value?: unknown }>) {
        const value = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        if (!(BOARD_COLUMN_STATES as readonly string[]).includes(value)) {
            throw new Error(`WorktrackerBoardSettingsModal: unsupported state ${value}`);
        }
        this._columns = this._columns.map((column, i) => (
            i === index ? { ...column, state: value } : column
        ));
    }

    private _nextColumnId() {
        let index = this._columns.length;
        let boardColumnId = `col_${index}`;
        while (this._columns.some((column) => column.board_column_id === boardColumnId)) {
            index += 1;
            boardColumnId = `col_${index}`;
        }
        return boardColumnId;
    }

    private _addColumn() {
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

    private _removeColumn(index: number) {
        if (this._columns.length <= 1) {
            return;
        }
        this._columns = this._columns
            .filter((_, i) => i !== index)
            .map((column, position) => ({ ...column, position }));
    }

    private _moveColumnToInsert(fromIndex: number, insertIndex: number) {
        this._columns = reorderByInsertIndex(this._columns, fromIndex, insertIndex)
            .map((column, position) => ({ ...column, position }));
    }

    private _onColumnRowDragStart(event: DragEvent, index: number) {
        event.stopPropagation();
        event.dataTransfer?.setData(BOARD_COLUMN_INDEX_MIME, String(index));
        if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
        this._dragColumnIndex = index;
    }

    private _onColumnRowDragEnd() {
        this._dragColumnIndex = -1;
        this._columnInsertIndex = -1;
    }

    private _onColumnInsertDragOver(event: DragEvent, insertIndex: number) {
        if (!event.dataTransfer || !event.dataTransfer.types.includes(BOARD_COLUMN_INDEX_MIME)) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = 'move';
        if (this._columnInsertIndex !== insertIndex) {
            this._columnInsertIndex = insertIndex;
        }
    }

    private _onColumnInsertDrop(event: DragEvent, insertIndex: number) {
        event.preventDefault();
        event.stopPropagation();
        this._columnInsertIndex = -1;
        this._dragColumnIndex = -1;
        const rawIndex = dragText(event.dataTransfer, BOARD_COLUMN_INDEX_MIME);
        if (typeof rawIndex !== 'string' || rawIndex.length === 0) {
            return;
        }
        const sourceIndex = Number(rawIndex);
        if (Number.isNaN(sourceIndex)) {
            throw new Error('WorktrackerBoardSettingsModal: invalid column drag index');
        }
        this._moveColumnToInsert(sourceIndex, insertIndex);
    }

    private _resolveRowInsertIndexFromPointer(event: DragEvent, rowIndex: number) {
        const target = event.currentTarget;
        if (!(target instanceof HTMLElement)) {
            return rowIndex;
        }
        const rect = target.getBoundingClientRect();
        const insertBefore = event.clientY < rect.top + rect.height / 2;
        return insertBefore ? rowIndex : rowIndex + 1;
    }

    private _onColumnRowLeadDragOver(event: DragEvent, rowIndex: number) {
        if (!event.dataTransfer || !event.dataTransfer.types.includes(BOARD_COLUMN_INDEX_MIME)) {
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

    private _onColumnRowLeadDrop(event: DragEvent, rowIndex: number) {
        if (!event.dataTransfer || !event.dataTransfer.types.includes(BOARD_COLUMN_INDEX_MIME)) {
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

    private _renderColumnInsertMarker(index: number) {
        const columnReorderActive = this._dragColumnIndex >= 0;
        const active = columnReorderActive && this._columnInsertIndex === index;
        return html`
            <div
                class="row-insert ${active ? 'active' : ''}"
                @dragover=${(event: DragEvent) => this._onColumnInsertDragOver(event, index)}
                @drop=${(event: DragEvent) => this._onColumnInsertDrop(event, index)}
            ></div>
        `;
    }

    private _renderColumnRow(column: BoardColumnDraft, index: number) {
        return html`
            <div class="column-row ${this._dragColumnIndex === index ? 'row-dragging' : ''}">
                <div class="column-row-head">
                    <div
                        class="column-row-lead"
                        draggable="true"
                        title=${this.t('board_settings_modal.reorder_column')}
                        @dragstart=${(event: DragEvent) => this._onColumnRowDragStart(event, index)}
                        @dragend=${() => this._onColumnRowDragEnd()}
                        @dragover=${(event: DragEvent) => this._onColumnRowLeadDragOver(event, index)}
                        @drop=${(event: DragEvent) => this._onColumnRowLeadDrop(event, index)}
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
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._onColumnLabelChange(index, e)}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('board_settings_modal.column_state')}
                        .value=${column.state}
                        .config=${this._stateConfig()}
                        ?disabled=${this._saving}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._onColumnStateChange(index, e)}
                    ></platform-field>
                </div>
            </div>
        `;
    }

    override async _performSave(): Promise<void> {
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
            if (typeof column.state !== 'string' || !(BOARD_COLUMN_STATES as readonly string[]).includes(column.state)) {
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

    override renderHeader() {
        return this.t('board_settings_modal.header');
    }

    override renderSaveHeaderButton() {
        const hasName = this._boardName.trim().length > 0;
        return this._renderHeaderSaveIcon({
            onClick: () => void this._performSave(),
            disabled: this._saving || this._loading || !hasName,
            title: this.t('board_settings_modal.submit'),
        });
    }

    override renderBody() {
        if (this._loading) {
            return html`<div><glass-spinner></glass-spinner></div>`;
        }
        return html`
            <form class="form-grid" @submit=${(e: SubmitEvent) => { e.preventDefault(); void this._performSave(); }}>
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

    override renderFooter(): TemplateResult {
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => void this.close()}>
                    ${this.t('board_settings_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._saving || this._loading}
                        @click=${() => void this._performSave()}>
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
