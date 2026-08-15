/**
 * flows-data-table-resource-editor — ресурс type=data_table (SQLite file_id).
 * Схема и Open; создание таблиц — в Documents viewer.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import './flows-base-resource-editor.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';
import { dataTableCreateRequest } from '../../_helpers/flows-resource-defaults.js';

export class FlowsDataTableResourceEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
        flowId: { type: String },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
        _draftName: { state: true },
        _formError: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            .body {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
            }
            .hero {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .stats {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .stat {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
            }
            .stat platform-icon {
                color: var(--accent);
            }
            .tables {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .table-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin: 0;
                padding: var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-elevated);
                color: var(--text-primary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .table-card:hover {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            .table-card:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .table-card-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                min-width: 0;
            }
            .table-name {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                font-weight: var(--font-semibold);
            }
            .table-name span {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .row-badge {
                flex: 0 0 auto;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                font-variant-numeric: tabular-nums;
            }
            .cols {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }
            .col-chip {
                font-size: var(--text-xs);
                padding: 2px 8px;
                border-radius: var(--radius-full);
                background: var(--accent-subtle);
                color: var(--text-secondary);
            }
            .empty {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: var(--space-3);
                padding: var(--space-4) var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
            }
            .empty-lead {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-2);
                text-align: center;
                color: var(--text-secondary);
            }
            .empty-lead platform-icon {
                color: var(--accent);
            }
            .empty-title {
                margin: 0;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .status {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: end;
            }
            .form-error {
                margin: 0;
                color: var(--color-danger);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
        this.flowId = '';
        this.compactHeader = false;
        this._draftName = 'leads';
        this._formError = '';
        this._createOp = this.useOp('flows/data_table_create');
        this._snapshotOp = this.useOp('flows/data_table_snapshot');
    }

    _cfg() {
        if (!isPlainObject(this.resource) || !isPlainObject(this.resource.config)) {
            return {};
        }
        return this.resource.config;
    }

    _fileId() {
        const fileId = this._cfg().file_id;
        return typeof fileId === 'string' ? fileId : '';
    }

    _emitConfig(patch) {
        const base = isPlainObject(this._cfg()) ? this._cfg() : {};
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...base, ...patch } } });
    }

    updated(changed) {
        super.updated(changed);
        const fileId = this._fileId();
        if (fileId.length > 0 && (changed.has('resource') || changed.has('resourceId'))) {
            this._snapshotOp.run({ file_id: fileId });
        }
    }

    _onFileIdChange(event) {
        const detail = event.detail;
        if (!detail || typeof detail !== 'object' || !('value' in detail)) {
            throw new Error('flows-data-table-resource-editor: file_id change');
        }
        const value = detail.value;
        if (typeof value !== 'string') {
            throw new Error('flows-data-table-resource-editor: file_id must be string');
        }
        this._emitConfig({ file_id: value.trim() });
    }

    async _createFile() {
        const flowId = this.flowId.trim();
        if (flowId.length === 0) {
            this._formError = this.t('data_table_resource_editor.flow_id_required');
            return;
        }
        const stem = this._draftName.trim();
        if (stem.length === 0) {
            this._formError = this.t('data_table_resource_editor.name_required');
            return;
        }
        this._formError = '';
        const created = await this._createOp.run(dataTableCreateRequest(flowId, stem));
        if (!created || typeof created.file_id !== 'string' || created.file_id.length === 0) {
            return;
        }
        this._emitConfig({ file_id: created.file_id });
        this._snapshotOp.run({ file_id: created.file_id });
    }

    _openFile() {
        const fileId = this._fileId();
        if (fileId.length === 0) {
            this._formError = this.t('data_table_resource_editor.file_id_required');
            return;
        }
        this.openFile(fileId);
    }

    _onTableCardKeydown(event) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            this._openFile();
        }
    }

    _schemaTables() {
        const result = this._snapshotOp.lastResult;
        if (!result || typeof result !== 'object' || !result.schema_snapshot) {
            return [];
        }
        const tables = result.schema_snapshot.tables;
        return Array.isArray(tables) ? tables : [];
    }

    _totals() {
        const tables = this._schemaTables();
        let rows = 0;
        for (const table of tables) {
            if (typeof table.row_count === 'number') {
                rows += table.row_count;
            }
        }
        return { tables: tables.length, rows };
    }

    _tableColumns(table) {
        return Array.isArray(table.columns) ? table.columns : [];
    }

    _renderBound() {
        const totals = this._totals();
        return html`
            <div class="hero">
                <platform-button
                    variant="primary"
                    @click=${() => this._openFile()}
                >
                    <platform-icon name="expand" size="18"></platform-icon>
                    ${this.t('data_table_resource_editor.open')}
                </platform-button>
                ${this._snapshotOp.busy ? html`
                    <p class="status">${this.t('data_table_resource_editor.schema_loading')}</p>
                ` : totals.tables > 0 ? html`
                    <div class="stats">
                        <span class="stat">
                            <platform-icon name="table" size="14"></platform-icon>
                            ${this.t('data_table_resource_editor.stat_tables', { count: totals.tables })}
                        </span>
                        <span class="stat">
                            <platform-icon name="list" size="14"></platform-icon>
                            ${this.t('data_table_resource_editor.stat_rows', { count: totals.rows })}
                        </span>
                    </div>
                ` : nothing}
            </div>
            ${this._snapshotOp.busy ? nothing : this._renderTables()}
        `;
    }

    _renderTables() {
        const tables = this._schemaTables();
        if (tables.length === 0) {
            return html`<p class="status">${this.t('data_table_resource_editor.schema_empty')}</p>`;
        }
        return html`
            <div class="tables">
                ${tables.map((table) => {
                    const columns = this._tableColumns(table);
                    const rowCount = typeof table.row_count === 'number' ? table.row_count : 0;
                    return html`
                        <article
                            class="table-card"
                            role="button"
                            tabindex="0"
                            @click=${() => this._openFile()}
                            @keydown=${(event) => this._onTableCardKeydown(event)}
                        >
                            <div class="table-card-head">
                                <span class="table-name">
                                    <platform-icon name="table" size="16"></platform-icon>
                                    <span>${table.name}</span>
                                </span>
                                <span class="row-badge">${this.t('data_table_resource_editor.schema_table_rows', { count: rowCount })}</span>
                            </div>
                            ${columns.length > 0 ? html`
                                <div class="cols">
                                    ${columns.map((column) => html`
                                        <span
                                            class="col-chip"
                                            title=${typeof column.column_type === 'string' ? column.column_type : ''}
                                        >${column.name}</span>
                                    `)}
                                </div>
                            ` : nothing}
                        </article>
                    `;
                })}
            </div>
        `;
    }

    _renderUnbound() {
        return html`
            <div class="empty">
                <div class="empty-lead">
                    <platform-icon name="table" size="28"></platform-icon>
                    <p class="empty-title">${this.t('data_table_resource_editor.empty_title')}</p>
                </div>
                <div class="actions">
                    <platform-field
                        type="string"
                        mode="edit"
                        pill-density="compact"
                        .label=${this.t('data_table_resource_editor.field_name')}
                        .value=${this._draftName}
                        @change=${(e) => { this._draftName = e.detail.value; }}
                    ></platform-field>
                    <platform-button
                        ?disabled=${this._createOp.busy}
                        @click=${() => { void this._createFile(); }}
                    >
                        <platform-icon name="plus" size="16"></platform-icon>
                        ${this.t('data_table_resource_editor.create')}
                    </platform-button>
                </div>
                <platform-field
                    type="string"
                    mode="edit"
                    pill-density="compact"
                    .label=${this.t('data_table_resource_editor.field_file_id')}
                    .value=${''}
                    .placeholder=${this.t('data_table_resource_editor.file_id_placeholder')}
                    @change=${this._onFileIdChange}
                ></platform-field>
            </div>
        `;
    }

    render() {
        const fileId = this._fileId();
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'data_table'}
                .compactHeader=${this.compactHeader}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div class="body" slot="settings">
                    ${this._formError ? html`<p class="form-error">${this._formError}</p>` : nothing}
                    ${fileId.length > 0 ? this._renderBound() : this._renderUnbound()}
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-data-table-resource-editor', FlowsDataTableResourceEditor);
