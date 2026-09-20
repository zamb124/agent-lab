/**
 * Company datasource connections — живые БД как шаг графа.
 * REST: `apps/flows/src/api/v1/datasources.py`.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';

const SSL_MODES = Object.freeze(['disable', 'require', 'verify-full']);
const SQL_OPERATIONS = Object.freeze(['select', 'insert', 'update', 'delete']);

/**
 * @param {Record<string, unknown>} row
 * @param {string} key
 * @returns {string | null}
 */
function optionalString(row, key) {
    if (!(key in row) || row[key] === null) {
        return null;
    }
    const value = row[key];
    if (typeof value !== 'string') {
        throw new Error(`flows/datasources.mapItem: ${key} must be string or null`);
    }
    return value;
}

/**
 * @param {Record<string, unknown>} row
 * @param {string} key
 * @returns {number | null}
 */
function optionalPort(row, key) {
    if (!(key in row) || row[key] === null) {
        return null;
    }
    const value = row[key];
    if (typeof value !== 'number' || !Number.isInteger(value) || value < 1 || value > 65535) {
        throw new Error(`flows/datasources.mapItem: ${key} must be integer 1..65535 or null`);
    }
    return value;
}

/**
 * @param {unknown} raw
 * @returns {{
 *   datasource_id: string,
 *   connector_id: string,
 *   name: string,
 *   host: string | null,
 *   port: number | null,
 *   database_name: string | null,
 *   username: string | null,
 *   ssl_mode: string,
 *   allowed_operations: string[],
 *   statement_timeout_ms: number,
 *   max_rows: number,
 * }}
 */
function mapDatasourceConnection(raw) {
    if (raw === null || typeof raw !== 'object') {
        throw new Error('flows/datasources.mapItem: object required');
    }
    const row = /** @type {Record<string, unknown>} */ (raw);
    if (typeof row.datasource_id !== 'string' || row.datasource_id.length === 0) {
        throw new Error('flows/datasources.mapItem: datasource_id required');
    }
    if (typeof row.connector_id !== 'string' || row.connector_id.length === 0) {
        throw new Error('flows/datasources.mapItem: connector_id required');
    }
    if (typeof row.name !== 'string' || row.name.length === 0) {
        throw new Error('flows/datasources.mapItem: name required');
    }
    if (typeof row.ssl_mode !== 'string' || !SSL_MODES.includes(row.ssl_mode)) {
        throw new Error('flows/datasources.mapItem: ssl_mode disable|require|verify-full required');
    }
    if (!Array.isArray(row.allowed_operations) || row.allowed_operations.length === 0) {
        throw new Error('flows/datasources.mapItem: allowed_operations non-empty array required');
    }
    if (typeof row.statement_timeout_ms !== 'number' || !Number.isInteger(row.statement_timeout_ms) || row.statement_timeout_ms < 1) {
        throw new Error('flows/datasources.mapItem: statement_timeout_ms integer >= 1 required');
    }
    if (typeof row.max_rows !== 'number' || !Number.isInteger(row.max_rows) || row.max_rows < 1) {
        throw new Error('flows/datasources.mapItem: max_rows integer >= 1 required');
    }
    const allowedOperations = [];
    for (const item of row.allowed_operations) {
        if (typeof item !== 'string' || !SQL_OPERATIONS.includes(item)) {
            throw new Error('flows/datasources.mapItem: allowed_operations item must be select|insert|update|delete');
        }
        allowedOperations.push(item);
    }
    return {
        datasource_id: row.datasource_id,
        connector_id: row.connector_id,
        name: row.name,
        host: optionalString(row, 'host'),
        port: optionalPort(row, 'port'),
        database_name: optionalString(row, 'database_name'),
        username: optionalString(row, 'username'),
        ssl_mode: row.ssl_mode,
        allowed_operations: allowedOperations,
        statement_timeout_ms: row.statement_timeout_ms,
        max_rows: row.max_rows,
    };
}

export const datasourcesResource = createResourceCollection({
    name: 'flows/datasources',
    baseUrl: '/flows/api/v1/datasources',
    idField: 'datasource_id',
    operations: ['list', 'get', 'create', 'update', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: {
        list: { method: 'GET', path: '/flows/api/v1/datasources' },
        get: { method: 'GET', path: '/flows/api/v1/datasources/:datasource_id' },
        create: { method: 'POST', path: '/flows/api/v1/datasources' },
        update: { method: 'PATCH', path: '/flows/api/v1/datasources/:datasource_id' },
        remove: { method: 'DELETE', path: '/flows/api/v1/datasources/:datasource_id' },
    },
    mapItem: mapDatasourceConnection,
    toastKeys: {
        create: 'flows:toast.datasource_created',
        create_error: 'flows:toast.datasource_create_error',
        update: 'flows:toast.datasource_updated',
        update_error: 'flows:toast.datasource_update_error',
        remove: 'flows:toast.datasource_removed',
        remove_error: 'flows:toast.datasource_remove_error',
    },
});

export const datasourceTestOp = createAsyncOp({
    name: 'flows/datasource_test',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/datasources/test_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/datasources/:datasource_id/test' },
});

export const datasourceIntrospectOp = createAsyncOp({
    name: 'flows/datasource_introspect',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/datasources/introspect_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/datasources/:datasource_id/introspect' },
});

export const datasourceQueryOp = createAsyncOp({
    name: 'flows/datasource_query',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/datasources/query_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/datasources/:datasource_id/query' },
});

export const datasourceExecuteOp = createAsyncOp({
    name: 'flows/datasource_execute',
    successToastKey: 'flows:toast.datasource_executed',
    errorToastKey: 'flows:toast.datasource_execute_error',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/datasources/execute_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/datasources/:datasource_id/execute' },
});
