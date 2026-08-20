/**
 * Редактор NodeType.datasource: подключение, операция, SQL.
 * Create/edit подключения — карточка в инспекторе (как HITL queue).
 * Play ноды — flows/code_execute. Здесь Test connection и схема таблиц.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import '@platform/lib/components/platform-button.js';
import './flows-base-node-editor.js';
import { asObject } from '../../_helpers/flows-resolvers.js';

const OPERATIONS = Object.freeze(['introspect', 'query', 'execute']);
const SSL_MODES = Object.freeze(['disable', 'require', 'verify-full']);
const SQL_OPERATIONS = Object.freeze(['select', 'insert', 'update', 'delete']);
const SQL_PARAM_RE = /(?<!:):([A-Za-z_][A-Za-z0-9_]*)/g;

/**
 * @param {string} connectorId
 * @returns {number | null}
 */
function defaultPortForConnector(connectorId) {
    if (connectorId === 'postgres') {
        return 5432;
    }
    if (connectorId === 'mysql') {
        return 3306;
    }
    if (connectorId === 'clickhouse') {
        return 8123;
    }
    return null;
}

/**
 * @param {string} host
 * @returns {boolean}
 */
function isLocalhostHost(host) {
    const normalized = host.trim().toLowerCase();
    return normalized === 'localhost' || normalized === '127.0.0.1';
}

/**
 * @param {string} sql
 * @returns {string[]}
 */
function sqlNamedParams(sql) {
    const names = [];
    const seen = new Set();
    SQL_PARAM_RE.lastIndex = 0;
    let match = SQL_PARAM_RE.exec(sql);
    while (match !== null) {
        const name = match[1];
        if (!seen.has(name)) {
            seen.add(name);
            names.push(name);
        }
        match = SQL_PARAM_RE.exec(sql);
    }
    return names;
}

export class FlowsDatasourceNodeEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        dataflowNode: { type: Object },
        embedded: { type: Boolean, reflect: true },
        _showCreate: { state: true },
        _createName: { state: true },
        _createHost: { state: true },
        _createPort: { state: true },
        _createDatabaseName: { state: true },
        _createUsername: { state: true },
        _createPassword: { state: true },
        _createSslMode: { state: true },
        _createAllowedOperations: { state: true },
        _editBoundId: { state: true },
        _editHydrated: { state: true },
        _editName: { state: true },
        _editHost: { state: true },
        _editPort: { state: true },
        _editDatabaseName: { state: true },
        _editUsername: { state: true },
        _editPassword: { state: true },
        _editSslMode: { state: true },
        _editAllowedOperations: { state: true },
        _editStatementTimeoutMs: { state: true },
        _editMaxRows: { state: true },
        _testSummary: { state: true },
        _testError: { state: true },
        _schemaTables: { state: true },
        _schemaError: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .picker-row {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            .create-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
                margin-bottom: var(--space-3);
            }
            .create-grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            }
            .create-actions,
            .connection-actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .schema-list {
                margin: 0;
                padding-left: 0;
                list-style: none;
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .schema-list > li {
                margin-bottom: var(--space-2);
            }
            .schema-columns {
                margin: var(--space-1) 0 0 0;
                padding-left: 1.1em;
                list-style: disc;
            }
            .schema-columns li { margin-bottom: var(--space-1); }
            .test-line {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0 0 var(--space-3) 0;
            }
            .test-line.test-error,
            .empty-warning {
                color: var(--error);
            }
            .ssl-hint,
            .sql-params {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0 0 var(--space-2) 0;
            }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = '';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.embedded = false;
        this._showCreate = false;
        this._createName = '';
        this._createHost = '';
        this._createPort = null;
        this._createDatabaseName = '';
        this._createUsername = '';
        this._createPassword = '';
        this._createSslMode = 'require';
        this._createAllowedOperations = ['select'];
        this._editBoundId = '';
        this._editHydrated = false;
        this._editName = '';
        this._editHost = '';
        this._editPort = null;
        this._editDatabaseName = '';
        this._editUsername = '';
        this._editPassword = '';
        this._editSslMode = 'require';
        this._editAllowedOperations = ['select'];
        this._editStatementTimeoutMs = 15000;
        this._editMaxRows = 1000;
        this._testSummary = null;
        this._testError = null;
        this._schemaTables = null;
        this._schemaError = null;
        this._datasources = this.useResource('flows/datasources');
        this._testOp = this.useOp('flows/datasource_test');
        this._introspectOp = this.useOp('flows/datasource_introspect');
    }

    connectedCallback() {
        super.connectedCallback();
        this._datasources.load({});
    }

    updated(changed) {
        super.updated(changed);
        const datasourceId = this._selectedDatasourceId();
        const item = this._connectionById(datasourceId);
        if (datasourceId !== this._editBoundId) {
            this._hydrateEdit(item, datasourceId);
            return;
        }
        if (item !== null && this._editHydrated === false) {
            this._hydrateEdit(item, datasourceId);
        }
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _selectedDatasourceId() {
        const cfg = asObject(this.nodeConfig);
        return typeof cfg.datasource_id === 'string' ? cfg.datasource_id : '';
    }

    _connectionById(datasourceId) {
        if (datasourceId.length === 0) {
            return null;
        }
        const items = this._datasources.items;
        if (!Array.isArray(items)) {
            throw new Error('flows-datasource-node-editor: datasources.items must be array');
        }
        for (const item of items) {
            if (item === null || typeof item !== 'object') {
                throw new Error('flows-datasource-node-editor: connection item must be object');
            }
            if (item.datasource_id === datasourceId) {
                return item;
            }
        }
        return null;
    }

    /**
     * @param {object | null} item
     * @param {string} datasourceId
     */
    _hydrateEdit(item, datasourceId) {
        this._editBoundId = datasourceId;
        if (item === null) {
            this._editHydrated = false;
            this._editName = '';
            this._editHost = '';
            this._editPort = null;
            this._editDatabaseName = '';
            this._editUsername = '';
            this._editPassword = '';
            this._editSslMode = 'require';
            this._editAllowedOperations = ['select'];
            this._editStatementTimeoutMs = 15000;
            this._editMaxRows = 1000;
            return;
        }
        this._editHydrated = true;
        this._editName = item.name;
        this._editHost = typeof item.host === 'string' ? item.host : '';
        this._editPort = typeof item.port === 'number' ? item.port : null;
        this._editDatabaseName = typeof item.database_name === 'string' ? item.database_name : '';
        this._editUsername = typeof item.username === 'string' ? item.username : '';
        this._editPassword = '';
        this._editSslMode = item.ssl_mode;
        this._editAllowedOperations = [...item.allowed_operations];
        this._editStatementTimeoutMs = item.statement_timeout_ms;
        this._editMaxRows = item.max_rows;
    }

    /**
     * @returns {{ value: string, label: string }[]}
     */
    _connectionOptions() {
        const items = this._datasources.items;
        if (!Array.isArray(items)) {
            throw new Error('flows-datasource-node-editor: datasources.items must be array');
        }
        const cfg = asObject(this.nodeConfig);
        const connectorId = typeof cfg.connector_id === 'string' ? cfg.connector_id : '';
        const options = [];
        for (const item of items) {
            if (item === null || typeof item !== 'object') {
                throw new Error('flows-datasource-node-editor: connection item must be object');
            }
            if (typeof item.datasource_id !== 'string' || item.datasource_id.length === 0) {
                throw new Error('flows-datasource-node-editor: datasource_id required');
            }
            if (typeof item.connector_id !== 'string' || item.connector_id.length === 0) {
                throw new Error('flows-datasource-node-editor: connector_id required');
            }
            if (typeof item.name !== 'string' || item.name.length === 0) {
                throw new Error('flows-datasource-node-editor: name required');
            }
            if (item.connector_id !== connectorId) {
                continue;
            }
            let label = item.name;
            if (typeof item.host === 'string' && item.host.length > 0 && typeof item.port === 'number') {
                label = `${item.name} · ${item.host}:${item.port}`;
            }
            options.push({
                value: item.datasource_id,
                label,
            });
        }
        return options;
    }

    _resetCreateForm() {
        const cfg = asObject(this.nodeConfig);
        const connectorId = typeof cfg.connector_id === 'string' ? cfg.connector_id : '';
        this._createName = '';
        this._createHost = '';
        this._createPort = defaultPortForConnector(connectorId);
        this._createDatabaseName = '';
        this._createUsername = '';
        this._createPassword = '';
        this._createSslMode = 'require';
        this._createAllowedOperations = ['select'];
    }

    _onDatasourceId(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-datasource-node-editor: datasource change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-datasource-node-editor: datasource detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-datasource-node-editor: datasource_id string required');
        }
        this._testSummary = null;
        this._testError = null;
        this._schemaTables = null;
        this._schemaError = null;
        this._emitPatch({ datasource_id: v });
    }

    _onConnectionCreate(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-datasource-node-editor: create detail required');
        }
        if (typeof d.query !== 'string') {
            throw new Error('flows-datasource-node-editor: create detail.query string required');
        }
        this._showCreate = true;
        this._resetCreateForm();
        const query = d.query.trim();
        if (query.length > 0) {
            this._createName = query;
        }
    }

    _toggleCreate() {
        this._showCreate = !this._showCreate;
        if (this._showCreate) {
            this._resetCreateForm();
            return;
        }
        this._resetCreateForm();
    }

    _onCreateName(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-datasource-node-editor: create name detail.value string');
        }
        this._createName = d.value;
    }

    _onCreateHost(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-datasource-node-editor: create host detail.value string');
        }
        this._createHost = d.value;
    }

    _onCreatePort(e) {
        this._createPort = this._readIntegerOrEmpty(e, 'create port');
    }

    _onCreateDatabaseName(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-datasource-node-editor: create database_name detail.value string');
        }
        this._createDatabaseName = d.value;
    }

    _onCreateUsername(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-datasource-node-editor: create username detail.value string');
        }
        this._createUsername = d.value;
    }

    _onCreatePassword(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-datasource-node-editor: create password detail.value string');
        }
        this._createPassword = d.value;
    }

    _onCreateSslMode(e) {
        this._createSslMode = this._readSslMode(e, 'create ssl_mode');
    }

    _onCreateAllowedOperations(e) {
        this._createAllowedOperations = this._readAllowedOperations(e, 'create allowed_operations');
    }

    _onEditName(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-datasource-node-editor: edit name detail.value string');
        }
        this._editName = d.value;
    }

    _onEditHost(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-datasource-node-editor: edit host detail.value string');
        }
        this._editHost = d.value;
    }

    _onEditPort(e) {
        this._editPort = this._readIntegerOrEmpty(e, 'edit port');
    }

    _onEditDatabaseName(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-datasource-node-editor: edit database_name detail.value string');
        }
        this._editDatabaseName = d.value;
    }

    _onEditUsername(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-datasource-node-editor: edit username detail.value string');
        }
        this._editUsername = d.value;
    }

    _onEditPassword(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-datasource-node-editor: edit password detail.value string');
        }
        this._editPassword = d.value;
    }

    _onEditSslMode(e) {
        this._editSslMode = this._readSslMode(e, 'edit ssl_mode');
    }

    _onEditAllowedOperations(e) {
        this._editAllowedOperations = this._readAllowedOperations(e, 'edit allowed_operations');
    }

    _onEditStatementTimeoutMs(e) {
        const value = this._readIntegerOrEmpty(e, 'edit statement_timeout_ms');
        if (value === null) {
            throw new Error('flows-datasource-node-editor: statement_timeout_ms required');
        }
        this._editStatementTimeoutMs = value;
    }

    _onEditMaxRows(e) {
        const value = this._readIntegerOrEmpty(e, 'edit max_rows');
        if (value === null) {
            throw new Error('flows-datasource-node-editor: max_rows required');
        }
        this._editMaxRows = value;
    }

    _readIntegerOrEmpty(e, label) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error(`flows-datasource-node-editor: ${label} detail`);
        }
        if (!('value' in d)) {
            throw new Error(`flows-datasource-node-editor: ${label} detail.value`);
        }
        const v = d.value;
        if (v === null || v === '') {
            return null;
        }
        if (typeof v !== 'number' || !Number.isInteger(v)) {
            throw new Error(`flows-datasource-node-editor: ${label} must be integer or empty`);
        }
        return v;
    }

    _readSslMode(e, label) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error(`flows-datasource-node-editor: ${label} detail.value string`);
        }
        if (!SSL_MODES.includes(d.value)) {
            throw new Error('flows-datasource-node-editor: ssl_mode disable|require|verify-full');
        }
        return d.value;
    }

    _readAllowedOperations(e, label) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !Array.isArray(d.value)) {
            throw new Error(`flows-datasource-node-editor: ${label} array`);
        }
        const next = [];
        for (const item of d.value) {
            if (typeof item !== 'string' || !SQL_OPERATIONS.includes(item)) {
                throw new Error('flows-datasource-node-editor: allowed_operations item');
            }
            next.push(item);
        }
        return next;
    }

    /**
     * @param {object} controller
     * @param {string} requestedId
     * @param {string} successType
     * @param {string} failedType
     * @returns {Promise<object | null>}
     */
    _waitForCausedEvent(controller, requestedId, successType, failedType) {
        const bus = controller.bus;
        return new Promise((resolve, reject) => {
            let offSuccess = null;
            let offFailed = null;
            const cleanup = () => {
                if (typeof offSuccess === 'function') {
                    offSuccess();
                }
                if (typeof offFailed === 'function') {
                    offFailed();
                }
            };
            offSuccess = bus.subscribeType(successType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                resolve(event.payload && typeof event.payload === 'object' ? event.payload : null);
            });
            offFailed = bus.subscribeType(failedType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                const message = event.payload && typeof event.payload.message === 'string'
                    ? event.payload.message
                    : 'datasource mutation failed';
                reject(new Error(message));
            });
        });
    }

    async _createConnection() {
        const cfg = asObject(this.nodeConfig);
        const connectorId = typeof cfg.connector_id === 'string' ? cfg.connector_id.trim() : '';
        if (connectorId.length === 0) {
            throw new Error('flows-datasource-node-editor: connector_id required to create connection');
        }
        const name = this._createName.trim();
        const host = this._createHost.trim();
        const databaseName = this._createDatabaseName.trim();
        const username = this._createUsername.trim();
        const password = this._createPassword;
        if (name.length === 0 || host.length === 0 || databaseName.length === 0 || username.length === 0) {
            this.toast('datasource_node_editor.create_required', { type: 'error' });
            return;
        }
        if (typeof this._createPort !== 'number' || !Number.isInteger(this._createPort)) {
            this.toast('datasource_node_editor.create_port_required', { type: 'error' });
            return;
        }
        if (password.length === 0) {
            this.toast('datasource_node_editor.create_password_required', { type: 'error' });
            return;
        }
        if (this._createAllowedOperations.length === 0) {
            this.toast('datasource_node_editor.create_operations_required', { type: 'error' });
            return;
        }
        if (this._datasources.createInFlight) {
            return;
        }
        const requested = this._datasources.create({
            connector_id: connectorId,
            name,
            host,
            port: this._createPort,
            database_name: databaseName,
            username,
            password,
            ssl_mode: this._createSslMode,
            allowed_operations: this._createAllowedOperations,
        });
        if (!requested || typeof requested.id !== 'string') {
            return;
        }
        const payload = await this._waitForCausedEvent(
            this._datasources,
            requested.id,
            this._datasources.resource.events.CREATED,
            this._datasources.resource.events.CREATE_FAILED,
        );
        const item = payload !== null && typeof payload.item === 'object' ? payload.item : null;
        if (item === null || typeof item !== 'object') {
            throw new Error('flows-datasource-node-editor: created connection item missing');
        }
        if (typeof item.datasource_id !== 'string' || item.datasource_id.length === 0) {
            throw new Error('flows-datasource-node-editor: created datasource_id missing');
        }
        this._emitPatch({ datasource_id: item.datasource_id });
        this._showCreate = false;
        this._resetCreateForm();
        this._datasources.load({});
    }

    async _saveConnection() {
        const datasourceId = this._selectedDatasourceId().trim();
        if (datasourceId.length === 0) {
            this.toast('datasource_node_editor.datasource_id_required', { type: 'error' });
            return;
        }
        if (this._datasources.isBusy(datasourceId)) {
            return;
        }
        const name = this._editName.trim();
        const host = this._editHost.trim();
        const databaseName = this._editDatabaseName.trim();
        const username = this._editUsername.trim();
        if (name.length === 0 || host.length === 0 || databaseName.length === 0 || username.length === 0) {
            this.toast('datasource_node_editor.create_required', { type: 'error' });
            return;
        }
        if (typeof this._editPort !== 'number' || !Number.isInteger(this._editPort)) {
            this.toast('datasource_node_editor.create_port_required', { type: 'error' });
            return;
        }
        if (this._editAllowedOperations.length === 0) {
            this.toast('datasource_node_editor.create_operations_required', { type: 'error' });
            return;
        }
        const body = {
            name,
            host,
            port: this._editPort,
            database_name: databaseName,
            username,
            ssl_mode: this._editSslMode,
            allowed_operations: this._editAllowedOperations,
            statement_timeout_ms: this._editStatementTimeoutMs,
            max_rows: this._editMaxRows,
        };
        if (this._editPassword.length > 0) {
            body.password = this._editPassword;
        }
        const requested = this._datasources.update(datasourceId, body);
        if (!requested || typeof requested.id !== 'string') {
            return;
        }
        await this._waitForCausedEvent(
            this._datasources,
            requested.id,
            this._datasources.resource.events.UPDATED,
            this._datasources.resource.events.UPDATE_FAILED,
        );
        this._editPassword = '';
        this._datasources.load({});
    }

    async _deleteConnection() {
        const datasourceId = this._selectedDatasourceId().trim();
        if (datasourceId.length === 0) {
            this.toast('datasource_node_editor.datasource_id_required', { type: 'error' });
            return;
        }
        const confirmed = await platformConfirm(this.t('datasource_node_editor.delete_confirm_body'), {
            title: this.t('datasource_node_editor.delete_confirm_title'),
            variant: 'danger',
            confirmVariant: 'danger',
        });
        if (!confirmed) {
            return;
        }
        const requested = this._datasources.remove(datasourceId);
        if (!requested || typeof requested.id !== 'string') {
            return;
        }
        await this._waitForCausedEvent(
            this._datasources,
            requested.id,
            this._datasources.resource.events.REMOVED,
            this._datasources.resource.events.REMOVE_FAILED,
        );
        this._emitPatch({ datasource_id: '' });
        this._testSummary = null;
        this._testError = null;
        this._schemaTables = null;
        this._schemaError = null;
        this._datasources.load({});
    }

    _requireOpError(op, label) {
        const message = op.error;
        if (typeof message !== 'string' || message.length === 0) {
            throw new Error(`flows-datasource-node-editor: ${label} failed without error message`);
        }
        return message;
    }

    async _runTest() {
        const datasourceId = this._selectedDatasourceId().trim();
        if (datasourceId.length === 0) {
            this.toast('datasource_node_editor.datasource_id_required', { type: 'error' });
            return;
        }
        this._testError = null;
        const result = await this._testOp.run({ datasource_id: datasourceId });
        if (result === null) {
            this._testSummary = null;
            this._testError = this._requireOpError(this._testOp, 'test');
            return;
        }
        if (typeof result !== 'object' || Array.isArray(result)) {
            throw new Error('flows-datasource-node-editor: test result object required');
        }
        if (typeof result.ok !== 'boolean') {
            throw new Error('flows-datasource-node-editor: test result.ok boolean required');
        }
        if (typeof result.latency_ms !== 'number') {
            throw new Error('flows-datasource-node-editor: test result.latency_ms number required');
        }
        const version = result.server_version;
        if (version !== null && version !== undefined && typeof version !== 'string') {
            throw new Error('flows-datasource-node-editor: test result.server_version string or null');
        }
        this._testError = null;
        this._testSummary = {
            ok: result.ok,
            latencyMs: result.latency_ms,
            serverVersion: typeof version === 'string' ? version : null,
        };
    }

    async _runSchema() {
        const datasourceId = this._selectedDatasourceId().trim();
        if (datasourceId.length === 0) {
            this.toast('datasource_node_editor.datasource_id_required', { type: 'error' });
            return;
        }
        this._schemaError = null;
        const result = await this._introspectOp.run({ datasource_id: datasourceId });
        if (result === null) {
            this._schemaTables = null;
            this._schemaError = this._requireOpError(this._introspectOp, 'schema');
            return;
        }
        if (typeof result !== 'object' || !Array.isArray(result.tables)) {
            throw new Error('flows-datasource-node-editor: introspect tables array required');
        }
        const tables = [];
        for (const table of result.tables) {
            if (table === null || typeof table !== 'object') {
                throw new Error('flows-datasource-node-editor: table object required');
            }
            if (typeof table.table_name !== 'string' || table.table_name.length === 0) {
                throw new Error('flows-datasource-node-editor: table_name required');
            }
            if (!Array.isArray(table.columns)) {
                throw new Error('flows-datasource-node-editor: table.columns array required');
            }
            const columns = [];
            for (const column of table.columns) {
                if (column === null || typeof column !== 'object') {
                    throw new Error('flows-datasource-node-editor: column object required');
                }
                if (typeof column.name !== 'string' || column.name.length === 0) {
                    throw new Error('flows-datasource-node-editor: column.name required');
                }
                if (typeof column.data_type !== 'string' || column.data_type.length === 0) {
                    throw new Error('flows-datasource-node-editor: column.data_type required');
                }
                columns.push({ name: column.name, dataType: column.data_type });
            }
            tables.push({ tableName: table.table_name, columns });
        }
        this._schemaError = null;
        this._schemaTables = tables;
    }

    _onSchemaTable(tableName) {
        if (typeof tableName !== 'string' || tableName.length === 0) {
            throw new Error('flows-datasource-node-editor: tableName required');
        }
        this._emitPatch({ sql: `SELECT * FROM ${tableName} LIMIT 50` });
    }

    _onSchemaColumn(columnName) {
        if (typeof columnName !== 'string' || columnName.length === 0) {
            throw new Error('flows-datasource-node-editor: columnName required');
        }
        const cfg = asObject(this.nodeConfig);
        const current = typeof cfg.sql === 'string' ? cfg.sql : '';
        const token = `:${columnName}`;
        if (current.length === 0) {
            this._emitPatch({ sql: token });
            return;
        }
        const glue = current.endsWith(' ') ? '' : ' ';
        this._emitPatch({ sql: `${current}${glue}${token}` });
    }

    async _onOperation(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-datasource-node-editor: operation change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-datasource-node-editor: operation detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string' || !OPERATIONS.includes(v)) {
            throw new Error('flows-datasource-node-editor: datasource_operation must be introspect|query|execute');
        }
        const cfg = asObject(this.nodeConfig);
        const current = OPERATIONS.includes(cfg.datasource_operation)
            ? cfg.datasource_operation
            : 'query';
        if (v === 'execute' && current !== 'execute') {
            const confirmed = await platformConfirm(this.t('datasource_node_editor.execute_confirm_body'), {
                title: this.t('datasource_node_editor.execute_confirm_title'),
                variant: 'danger',
                confirmVariant: 'danger',
            });
            if (!confirmed) {
                this.requestUpdate();
                return;
            }
        }
        this._emitPatch({ datasource_operation: v });
    }

    _onSql(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-datasource-node-editor: sql change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-datasource-node-editor: sql detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-datasource-node-editor: sql string required');
        }
        this._emitPatch({ sql: v });
    }

    _sslModeValues() {
        return [
            { value: 'disable', label: this.t('datasource_node_editor.ssl_disable') },
            { value: 'require', label: this.t('datasource_node_editor.ssl_require') },
            { value: 'verify-full', label: this.t('datasource_node_editor.ssl_verify_full') },
        ];
    }

    _credentialFields(prefix, values, handlers) {
        return html`
            <platform-field
                type="string"
                mode="edit"
                .label=${this.t('datasource_node_editor.create_name')}
                .value=${values.name}
                @change=${handlers.name}
            ></platform-field>
            <platform-field
                type="string"
                mode="edit"
                .label=${this.t('datasource_node_editor.create_host')}
                .value=${values.host}
                @change=${handlers.host}
            ></platform-field>
            <platform-field
                type="integer"
                mode="edit"
                .label=${this.t('datasource_node_editor.create_port')}
                .value=${values.port}
                @change=${handlers.port}
            ></platform-field>
            <platform-field
                type="string"
                mode="edit"
                .label=${this.t('datasource_node_editor.create_database_name')}
                .value=${values.databaseName}
                @change=${handlers.databaseName}
            ></platform-field>
            <platform-field
                type="string"
                mode="edit"
                .label=${this.t('datasource_node_editor.create_username')}
                .value=${values.username}
                @change=${handlers.username}
            ></platform-field>
            <platform-field
                type="string"
                input-type="password"
                mode="edit"
                .label=${this.t('datasource_node_editor.create_password')}
                .hint=${prefix === 'edit' ? this.t('datasource_node_editor.password_keep_hint') : ''}
                .value=${values.password}
                @change=${handlers.password}
            ></platform-field>
            <platform-field
                type="enum"
                mode="edit"
                .label=${this.t('datasource_node_editor.create_ssl_mode')}
                .value=${values.sslMode}
                .config=${{ values: this._sslModeValues() }}
                @change=${handlers.sslMode}
            ></platform-field>
            <platform-field
                type="array"
                mode="edit"
                .label=${this.t('datasource_node_editor.create_allowed_operations')}
                .value=${values.allowedOperations}
                .config=${{ allowed_values: [...SQL_OPERATIONS] }}
                @change=${handlers.allowedOperations}
            ></platform-field>
        `;
    }

    render() {
        const cfg = asObject(this.nodeConfig);
        const connectorId = typeof cfg.connector_id === 'string' ? cfg.connector_id : '';
        const datasourceId = typeof cfg.datasource_id === 'string' ? cfg.datasource_id : '';
        const operation = OPERATIONS.includes(cfg.datasource_operation)
            ? cfg.datasource_operation
            : 'query';
        const sql = typeof cfg.sql === 'string' ? cfg.sql : '';
        const operationValues = [
            { value: 'introspect', label: this.t('datasource_node_editor.operation_introspect') },
            { value: 'query', label: this.t('datasource_node_editor.operation_query') },
            { value: 'execute', label: this.t('datasource_node_editor.operation_execute') },
        ];
        const showSql = operation === 'query' || operation === 'execute';
        const testBusy = this._testOp.busy === true;
        const schemaBusy = this._introspectOp.busy === true;
        const createBusy = this._datasources.createInFlight === true;
        const editBusy = datasourceId.length > 0 && this._datasources.isBusy(datasourceId);
        const selected = this._connectionById(datasourceId);
        const sqlParams = sqlNamedParams(sql);
        const createLocalhost = isLocalhostHost(this._createHost);
        const editLocalhost = isLocalhostHost(this._editHost);
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'datasource'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
                ?embedded=${this.embedded}
            >
                <div slot="settings">
                    <div class="field">
                        <platform-field
                            type="string"
                            mode="view"
                            .label=${this.t('datasource_node_editor.connector_id')}
                            .value=${connectorId}
                        ></platform-field>
                    </div>
                    ${datasourceId.trim().length === 0 ? html`
                        <p class="empty-warning">${this.t('datasource_node_editor.empty_connection_warning')}</p>
                    ` : nothing}
                    <div class="picker-row">
                        <platform-searchable-combobox
                            .label=${this.t('datasource_node_editor.datasource_id')}
                            .placeholder=${this.t('datasource_node_editor.datasource_picker')}
                            .emptyLabel=${this.t('datasource_node_editor.datasource_clear')}
                            .createLabel=${this.t('datasource_node_editor.connection_create')}
                            .createQueryLabel=${this.t('datasource_node_editor.connection_create_query')}
                            aria-label=${this.t('datasource_node_editor.datasource_aria')}
                            .value=${datasourceId}
                            .options=${this._connectionOptions()}
                            @change=${this._onDatasourceId}
                            @create=${this._onConnectionCreate}
                        ></platform-searchable-combobox>
                    </div>
                    ${this._showCreate ? html`
                        <section class="create-card">
                            <div class="create-grid">
                                ${this._credentialFields('create', {
                                    name: this._createName,
                                    host: this._createHost,
                                    port: this._createPort,
                                    databaseName: this._createDatabaseName,
                                    username: this._createUsername,
                                    password: this._createPassword,
                                    sslMode: this._createSslMode,
                                    allowedOperations: this._createAllowedOperations,
                                }, {
                                    name: this._onCreateName,
                                    host: this._onCreateHost,
                                    port: this._onCreatePort,
                                    databaseName: this._onCreateDatabaseName,
                                    username: this._onCreateUsername,
                                    password: this._onCreatePassword,
                                    sslMode: this._onCreateSslMode,
                                    allowedOperations: this._onCreateAllowedOperations,
                                })}
                            </div>
                            ${createLocalhost ? html`
                                <p class="ssl-hint">${this.t('datasource_node_editor.ssl_localhost_hint')}</p>
                            ` : nothing}
                            <div class="create-actions">
                                <platform-button
                                    variant="ghost"
                                    density="compact"
                                    @click=${() => this._toggleCreate()}
                                >
                                    ${this.t('datasource_node_editor.create_cancel')}
                                </platform-button>
                                <platform-button
                                    variant="primary"
                                    density="compact"
                                    ?disabled=${createBusy}
                                    @click=${() => void this._createConnection()}
                                >
                                    ${this.t('datasource_node_editor.create_submit')}
                                </platform-button>
                            </div>
                        </section>
                    ` : nothing}
                    ${selected !== null && this._showCreate === false ? html`
                        <section class="create-card" data-connection-edit>
                            <div class="create-grid">
                                ${this._credentialFields('edit', {
                                    name: this._editName,
                                    host: this._editHost,
                                    port: this._editPort,
                                    databaseName: this._editDatabaseName,
                                    username: this._editUsername,
                                    password: this._editPassword,
                                    sslMode: this._editSslMode,
                                    allowedOperations: this._editAllowedOperations,
                                }, {
                                    name: this._onEditName,
                                    host: this._onEditHost,
                                    port: this._onEditPort,
                                    databaseName: this._onEditDatabaseName,
                                    username: this._onEditUsername,
                                    password: this._onEditPassword,
                                    sslMode: this._onEditSslMode,
                                    allowedOperations: this._onEditAllowedOperations,
                                })}
                                <platform-field
                                    type="integer"
                                    mode="edit"
                                    .label=${this.t('datasource_node_editor.timeout_ms')}
                                    .value=${this._editStatementTimeoutMs}
                                    @change=${this._onEditStatementTimeoutMs}
                                ></platform-field>
                                <platform-field
                                    type="integer"
                                    mode="edit"
                                    .label=${this.t('datasource_node_editor.max_rows')}
                                    .value=${this._editMaxRows}
                                    @change=${this._onEditMaxRows}
                                ></platform-field>
                            </div>
                            ${editLocalhost ? html`
                                <p class="ssl-hint">${this.t('datasource_node_editor.ssl_localhost_hint')}</p>
                            ` : nothing}
                            <div class="create-actions">
                                <platform-button
                                    variant="danger"
                                    density="compact"
                                    ?disabled=${editBusy}
                                    @click=${() => void this._deleteConnection()}
                                >
                                    ${this.t('datasource_node_editor.connection_delete')}
                                </platform-button>
                                <platform-button
                                    variant="primary"
                                    density="compact"
                                    ?disabled=${editBusy}
                                    @click=${() => void this._saveConnection()}
                                >
                                    ${this.t('datasource_node_editor.connection_save')}
                                </platform-button>
                            </div>
                        </section>
                    ` : nothing}
                    <div class="connection-actions">
                        <platform-button
                            variant="ghost"
                            density="compact"
                            ?disabled=${datasourceId.length === 0 || testBusy}
                            @click=${() => void this._runTest()}
                        >
                            ${this.t('datasource_node_editor.test_connection')}
                        </platform-button>
                        <platform-button
                            variant="secondary"
                            density="compact"
                            ?disabled=${datasourceId.length === 0 || schemaBusy}
                            @click=${() => void this._runSchema()}
                        >
                            ${this.t('datasource_node_editor.load_schema')}
                        </platform-button>
                    </div>
                    ${this._testError !== null ? html`
                        <p class="test-line test-error">${this._testError}</p>
                    ` : nothing}
                    ${this._testSummary !== null ? html`
                        <p class="test-line">
                            ${this.t('datasource_node_editor.test_summary', {
                                ok: this._testSummary.ok
                                    ? this.t('datasource_node_editor.test_ok')
                                    : this.t('datasource_node_editor.test_fail'),
                                ms: String(this._testSummary.latencyMs),
                                version: this._testSummary.serverVersion === null
                                    ? this.t('datasource_node_editor.test_version_unknown')
                                    : this._testSummary.serverVersion,
                            })}
                        </p>
                    ` : nothing}
                    ${this._schemaError !== null ? html`
                        <p class="test-line test-error">${this._schemaError}</p>
                    ` : nothing}
                    ${this._schemaTables !== null ? html`
                        <p class="test-line">
                            ${this.t('datasource_node_editor.test_tables', {
                                count: String(this._schemaTables.length),
                            })}
                        </p>
                        <p class="sql-params">${this.t('datasource_node_editor.schema_click_table')}</p>
                        <p class="sql-params">${this.t('datasource_node_editor.schema_click_column')}</p>
                        <ul class="schema-list">
                            ${this._schemaTables.map((table) => html`
                                <li>
                                    <platform-button
                                        variant="ghost"
                                        density="compact"
                                        @click=${() => this._onSchemaTable(table.tableName)}
                                    >
                                        ${table.tableName}
                                    </platform-button>
                                    <ul class="schema-columns">
                                        ${table.columns.map((column) => html`
                                            <li>
                                                <platform-button
                                                    variant="ghost"
                                                    density="compact"
                                                    @click=${() => this._onSchemaColumn(column.name)}
                                                >
                                                    ${column.name}:${column.dataType}
                                                </platform-button>
                                            </li>
                                        `)}
                                    </ul>
                                </li>
                            `)}
                        </ul>
                    ` : nothing}
                    <div class="field">
                        <platform-field
                            mode="edit"
                            type="enum"
                            .label=${this.t('datasource_node_editor.operation')}
                            .value=${operation}
                            .config=${{ values: operationValues }}
                            @change=${(e) => void this._onOperation(e)}
                        ></platform-field>
                    </div>
                    ${showSql ? html`
                        <div class="field">
                            <platform-field
                                type="text"
                                mode="edit"
                                .label=${this.t('datasource_node_editor.sql')}
                                .placeholder=${this.t('datasource_node_editor.sql_placeholder')}
                                .hint=${this.t('datasource_node_editor.sql_hint')}
                                .value=${sql}
                                @change=${this._onSql}
                            ></platform-field>
                        </div>
                        ${sqlParams.length > 0 ? html`
                            <p class="sql-params">${this.t('datasource_node_editor.sql_params', {
                                names: sqlParams.map((name) => `:${name}`).join(', '),
                            })}</p>
                        ` : nothing}
                        <p class="sql-params">${this.t('datasource_node_editor.sql_mapping_hint')}</p>
                    ` : nothing}
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-datasource-node-editor', FlowsDatasourceNodeEditor);
