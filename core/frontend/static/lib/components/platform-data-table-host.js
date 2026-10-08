/**
 * platform-data-table-host — native Lit grid for FileCategory.DATA_TABLE (.sqlite).
 * Rows come from office paging API; SQLite is never loaded in the browser.
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { httpRequest } from '../events/http.js';
import { hasPlatformBus } from '../events/bus-singleton.js';
import './fields/platform-field.js';
import './platform-button.js';
import './platform-icon.js';

const COLUMN_TYPES = ['text', 'integer', 'real', 'boolean', 'datetime', 'json', 'file_ref'];
const DEFAULT_PAGE_SIZE = 50;

function handlerPayload(openConfig) {
    if (!openConfig || typeof openConfig !== 'object') {
        throw new Error('platform-data-table-host: openConfig required');
    }
    if (openConfig.handler !== 'data_table') {
        throw new Error('platform-data-table-host: handler must be data_table');
    }
    const payload = openConfig.data_table;
    if (!payload || typeof payload !== 'object') {
        throw new Error('platform-data-table-host: data_table payload required');
    }
    return payload;
}

function requireUrl(value, label) {
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`platform-data-table-host: ${label} required`);
    }
    return value;
}

export class PlatformDataTableHost extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        openConfig: { type: Object, attribute: false },
        fileId: { type: String, attribute: 'file-id' },
        tableName: { type: String, attribute: 'table-name' },
        viewMode: { type: String, attribute: 'view-mode' },
        pageSize: { type: Number, attribute: 'page-size' },
        interaction: { type: String },
        chrome: { type: Object, attribute: false },
        suspended: { type: Boolean, reflect: true },
        _schema: { state: true },
        _rows: { state: true },
        _nextCursor: { state: true },
        _hasMore: { state: true },
        _loading: { state: true },
        _error: { state: true },
        _columnFilters: { state: true },
        _draftColumnName: { state: true },
        _draftColumnType: { state: true },
        _draftTableName: { state: true },
        _showAddColumn: { state: true },
        _showAddTable: { state: true },
        _editing: { state: true },
        _formError: { state: true },
        _deletingRowId: { state: true },
        _exporting: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-width: 0;
                min-height: 0;
                width: 100%;
                height: 100%;
                background: var(--bg-primary);
                color: var(--text-primary);
            }
            .status, .error {
                padding: var(--space-4);
                font-size: var(--text-sm);
            }
            .error { color: var(--color-danger, var(--error)); }
            .toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                justify-content: space-between;
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                background: var(--bg-secondary, var(--glass-solid-medium));
                min-width: 0;
            }
            .toolbar-start, .toolbar-end, .toolbar-group {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                min-width: 0;
            }
            .toolbar-end {
                margin-left: auto;
            }
            .table-tab {
                border-bottom: 2px solid transparent;
                border-radius: var(--radius-sm, 6px);
            }
            .table-tab.is-active {
                border-bottom-color: var(--accent);
            }
            .toolbar-sep {
                width: 1px;
                height: 1.25rem;
                background: var(--border-subtle);
                flex: 0 0 1px;
            }
            .form-error.banner {
                margin: 0;
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--error-border, var(--border-subtle));
                background: var(--error-bg, transparent);
                color: var(--color-danger, var(--error));
                font-size: var(--text-sm);
            }
            .grid-wrap {
                flex: 1;
                min-height: 0;
                overflow: auto;
                background: var(--bg-primary);
            }
            table {
                width: 100%;
                border-collapse: separate;
                border-spacing: 0;
                font-size: var(--text-sm);
                table-layout: auto;
            }
            th, td {
                border-bottom: 1px solid var(--border-subtle);
                border-right: 1px solid var(--border-subtle);
                padding: 0.4rem 0.65rem;
                text-align: left;
                vertical-align: middle;
                min-width: 8rem;
            }
            th:last-child, td:last-child {
                border-right: none;
            }
            th {
                position: sticky;
                top: 0;
                background: var(--bg-elevated, var(--bg-secondary, var(--glass-solid-medium)));
                z-index: 1;
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                box-shadow: 0 1px 0 var(--border-subtle);
            }
            tbody tr:nth-child(even) td {
                background: var(--bg-secondary, var(--glass-solid-medium));
            }
            tbody tr:hover td {
                background: var(--bg-hover, var(--glass-solid-strong, var(--bg-secondary)));
            }
            th.sys, td.sys {
                color: var(--text-tertiary, var(--text-secondary));
                font-variant-numeric: tabular-nums;
                min-width: 4.5rem;
                width: 4.5rem;
            }
            th.row-actions, td.row-actions {
                min-width: 2.75rem;
                width: 2.75rem;
                padding: 0.15rem;
                text-align: center;
                position: sticky;
                right: 0;
                background: inherit;
                z-index: 1;
            }
            th.row-actions {
                background: var(--bg-elevated, var(--bg-secondary, var(--glass-solid-medium)));
                z-index: 2;
            }
            .col-head {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                min-width: 0;
            }
            .col-title {
                font-weight: var(--font-semibold);
            }
            .col-filter {
                width: 100%;
                box-sizing: border-box;
                min-width: 0;
                padding: 0.2rem 0.45rem;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm, 6px);
                background: var(--bg-primary);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-xs);
            }
            td.cell-editable {
                cursor: cell;
                min-height: 2rem;
            }
            td.cell-editable:hover {
                outline: 1px solid var(--accent);
                outline-offset: -1px;
            }
            td.cell-editing {
                padding: 0;
                cursor: text;
            }
            td.cell-editing input {
                width: 100%;
                box-sizing: border-box;
                border: 2px solid var(--accent);
                background: var(--bg-primary);
                color: var(--text-primary);
                font: inherit;
                padding: 0.35rem 0.5rem;
                outline: none;
            }
            .cell-placeholder {
                color: var(--text-tertiary, var(--text-secondary));
                font-size: var(--text-xs);
            }
            .schema-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4);
            }
            .schema-card {
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-3);
                background: var(--glass-solid-medium);
            }
            .add-form {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                align-items: end;
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
            }
            .pager {
                display: flex;
                justify-content: flex-end;
                padding: var(--space-3) var(--space-4);
                border-top: 1px solid var(--border-subtle);
            }
        `,
    ];

    constructor() {
        super();
        this.openConfig = null;
        this.fileId = '';
        this.tableName = '';
        this.viewMode = 'data';
        this.pageSize = DEFAULT_PAGE_SIZE;
        this.interaction = 'edit';
        this.chrome = null;
        this.suspended = false;
        this._schema = null;
        this._rows = [];
        this._nextCursor = null;
        this._hasMore = false;
        this._loading = false;
        this._error = '';
        this._columnFilters = {};
        this._draftColumnName = '';
        this._draftColumnType = 'text';
        this._draftTableName = '';
        this._showAddColumn = false;
        this._showAddTable = false;
        this._editing = null;
        this._formError = '';
        this._deletingRowId = null;
        this._exporting = '';
        this._rowsBaseUrl = '';
        this._mutateBaseUrl = '';
        this._bootstrappedFileId = '';
        this._filterTimer = null;
        this._ignoreBlurCommit = false;
        this._editDraft = '';
    }

    disconnectedCallback() {
        if (this._filterTimer !== null) {
            window.clearTimeout(this._filterTimer);
            this._filterTimer = null;
        }
        super.disconnectedCallback();
    }

    _isView() {
        return this.interaction === 'view';
    }

    _text(key, vars) {
        if (hasPlatformBus()) {
            return this.t(key === 'loading' ? 'file_viewer.loading' : `file_viewer.${key}`, vars);
        }
        const chrome = this.chrome;
        if (!chrome || typeof chrome !== 'object') {
            throw new Error('platform-data-table-host: chrome required without bus');
        }
        const template = chrome[key];
        if (typeof template !== 'string' || template.length === 0) {
            throw new Error(`platform-data-table-host: chrome.${key} required`);
        }
        if (!vars) {
            return template;
        }
        return template.replace(/\{(\w+)\}/g, (match, name) => {
            if (!Object.prototype.hasOwnProperty.call(vars, name)) {
                throw new Error(`platform-data-table-host: chrome.${key} missing ${name}`);
            }
            return String(vars[name]);
        });
    }

    updated(changed) {
        super.updated(changed);
        if (this.suspended) {
            return;
        }
        if (changed.has('openConfig') && this.openConfig) {
            this._bootstrapFromPayload();
        } else if (
            (changed.has('fileId') || changed.has('openConfig'))
            && !this.openConfig
            && typeof this.fileId === 'string'
            && this.fileId.trim().length > 0
            && this._bootstrappedFileId !== this.fileId.trim()
        ) {
            void this._bootstrapFromFileId();
        }
        if (
            (
                changed.has('tableName')
                || changed.has('pageSize')
                || changed.has('viewMode')
            )
            && this._schema
            && this.viewMode === 'data'
        ) {
            void this._reloadRows();
        }
        if (changed.has('_editing') && this._editing) {
            const previous = changed.get('_editing');
            const sameCell = Boolean(
                previous
                && previous.rowId === this._editing.rowId
                && previous.column === this._editing.column,
            );
            if (!sameCell) {
                const input = this.renderRoot.querySelector('td.cell-editing input');
                if (input instanceof HTMLInputElement) {
                    input.focus();
                    if (this._editing.selectAll) {
                        input.select();
                    } else {
                        const end = input.value.length;
                        input.setSelectionRange(end, end);
                    }
                }
            }
            this._ignoreBlurCommit = false;
        }
    }

    _applySchema(snapshot) {
        if (!snapshot || typeof snapshot !== 'object') {
            throw new Error('platform-data-table-host: schema_snapshot required');
        }
        this._schema = snapshot;
        this._error = '';
        if (this.tableName.length === 0) {
            const first = Array.isArray(snapshot.tables) ? snapshot.tables[0] : null;
            if (first && typeof first.name === 'string' && first.name.length > 0) {
                this.tableName = first.name;
            }
        }
        this.emit('data-table-schema', { schema: snapshot, tableName: this.tableName });
        if (this.viewMode === 'data') {
            void this._reloadRows();
        }
    }

    _bootstrapFromPayload() {
        const payload = handlerPayload(this.openConfig);
        this._rowsBaseUrl = requireUrl(payload.rows_url, 'rows_url');
        this._mutateBaseUrl = requireUrl(payload.mutate_url, 'mutate_url');
        this._applySchema(payload.schema_snapshot);
    }

    async _bootstrapFromFileId() {
        const fileId = this.fileId.trim();
        this._bootstrappedFileId = fileId;
        this._loading = true;
        this._error = '';
        try {
            const snapshot = await this._fetchJson(
                `/documents/api/v1/data-tables/${encodeURIComponent(fileId)}`,
            );
            if (!snapshot || typeof snapshot !== 'object' || !snapshot.schema_snapshot) {
                throw new Error('platform-data-table-host: snapshot.schema_snapshot required');
            }
            this._rowsBaseUrl = `/documents/api/v1/data-tables/${fileId}/tables`;
            this._mutateBaseUrl = `/documents/api/v1/data-tables/${fileId}`;
            this._applySchema(snapshot.schema_snapshot);
        } catch (exc) {
            this._error = exc instanceof Error ? exc.message : String(exc);
            this.emit('editor-error', { message: this._error });
        } finally {
            this._loading = false;
        }
    }

    _mutateUrl() {
        if (this._mutateBaseUrl.length > 0) {
            return this._mutateBaseUrl;
        }
        return requireUrl(handlerPayload(this.openConfig).mutate_url, 'mutate_url');
    }

    _rowsUrl() {
        if (this._rowsBaseUrl.length > 0) {
            return this._rowsBaseUrl;
        }
        return requireUrl(handlerPayload(this.openConfig).rows_url, 'rows_url');
    }

    _pageQuery(extra) {
        const limit = Number.isInteger(this.pageSize) && this.pageSize > 0
            ? Math.min(this.pageSize, 200)
            : DEFAULT_PAGE_SIZE;
        const params = [`limit=${limit}`];
        const table = this._activeTable();
        if (table) {
            for (const column of table.columns) {
                const query = this._columnFilters[column.name];
                if (typeof query === 'string' && query.trim().length > 0) {
                    params.push(`column_q=${encodeURIComponent(`${column.name}:${query.trim()}`)}`);
                }
            }
        }
        if (extra) {
            params.push(extra);
        }
        return params.join('&');
    }

    async _fetchJson(url, options) {
        const method = options && typeof options.method === 'string' ? options.method : 'GET';
        const request = { method, url };
        if (options && Object.prototype.hasOwnProperty.call(options, 'body')) {
            request.body = options.body;
        }
        return httpRequest(request);
    }

    async refreshSchema() {
        const snapshot = await this._fetchJson(this._mutateUrl());
        if (!snapshot || typeof snapshot !== 'object' || !snapshot.schema_snapshot) {
            throw new Error('platform-data-table-host: snapshot.schema_snapshot required');
        }
        this._schema = snapshot.schema_snapshot;
        this.emit('data-table-schema', { schema: this._schema, tableName: this.tableName });
        this.emit('document-state', { dirty: false });
    }

    async _reloadRows() {
        if (!this.tableName) {
            this._rows = [];
            this._hasMore = false;
            this._nextCursor = null;
            return;
        }
        this._loading = true;
        this._error = '';
        try {
            const url = `${this._rowsUrl()}/${encodeURIComponent(this.tableName)}/rows?${this._pageQuery()}`;
            const page = await this._fetchJson(url);
            if (!page || !Array.isArray(page.items)) {
                throw new Error('platform-data-table-host: rows page.items required');
            }
            this._rows = page.items;
            this._nextCursor = typeof page.next_cursor === 'string' ? page.next_cursor : null;
            this._hasMore = page.has_more === true;
        } catch (exc) {
            this._error = exc instanceof Error ? exc.message : String(exc);
            this.emit('editor-error', { message: this._error });
        } finally {
            this._loading = false;
        }
    }

    async loadMore() {
        if (!this._hasMore || this._nextCursor === null || !this.tableName) {
            return;
        }
        this._loading = true;
        try {
            const extra = `cursor=${encodeURIComponent(this._nextCursor)}`;
            const url = `${this._rowsUrl()}/${encodeURIComponent(this.tableName)}/rows?${this._pageQuery(extra)}`;
            const page = await this._fetchJson(url);
            if (!page || !Array.isArray(page.items)) {
                throw new Error('platform-data-table-host: rows page.items required');
            }
            this._rows = [...this._rows, ...page.items];
            this._nextCursor = typeof page.next_cursor === 'string' ? page.next_cursor : null;
            this._hasMore = page.has_more === true;
        } catch (exc) {
            this._error = exc instanceof Error ? exc.message : String(exc);
            this.emit('editor-error', { message: this._error });
        } finally {
            this._loading = false;
        }
    }

    async addRow() {
        if (this._isView()) {
            return;
        }
        if (!this.tableName) {
            this._showAddTable = true;
            return;
        }
        try {
            await this._fetchJson(
                `${this._mutateUrl()}/tables/${encodeURIComponent(this.tableName)}/rows`,
                {
                    method: 'POST',
                    body: { rows: [{}] },
                },
            );
            await this.refreshSchema();
            await this._reloadRows();
        } catch (exc) {
            this._formError = exc instanceof Error ? exc.message : String(exc);
        }
    }

    async deleteRow(rowId) {
        if (this._isView()) {
            return;
        }
        if (!this.tableName) {
            this._formError = this._text('data_table_table_required');
            return;
        }
        const { platformConfirm } = await import('./platform-confirm-modal.js');
        const confirmed = await platformConfirm(
            this._text('data_table_delete_row_confirm', { row_id: rowId }),
            {
                title: this._text('data_table_delete_row'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this._text('data_table_delete_row'),
            },
        );
        if (!confirmed) {
            return;
        }
        this._deletingRowId = rowId;
        this._formError = '';
        try {
            await this._fetchJson(
                `${this._mutateUrl()}/tables/${encodeURIComponent(this.tableName)}/rows/delete`,
                {
                    method: 'POST',
                    body: { row_ids: [rowId] },
                },
            );
            await this.refreshSchema();
            await this._reloadRows();
        } catch (exc) {
            this._formError = exc instanceof Error ? exc.message : String(exc);
        } finally {
            this._deletingRowId = null;
        }
    }

    _exportUrl(sourceFormat) {
        if (!this.tableName) {
            throw new Error('platform-data-table-host: table name required for export');
        }
        return `${this._rowsUrl()}/${encodeURIComponent(this.tableName)}/export?source_format=${sourceFormat}`;
    }

    async _exportTable(sourceFormat) {
        if (sourceFormat !== 'csv' && sourceFormat !== 'xlsx') {
            throw new Error(`platform-data-table-host: invalid export format ${sourceFormat}`);
        }
        if (!this.tableName) {
            this._formError = this._text('data_table_table_required');
            return;
        }
        this._exporting = sourceFormat;
        try {
            const exported = await this._fetchJson(this._exportUrl(sourceFormat));
            if (!exported || typeof exported.download_url !== 'string' || exported.download_url.length === 0) {
                throw new Error('platform-data-table-host: export must return FileRecord.download_url');
            }
            const link = document.createElement('a');
            link.href = exported.download_url;
            link.download = `${this.tableName}.${sourceFormat}`;
            link.rel = 'noopener';
            document.body.appendChild(link);
            link.click();
            link.remove();
        } catch (error) {
            this._formError = error instanceof Error ? error.message : String(error);
        } finally {
            this._exporting = '';
        }
    }

    _columnSpec(columnName) {
        const table = this._activeTable();
        if (!table) {
            return null;
        }
        const found = table.columns.find((column) => column.name === columnName);
        return found || null;
    }

    _sameCellValue(left, right) {
        if (left === right) {
            return true;
        }
        if (left === null && right === undefined) {
            return true;
        }
        if (left === undefined && right === null) {
            return true;
        }
        return JSON.stringify(left) === JSON.stringify(right);
    }

    _coercePatchValue(column, rawValue) {
        const columnType = column.column_type;
        const invalid = () => new Error(
            this._text('data_table_cell_invalid', {
                column: column.name,
                column_type: columnType,
            }),
        );
        if (rawValue === null || rawValue === undefined) {
            if (column.not_null) {
                throw invalid();
            }
            return null;
        }
        const asString = typeof rawValue === 'string' ? rawValue : String(rawValue);
        const trimmed = asString.trim();
        if (trimmed.length === 0) {
            if (column.not_null) {
                throw invalid();
            }
            return null;
        }
        if (columnType === 'text') {
            return asString;
        }
        if (columnType === 'integer') {
            const negative = trimmed.startsWith('-');
            const digits = negative ? trimmed.slice(1) : trimmed;
            if (digits.length === 0 || !/^\d+$/.test(digits)) {
                throw invalid();
            }
            return Number.parseInt(trimmed, 10);
        }
        if (columnType === 'real') {
            const parsed = Number(trimmed);
            if (!Number.isFinite(parsed)) {
                throw invalid();
            }
            return parsed;
        }
        if (columnType === 'boolean') {
            const token = trimmed.toLowerCase();
            if (token === 'true' || token === '1' || token === 'yes') {
                return true;
            }
            if (token === 'false' || token === '0' || token === 'no') {
                return false;
            }
            throw invalid();
        }
        if (columnType === 'datetime') {
            const parsed = Date.parse(trimmed);
            if (Number.isNaN(parsed)) {
                throw invalid();
            }
            return trimmed;
        }
        if (columnType === 'json') {
            try {
                return JSON.parse(trimmed);
            } catch {
                throw invalid();
            }
        }
        if (columnType === 'file_ref') {
            return trimmed;
        }
        throw invalid();
    }

    async _patchCell(rowId, columnName, rawValue) {
        if (this._isView()) {
            return;
        }
        const column = this._columnSpec(columnName);
        if (!column) {
            this._formError = this._text('data_table_cell_invalid', {
                column: columnName,
                column_type: 'unknown',
            });
            return;
        }
        let typed;
        try {
            typed = this._coercePatchValue(column, rawValue);
        } catch (exc) {
            this._formError = exc instanceof Error ? exc.message : String(exc);
            return;
        }
        const currentRow = this._rows.find((row) => row.row_id === rowId);
        const current = currentRow && currentRow.values ? currentRow.values[columnName] : null;
        if (this._sameCellValue(current, typed)) {
            return;
        }
        this._formError = '';
        this._rows = this._rows.map((row) => {
            if (row.row_id !== rowId) {
                return row;
            }
            return { ...row, values: { ...row.values, [columnName]: typed } };
        });
        try {
            await this._fetchJson(
                `${this._mutateUrl()}/tables/${encodeURIComponent(this.tableName)}/rows/${rowId}`,
                {
                    method: 'PATCH',
                    body: { values: { [columnName]: typed } },
                },
            );
        } catch (exc) {
            this._formError = exc instanceof Error ? exc.message : String(exc);
            await this._reloadRows();
        }
    }

    showAddColumn() {
        if (this._isView()) {
            return;
        }
        this._showAddColumn = true;
        this._showAddTable = false;
        this._formError = '';
    }

    showAddTable() {
        if (this._isView()) {
            return;
        }
        this._showAddTable = true;
        this._showAddColumn = false;
        this._formError = '';
    }

    async _submitAddColumn() {
        const name = this._draftColumnName.trim();
        if (!name) {
            this._formError = this._text('data_table_column_name_required');
            return;
        }
        if (!this.tableName) {
            this._formError = this._text('data_table_table_required');
            return;
        }
        this._formError = '';
        this._loading = true;
        try {
            await this._fetchJson(
                `${this._mutateUrl()}/tables/${encodeURIComponent(this.tableName)}/columns`,
                {
                    method: 'POST',
                    body: {
                        name,
                        column_type: this._draftColumnType,
                        not_null: false,
                    },
                },
            );
            this._draftColumnName = '';
            this._showAddColumn = false;
            await this.refreshSchema();
            await this._reloadRows();
        } catch (exc) {
            this._formError = exc instanceof Error ? exc.message : String(exc);
        } finally {
            this._loading = false;
        }
    }

    async _submitAddTable() {
        const name = this._draftTableName.trim();
        if (!name) {
            this._formError = this._text('data_table_table_name_required');
            return;
        }
        this._formError = '';
        this._loading = true;
        try {
            await this._fetchJson(`${this._mutateUrl()}/tables`, {
                method: 'POST',
                body: {
                    name,
                    columns: [{ name: 'value', column_type: 'text', not_null: false }],
                },
            });
            this._draftTableName = '';
            this._showAddTable = false;
            this.tableName = name;
            await this.refreshSchema();
            await this._reloadRows();
        } catch (exc) {
            this._formError = exc instanceof Error ? exc.message : String(exc);
        } finally {
            this._loading = false;
        }
    }

    _activeTable() {
        const schema = this._schema;
        if (!schema || !Array.isArray(schema.tables)) {
            return null;
        }
        const found = schema.tables.find((table) => table.name === this.tableName);
        if (!found) {
            return null;
        }
        return found;
    }

    _setTable(name) {
        if (typeof name !== 'string' || name.length === 0) {
            throw new Error('platform-data-table-host: table name required');
        }
        if (this.tableName === name) {
            return;
        }
        this.tableName = name;
        this._columnFilters = {};
        this._editing = null;
        this.emit('data-table-schema', { schema: this._schema, tableName: name });
    }

    _setViewMode(mode) {
        if (mode !== 'data' && mode !== 'schema') {
            throw new Error(`platform-data-table-host: invalid viewMode ${mode}`);
        }
        this.viewMode = mode;
        this._editing = null;
    }

    _setPageSize(size) {
        if (size !== 50 && size !== 100) {
            throw new Error(`platform-data-table-host: invalid pageSize ${size}`);
        }
        this.pageSize = size;
    }

    _filterValue(columnName) {
        const value = this._columnFilters[columnName];
        return typeof value === 'string' ? value : '';
    }

    _onColumnFilterInput(columnName, value) {
        this._columnFilters = { ...this._columnFilters, [columnName]: value };
        if (this._filterTimer !== null) {
            window.clearTimeout(this._filterTimer);
        }
        this._filterTimer = window.setTimeout(() => {
            this._filterTimer = null;
            void this._reloadRows();
        }, 250);
    }

    _beginEdit(rowId, columnName, options) {
        if (this._isView()) {
            return;
        }
        const current = this._editing;
        if (current && current.rowId === rowId && current.column === columnName) {
            return;
        }
        if (current) {
            const open = this.renderRoot.querySelector('td.cell-editing input');
            const previousValue = open instanceof HTMLInputElement ? open.value : this._editDraft;
            this._ignoreBlurCommit = true;
            void this._patchCell(current.rowId, current.column, previousValue);
        }
        const row = this._rows.find((item) => item.row_id === rowId);
        const display = row ? String(this._cellValue(row, columnName)) : '';
        const draft = options && Object.prototype.hasOwnProperty.call(options, 'draft')
            ? options.draft
            : display;
        this._editDraft = draft;
        this._editing = {
            rowId,
            column: columnName,
            draft,
            selectAll: Boolean(options && options.selectAll),
        };
    }

    _commitEdit(rawValue) {
        const editing = this._editing;
        if (!editing) {
            return;
        }
        this._ignoreBlurCommit = true;
        this._editing = null;
        this._editDraft = '';
        void this._patchCell(editing.rowId, editing.column, rawValue);
    }

    _cancelEdit() {
        this._ignoreBlurCommit = true;
        this._editing = null;
        this._editDraft = '';
    }

    _onEditInput(event) {
        if (!(event.target instanceof HTMLInputElement)) {
            return;
        }
        this._editDraft = event.target.value;
    }

    _onEditKeydown(event) {
        if (!(event.target instanceof HTMLInputElement)) {
            return;
        }
        if (event.key === 'Enter') {
            event.preventDefault();
            this._commitEdit(event.target.value);
            return;
        }
        if (event.key === 'Tab') {
            event.preventDefault();
            const editing = this._editing;
            const value = event.target.value;
            this._commitEdit(value);
            if (!editing) {
                return;
            }
            const next = this._neighborColumn(editing.column, event.shiftKey ? -1 : 1);
            if (next) {
                this._beginEdit(editing.rowId, next, { selectAll: true });
            }
            return;
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            this._cancelEdit();
        }
    }

    _onEditBlur(event) {
        if (this._ignoreBlurCommit) {
            this._ignoreBlurCommit = false;
            return;
        }
        if (!(event.target instanceof HTMLInputElement)) {
            return;
        }
        void this._commitEdit(event.target.value);
    }

    _neighborColumn(columnName, delta) {
        const table = this._activeTable();
        if (!table) {
            return null;
        }
        const names = table.columns.map((column) => column.name);
        const index = names.indexOf(columnName);
        if (index < 0) {
            return null;
        }
        const next = index + delta;
        if (next < 0 || next >= names.length) {
            return null;
        }
        return names[next];
    }

    _onCellKeydown(event, rowId, columnName) {
        if (event.ctrlKey || event.metaKey || event.altKey) {
            return;
        }
        if (event.key === 'Enter' || event.key === 'F2') {
            event.preventDefault();
            this._beginEdit(rowId, columnName, { selectAll: true });
            return;
        }
        if (event.key.length === 1) {
            event.preventDefault();
            this._beginEdit(rowId, columnName, { draft: event.key, selectAll: false });
        }
    }

    _onGridScroll(event) {
        if (this._isView()) {
            return;
        }
        const target = event.currentTarget;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        const remaining = target.scrollHeight - target.scrollTop - target.clientHeight;
        if (remaining < 80 && this._hasMore && !this._loading) {
            void this.loadMore();
        }
    }

    _renderToolbar() {
        const schema = this._schema;
        const tables = schema && Array.isArray(schema.tables) ? schema.tables : [];
        const editable = !this._isView();
        const canExport = this.tableName.length > 0;
        return html`
            <div class="toolbar">
                <div class="toolbar-start">
                    ${tables.map((table) => html`
                        <platform-button
                            class="table-tab ${this.tableName === table.name ? 'is-active' : ''}"
                            density="dense"
                            variant="ghost"
                            aria-label=${table.name}
                            aria-pressed=${this.tableName === table.name ? 'true' : 'false'}
                            @click=${() => this._setTable(table.name)}
                        >${table.name}</platform-button>
                    `)}
                    ${editable ? html`
                        <span class="toolbar-sep" aria-hidden="true"></span>
                        <platform-button
                            icon-only
                            density="dense"
                            variant="ghost"
                            class=${this.viewMode === 'data' ? 'table-tab is-active' : 'table-tab'}
                            aria-label=${this._text('data_table_view_data')}
                            title=${this._text('data_table_view_data')}
                            @click=${() => this._setViewMode('data')}
                        >
                            <platform-icon name="list" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            icon-only
                            density="dense"
                            variant="ghost"
                            class=${this.viewMode === 'schema' ? 'table-tab is-active' : 'table-tab'}
                            aria-label=${this._text('data_table_view_schema')}
                            title=${this._text('data_table_view_schema')}
                            @click=${() => this._setViewMode('schema')}
                        >
                            <platform-icon name="adjustment" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            density="dense"
                            variant="ghost"
                            class=${this.pageSize === 50 ? 'table-tab is-active' : 'table-tab'}
                            aria-label=${this._text('data_table_page_size')}
                            @click=${() => this._setPageSize(50)}
                        >50</platform-button>
                        <platform-button
                            density="dense"
                            variant="ghost"
                            class=${this.pageSize === 100 ? 'table-tab is-active' : 'table-tab'}
                            aria-label=${this._text('data_table_page_size')}
                            @click=${() => this._setPageSize(100)}
                        >100</platform-button>
                    ` : nothing}
                </div>
                <div class="toolbar-end">
                    ${editable ? html`
                        <platform-button
                            icon-only
                            density="dense"
                            variant="ghost"
                            aria-label=${this._text('data_table_add_table')}
                            title=${this._text('data_table_add_table')}
                            @click=${() => this.showAddTable()}
                        >
                            <platform-icon name="table" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            icon-only
                            density="dense"
                            variant="ghost"
                            aria-label=${this._text('data_table_add_column')}
                            title=${this._text('data_table_add_column')}
                            ?disabled=${this.tableName.length === 0}
                            @click=${() => this.showAddColumn()}
                        >
                            <platform-icon name="layers" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            icon-only
                            density="dense"
                            variant="ghost"
                            aria-label=${this._text('data_table_add_row')}
                            title=${this._text('data_table_add_row')}
                            ?disabled=${this.tableName.length === 0}
                            @click=${() => { void this.addRow(); }}
                        >
                            <platform-icon name="plus" size="16"></platform-icon>
                        </platform-button>
                        <span class="toolbar-sep" aria-hidden="true"></span>
                    ` : nothing}
                    <platform-button
                        icon-only
                        density="dense"
                        variant="ghost"
                        aria-label=${this._text('data_table_export_csv')}
                        title=${this._text('data_table_export_csv')}
                        ?disabled=${!canExport || this._exporting.length > 0}
                        @click=${() => this._exportTable('csv')}
                    >
                        <platform-icon file-icon name="csv" size="16"></platform-icon>
                    </platform-button>
                    <platform-button
                        icon-only
                        density="dense"
                        variant="ghost"
                        aria-label=${this._text('data_table_export_xlsx')}
                        title=${this._text('data_table_export_xlsx')}
                        ?disabled=${!canExport || this._exporting.length > 0}
                        @click=${() => this._exportTable('xlsx')}
                    >
                        <platform-icon file-icon name="xlsx" size="16"></platform-icon>
                    </platform-button>
                </div>
            </div>
        `;
    }

    _renderAddForms() {
        if (this._isView() || (!this._showAddColumn && !this._showAddTable)) {
            return nothing;
        }
        return html`
            <div class="add-form">
                ${this._showAddTable ? html`
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this._text('data_table_table_name')}
                        .placeholder=${this._text('data_table_table_name_placeholder')}
                        .value=${this._draftTableName}
                        @change=${(e) => { this._draftTableName = e.detail.value; }}
                    ></platform-field>
                    <platform-button
                        ?disabled=${this._loading || this._draftTableName.trim().length === 0}
                        @click=${() => { void this._submitAddTable(); }}
                    >
                        ${this._text('data_table_create_submit')}
                    </platform-button>
                ` : nothing}
                ${this._showAddColumn ? html`
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this._text('data_table_column_name')}
                        .placeholder=${this._text('data_table_column_name_placeholder')}
                        .value=${this._draftColumnName}
                        @change=${(e) => { this._draftColumnName = e.detail.value; }}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this._text('data_table_column_type')}
                        .value=${this._draftColumnType}
                        .config=${{ values: COLUMN_TYPES }}
                        @change=${(e) => { this._draftColumnType = e.detail.value; }}
                    ></platform-field>
                    <platform-button
                        ?disabled=${this._loading || this._draftColumnName.trim().length === 0}
                        @click=${() => { void this._submitAddColumn(); }}
                    >
                        ${this._text('data_table_add_column_submit')}
                    </platform-button>
                ` : nothing}
            </div>
        `;
    }

    _renderSchema() {
        const table = this._activeTable();
        if (!table) {
            return html`<div class="status">${this._text('data_table_empty')}</div>`;
        }
        return html`
            <div class="schema-list">
                <div class="schema-card">
                    <strong>${table.name}</strong>
                    <span> · ${this._text('data_table_row_count', { count: table.row_count })}</span>
                    ${table.columns.map((column) => html`
                        <div>${column.name}: ${column.column_type}${column.not_null ? ' NOT NULL' : ''}</div>
                    `)}
                </div>
            </div>
        `;
    }

    _cellValue(row, columnName) {
        const values = row.values;
        if (!values || typeof values !== 'object') {
            return '';
        }
        const value = values[columnName];
        if (value === null || value === undefined) {
            return '';
        }
        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
            return value;
        }
        return JSON.stringify(value);
    }

    _renderPager() {
        if (!this._hasMore) {
            return nothing;
        }
        return html`
            <div class="pager">
                <platform-button
                    ?disabled=${this._loading}
                    @click=${() => { void this.loadMore(); }}
                >${this._text('data_table_next')}</platform-button>
            </div>
        `;
    }

    _renderGrid() {
        const table = this._activeTable();
        if (!table) {
            return html`<div class="status">${this._text('data_table_empty')}</div>`;
        }
        const columns = table.columns;
        const editable = !this._isView();
        const editing = this._editing;
        return html`
            <div class="grid-wrap" @scroll=${this._onGridScroll}>
                <table>
                    <thead>
                        <tr>
                            <th class="sys">row_id</th>
                            ${columns.map((column) => html`
                                <th>
                                    <div class="col-head">
                                        <span class="col-title">${column.name}</span>
                                        <input
                                            type="search"
                                            data-canon="search-as-you-type"
                                            class="col-filter"
                                            placeholder=${this._text('data_table_column_filter_placeholder')}
                                            .value=${this._filterValue(column.name)}
                                            @input=${(e) => this._onColumnFilterInput(column.name, e.target.value)}
                                        />
                                    </div>
                                </th>
                            `)}
                            ${editable ? html`<th class="row-actions"></th>` : nothing}
                        </tr>
                    </thead>
                    <tbody>
                        ${this._rows.map((row) => html`
                            <tr>
                                <td class="sys">${row.row_id}</td>
                                ${columns.map((column) => {
                                    const isEditing = editable
                                        && editing
                                        && editing.rowId === row.row_id
                                        && editing.column === column.name;
                                    const display = this._cellValue(row, column.name);
                                    if (isEditing) {
                                        return html`<td class="cell-editing">
                                            <input
                                                data-canon="inline-edit"
                                                .value=${this._editDraft}
                                                @input=${this._onEditInput}
                                                @keydown=${this._onEditKeydown}
                                                @blur=${this._onEditBlur}
                                            />
                                        </td>`;
                                    }
                                    const empty = display === '';
                                    return html`<td
                                        class=${editable ? 'cell-editable' : ''}
                                        tabindex=${editable ? '0' : nothing}
                                        @click=${editable ? () => this._beginEdit(row.row_id, column.name, { selectAll: true }) : undefined}
                                        @keydown=${editable ? (e) => this._onCellKeydown(e, row.row_id, column.name) : undefined}
                                    >${empty
                                        ? (editable
                                            ? html`<span class="cell-placeholder">${this._text('data_table_cell_edit_hint')}</span>`
                                            : '')
                                        : display}</td>`;
                                })}
                                ${editable ? html`
                                    <td class="row-actions">
                                        <platform-button
                                            icon-only
                                            density="dense"
                                            variant="ghost"
                                            danger
                                            aria-label=${this._text('data_table_delete_row')}
                                            title=${this._text('data_table_delete_row')}
                                            ?disabled=${this._deletingRowId === row.row_id || this._loading}
                                            @click=${(event) => {
                                                event.stopPropagation();
                                                void this.deleteRow(row.row_id);
                                            }}
                                        >
                                            <platform-icon name="trash" size="14"></platform-icon>
                                        </platform-button>
                                    </td>
                                ` : nothing}
                            </tr>
                        `)}
                    </tbody>
                </table>
                ${this._loading ? html`<div class="status">${this._text('loading')}</div>` : nothing}
            </div>
            ${this._renderPager()}
        `;
    }

    render() {
        if (this._error) {
            return html`<div class="error">${this._error}</div>`;
        }
        if (!this._schema) {
            return html`<div class="status">${this._text('loading')}</div>`;
        }
        return html`
            ${this._renderToolbar()}
            ${this._formError
                ? html`<p class="form-error banner">${this._formError}</p>`
                : nothing}
            ${this._renderAddForms()}
            ${this.viewMode === 'schema' ? this._renderSchema() : this._renderGrid()}
        `;
    }
}

customElements.define('platform-data-table-host', PlatformDataTableHost);
