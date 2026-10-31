/**
 * Company variables — команды `secrets/variables/*` владельца secrets (WS + REST-зеркало).
 */

import { createResourceCollection } from '@platform/lib/events/index.js';
import type { ResourceItem } from '../factories/resource-collection.js';
import { isPlainRecord } from '../payload.js';

function requireRecord(raw: unknown, message: string): JsonObject {
    if (!isPlainRecord(raw)) {
        throw new Error(message);
    }
    return raw;
}

type JsonObject = Record<string, unknown>;

export interface PlatformVariableValueSpec {
    value_kind: 'static' | 'expression';
    value: unknown;
    expression: string | null;
}

export interface PlatformVariableScopeOverride {
    value_kind: 'static' | 'expression';
    value: unknown;
    expression: string | null;
    priority: number;
    match: Array<{ field: string; op: string; ref_key: string | null; value: unknown }>;
}

export interface PlatformVariable extends ResourceItem {
    variable_key: string;
    company_id: string;
    version: number;
    payload: { base: PlatformVariableValueSpec; scopes: PlatformVariableScopeOverride[] };
    secret: boolean;
    shared_for_execution: boolean;
    public: boolean;
    created_by: string | null;
    title: string | null;
    description: string;
    order: number | null;
    groups: string[];
    created_at: string | null;
    updated_at: string | null;
}

function _requireString(raw: unknown, field: string): string {
    if (typeof raw !== 'string' || raw.trim() === '') {
        throw new Error(`secrets/variables: ${field} must be non-empty string`);
    }
    return raw;
}

function _mapValueSpec(raw: unknown, field: string): PlatformVariableValueSpec {
    const spec = requireRecord(raw, `secrets/variables: ${field}.base required`);
    const valueKind = spec.value_kind;
    if (valueKind !== 'static' && valueKind !== 'expression') {
        throw new Error(`secrets/variables: ${field}.base.value_kind invalid`);
    }
    return {
        value_kind: valueKind,
        value: spec.value === undefined ? null : spec.value,
        expression: typeof spec.expression === 'string' ? spec.expression : null,
    };
}

function _mapScopeOverride(raw: unknown, index: number): PlatformVariableScopeOverride {
    const scope = requireRecord(raw, `secrets/variables: scopes[${index}] invalid`);
    const matchIn = Array.isArray(scope.match) ? scope.match : [];
    const match = matchIn.map((entry: unknown, matchIndex: number) => {
        const e = requireRecord(entry, `secrets/variables: scopes[${index}].match[${matchIndex}] invalid`);
        return {
            field: _requireString(e.field, `scopes[${index}].match[${matchIndex}].field`),
            op: typeof e.op === 'string' ? e.op : 'eq',
            ref_key: typeof e.ref_key === 'string' ? e.ref_key : null,
            value: e.value === undefined ? null : e.value,
        };
    });
    return {
        value_kind: scope.value_kind === 'expression' ? 'expression' : 'static',
        value: scope.value === undefined ? null : scope.value,
        expression: typeof scope.expression === 'string' ? scope.expression : null,
        priority: typeof scope.priority === 'number' ? scope.priority : 0,
        match,
    };
}

export function mapPlatformVariable(raw: unknown): PlatformVariable {
    const v = requireRecord(raw, 'secrets/variables.mapItem: payload must be object');
    const variableKey = _requireString(v.variable_key, 'variable_key');
    const pv = requireRecord(v.payload, `secrets/variables: ${variableKey}.payload required`);
    const scopesIn = Array.isArray(pv.scopes) ? pv.scopes : [];
    const scopes = scopesIn.map((scope: unknown, index: number) => _mapScopeOverride(scope, index));
    return {
        variable_key: variableKey,
        company_id: _requireString(v.company_id, 'company_id'),
        version: typeof v.version === 'number' ? v.version : 1,
        payload: {
            base: _mapValueSpec(pv.base, `${variableKey}.payload.base`),
            scopes,
        },
        secret: Boolean(v.secret),
        shared_for_execution: Boolean(v.shared_for_execution),
        public: Boolean(v.public),
        created_by: typeof v.created_by === 'string' ? v.created_by : null,
        title: typeof v.title === 'string' ? v.title : null,
        description: typeof v.description === 'string' ? v.description : '',
        order: typeof v.order === 'number' ? v.order : null,
        groups: Array.isArray(v.groups) ? v.groups.filter((g): g is string => typeof g === 'string') : [],
        created_at: typeof v.created_at === 'string' ? v.created_at : null,
        updated_at: typeof v.updated_at === 'string' ? v.updated_at : null,
    };
}

export const secretsVariablesResource = createResourceCollection<ReturnType<typeof mapPlatformVariable>>({
    name: 'secrets/variables',
    baseUrl: '/secrets/api/v1/variables',
    idField: 'variable_key',
    itemPathTemplate: '/secrets/api/v1/variables/:variable_key',
    buildItemUrl: (id) => `/secrets/api/v1/variables/${encodeURIComponent(id)}`,
    operations: ['list', 'get', 'create', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    mapItem: mapPlatformVariable,
    toastKeys: {
        create: 'company_variables:toast.created',
        create_error: 'company_variables:toast.create_error',
        remove: 'company_variables:toast.removed',
        remove_error: 'company_variables:toast.remove_error',
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'secrets/variables': typeof secretsVariablesResource;
    }
}
