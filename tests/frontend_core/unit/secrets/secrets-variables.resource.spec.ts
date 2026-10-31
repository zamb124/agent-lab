/**
 * secrets-variables.resource.js, secrets-variable-versions, secrets-variables-resolve.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    mapPlatformVariable,
    secretsVariablesResource,
} from '@platform/lib/events/resources/secrets-variables.resource.js';
import { secretsVariableVersionsLoadOp } from '@platform/lib/events/resources/secrets-variable-versions.resource.js';
import { secretsVariablesResolveOp } from '@platform/lib/events/resources/secrets-variables-resolve.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { testEvent } from '../../helpers/bus-fixtures.js';

function isResultPage(v: unknown): v is { items: Array<{ variable_key: string; groups?: string[] }>; total: number } {
    return typeof v === 'object' && v !== null && 'items' in v && 'total' in v;
}
import { prop } from '../../helpers/prop.js';

beforeEach(() => {
    resetFactories();
});
afterEach(() => {
    resetFactories();
});

function minimalVariablePayload(overrides = {}) {
    return {
        variable_key: 'MY_VAR',
        company_id: 'comp1',
        version: 2,
        payload: {
            base: { value_kind: 'static', value: 'hello', expression: null },
            scopes: [
                {
                    value_kind: 'expression',
                    value: null,
                    expression: 'ctx.env',
                    priority: 10,
                    match: [{ field: 'flow_id', op: 'eq', ref_key: 'flow', value: 'f1' }],
                },
            ],
        },
        secret: true,
        shared_for_execution: true,
        public: false,
        created_by: 'user1',
        title: 'Title',
        description: 'Desc',
        order: 5,
        groups: ['g1', 42, 'g2'],
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-02T00:00:00Z',
        ...overrides,
    };
}

describe('mapPlatformVariable', () => {
    it('нормализует полный DTO', () => {
        const mapped = mapPlatformVariable(minimalVariablePayload());
        expect(mapped.variable_key).toBe('MY_VAR');
        expect(mapped.company_id).toBe('comp1');
        expect(mapped.version).toBe(2);
        expect(prop(mapped.payload, 'base')).toEqual({
            value_kind: 'static',
            value: 'hello',
            expression: null,
        });
        expect(prop(mapped.payload, 'scopes')).toHaveLength(1);
        expect(prop(prop(prop(prop(mapped.payload, 'scopes'), '0'), 'match'), '0')).toEqual({
            field: 'flow_id',
            op: 'eq',
            ref_key: 'flow',
            value: 'f1',
        });
        expect(mapped.secret).toBe(true);
        expect(mapped.groups).toEqual(['g1', 'g2']);
    });

    it('expression value_kind в base', () => {
        const mapped = mapPlatformVariable(minimalVariablePayload({
            payload: {
                base: { value_kind: 'expression', expression: '1+1' },
                scopes: [],
            },
        }));
        expect(mapped.payload.base.value_kind).toBe('expression');
        expect(mapped.payload.base.expression).toBe('1+1');
    });

    it('invalid payload — throw', () => {
        expect(() => mapPlatformVariable(null)).toThrow(/payload must be object/);
        expect(() => mapPlatformVariable({ variable_key: 'x', company_id: 'c' })).toThrow(/payload required/);
        expect(() => mapPlatformVariable({
            variable_key: '',
            company_id: 'c',
            payload: { base: { value_kind: 'static', value: 'x' }, scopes: [] },
        })).toThrow(/variable_key/);
        expect(() => mapPlatformVariable({
            variable_key: 'x',
            company_id: 'c',
            payload: { base: { value_kind: 'bad' }, scopes: [] },
        })).toThrow(/value_kind invalid/);
        expect(() => mapPlatformVariable({
            variable_key: 'x',
            company_id: 'c',
            payload: { scopes: [] },
        })).toThrow(/base required/);
        expect(() => mapPlatformVariable({
            variable_key: 'x',
            company_id: 'c',
            payload: { base: { value_kind: 'static', value: 'x' }, scopes: [null] },
        })).toThrow(/scopes\[0\] invalid/);
        expect(() => mapPlatformVariable({
            variable_key: 'x',
            company_id: 'c',
            payload: {
                base: { value_kind: 'static', value: 'x' },
                scopes: [{ match: [null] }],
            },
        })).toThrow(/match\[0\] invalid/);
    });
});

describe('secretsVariablesResource', () => {
    it('WS-команды владельца, restMirror и idField', () => {
        expect(secretsVariablesResource.transport).toBe('ws');
        expect(secretsVariablesResource.idField).toBe('variable_key');
        expect(secretsVariablesResource.events.LIST_REQUESTED).toBe('secrets/variables/list_requested');
        expect(secretsVariablesResource.events.CREATE_REQUESTED).toBe('secrets/variables/create_requested');
        expect(secretsVariablesResource.events.REMOVE_REQUESTED).toBe('secrets/variables/remove_requested');
        expect(secretsVariablesResource.restMirror.list).toEqual({
            method: 'GET',
            path: '/secrets/api/v1/variables',
        });
        expect(secretsVariablesResource.restMirror.get).toEqual({
            method: 'GET',
            path: '/secrets/api/v1/variables/:variable_key',
        });
    });

    it('LIST_LOADED и CREATED мапят items через mapPlatformVariable', () => {
        const raw = minimalVariablePayload();
        const listed = secretsVariablesResource.reducer(secretsVariablesResource.slice.initial, testEvent(secretsVariablesResource.events.LIST_LOADED, { items: [raw], total: 1 }));
        expect(prop(listed.items[0], 'groups')).toEqual(['g1', 'g2']);
        const created = secretsVariablesResource.reducer(listed, testEvent(secretsVariablesResource.events.CREATED, { item: minimalVariablePayload({ variable_key: 'NEW_VAR' }) }));
        expect(prop(prop(created.byId, 'NEW_VAR'), 'variable_key')).toBe('NEW_VAR');
        const removed = secretsVariablesResource.reducer(created, testEvent(secretsVariablesResource.events.REMOVED, { variable_key: 'MY_VAR' }));
        expect(removed.items.map((item) => prop(item, 'variable_key'))).toEqual(['NEW_VAR']);
    });
});

describe('secretsVariableVersionsLoadOp', () => {
    it('WS-команда versions с restMirror; slice хранит нормализованную страницу', () => {
        expect(secretsVariableVersionsLoadOp.transport).toBe('ws');
        expect(secretsVariableVersionsLoadOp.commandType).toBe('secrets/variables/versions_requested');
        expect(secretsVariableVersionsLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/secrets/api/v1/variables/:variable_key/versions',
        });
        const raw = minimalVariablePayload({ variable_key: 'V1', version: 3 });
        const state = secretsVariableVersionsLoadOp.reducer(secretsVariableVersionsLoadOp.slice.initial, testEvent(secretsVariableVersionsLoadOp.events.SUCCEEDED, { result: { items: [raw], total: 1, limit: 50, offset: 0 }, request: { variable_key: 'V1' } }));
        const result = state.lastResult;
        if (!isResultPage(result)) throw new Error('lastResult page expected');
        expect(result.items[0]?.variable_key).toBe('V1');
        expect(result.items[0]?.groups).toEqual(['g1', 'g2']);
        expect(result.total).toBe(1);
    });

    it('невалидный result — throw', () => {
        expect(() => secretsVariableVersionsLoadOp.reducer(secretsVariableVersionsLoadOp.slice.initial, testEvent(secretsVariableVersionsLoadOp.events.SUCCEEDED, { result: { total: 0 }, request: { variable_key: 'K' } }))).toThrow(/OffsetPage result required/);
    });
});

describe('secretsVariablesResolveOp', () => {
    it('WS-команда resolve с restMirror', () => {
        expect(secretsVariablesResolveOp.transport).toBe('ws');
        expect(secretsVariablesResolveOp.commandType).toBe('secrets/variables/resolve_requested');
        expect(secretsVariablesResolveOp.restMirror).toEqual({
            method: 'POST',
            path: '/secrets/api/v1/variables/resolve',
        });
    });
});
