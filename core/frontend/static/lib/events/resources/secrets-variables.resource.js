/**
 * Company variables — канонический REST к secrets-сервису.
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

function _requireString(raw, field) {
    if (typeof raw !== 'string' || raw.trim() === '') {
        throw new Error(`secrets/variables: ${field} must be non-empty string`);
    }
    return raw;
}

function _mapValueSpec(raw, field) {
    if (!raw || typeof raw !== 'object') {
        throw new Error(`secrets/variables: ${field}.base required`);
    }
    const valueKind = raw.value_kind;
    if (valueKind !== 'static' && valueKind !== 'expression') {
        throw new Error(`secrets/variables: ${field}.base.value_kind invalid`);
    }
    return {
        value_kind: valueKind,
        value: raw.value ?? null,
        expression: typeof raw.expression === 'string' ? raw.expression : null,
    };
}

function _mapScopeOverride(raw, index) {
    if (!raw || typeof raw !== 'object') {
        throw new Error(`secrets/variables: scopes[${index}] invalid`);
    }
    const matchIn = Array.isArray(raw.match) ? raw.match : [];
    const match = matchIn.map((entry, matchIndex) => {
        if (!entry || typeof entry !== 'object') {
            throw new Error(`secrets/variables: scopes[${index}].match[${matchIndex}] invalid`);
        }
        return {
            field: _requireString(entry.field, `scopes[${index}].match[${matchIndex}].field`),
            op: typeof entry.op === 'string' ? entry.op : 'eq',
            ref_key: typeof entry.ref_key === 'string' ? entry.ref_key : null,
            value: entry.value ?? null,
        };
    });
    return {
        value_kind: raw.value_kind === 'expression' ? 'expression' : 'static',
        value: raw.value ?? null,
        expression: typeof raw.expression === 'string' ? raw.expression : null,
        priority: typeof raw.priority === 'number' ? raw.priority : 0,
        match,
    };
}

export function mapPlatformVariable(raw) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('secrets/variables.mapItem: payload must be object');
    }
    const variableKey = _requireString(raw.variable_key, 'variable_key');
    const payloadRaw = raw.payload;
    if (!payloadRaw || typeof payloadRaw !== 'object') {
        throw new Error(`secrets/variables: ${variableKey}.payload required`);
    }
    const scopesIn = Array.isArray(payloadRaw.scopes) ? payloadRaw.scopes : [];
    const scopes = scopesIn.map((scope, index) => _mapScopeOverride(scope, index));
    return {
        variable_key: variableKey,
        company_id: _requireString(raw.company_id, 'company_id'),
        version: typeof raw.version === 'number' ? raw.version : 1,
        payload: {
            base: _mapValueSpec(payloadRaw.base, `${variableKey}.payload.base`),
            scopes,
        },
        secret: Boolean(raw.secret),
        shared_for_execution: Boolean(raw.shared_for_execution),
        public: Boolean(raw.public),
        created_by: typeof raw.created_by === 'string' ? raw.created_by : null,
        title: typeof raw.title === 'string' ? raw.title : null,
        description: typeof raw.description === 'string' ? raw.description : '',
        order: typeof raw.order === 'number' ? raw.order : null,
        groups: Array.isArray(raw.groups) ? raw.groups.filter((g) => typeof g === 'string') : [],
        created_at: typeof raw.created_at === 'string' ? raw.created_at : null,
        updated_at: typeof raw.updated_at === 'string' ? raw.updated_at : null,
    };
}

export const secretsVariablesResource = createResourceCollection({
    name: 'secrets/variables',
    baseUrl: '/secrets/api/v1/variables',
    idField: 'variable_key',
    itemPathTemplate: '/secrets/api/v1/variables/:variable_key',
    buildItemUrl: (id) => `/secrets/api/v1/variables/${encodeURIComponent(id)}`,
    operations: ['list', 'get', 'create', 'remove'],
    mapItem: mapPlatformVariable,
    toastKeys: {
        create: 'company_variables:toast.created',
        create_error: 'company_variables:toast.create_error',
        remove: 'company_variables:toast.removed',
        remove_error: 'company_variables:toast.remove_error',
    },
});
