/**
 * secrets-variables.resource.js, secrets-variable-versions, secrets-variables-resolve.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { CoreEvents } from '@platform/lib/events/contract.js';
import {
    mapPlatformVariable,
    secretsVariablesResource,
} from '@platform/lib/events/resources/secrets-variables.resource.js';
import { secretsVariableVersionsLoadOp } from '@platform/lib/events/resources/secrets-variable-versions.resource.js';
import { secretsVariablesResolveOp } from '@platform/lib/events/resources/secrets-variables-resolve.resource.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

let fetchMock;

beforeEach(() => {
    resetFactories();
    fetchMock = installFetchMock();
});
afterEach(() => {
    fetchMock.uninstall();
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
        expect(mapped.payload.base).toEqual({
            value_kind: 'static',
            value: 'hello',
            expression: null,
        });
        expect(mapped.payload.scopes).toHaveLength(1);
        expect(mapped.payload.scopes[0].match[0]).toEqual({
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
    it('restMirror и idField', () => {
        expect(secretsVariablesResource.idField).toBe('variable_key');
        expect(secretsVariablesResource.restMirror.list).toEqual({
            method: 'GET',
            path: '/secrets/api/v1/variables',
        });
        expect(secretsVariablesResource.restMirror.get).toEqual({
            method: 'GET',
            path: '/secrets/api/v1/variables/:variable_key',
        });
    });

    it('LIST_REQUESTED мапит items', async () => {
        const raw = minimalVariablePayload();
        fetchMock.respondJson('GET', '/secrets/api/v1/variables?limit=200', { items: [raw] });
        const dispatched = [];
        await secretsVariablesResource.effect(
            {
                type: secretsVariablesResource.events.LIST_REQUESTED,
                payload: null,
                id: 'l1',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );
        const loaded = dispatched.find((d) => d.type === secretsVariablesResource.events.LIST_LOADED);
        expect(loaded.payload.items[0].variable_key).toBe('MY_VAR');
    });

    it('GET_REQUESTED мапит item', async () => {
        const raw = minimalVariablePayload({ variable_key: 'GET_ME' });
        fetchMock.respondJson('GET', '/secrets/api/v1/variables/GET_ME', raw);
        const dispatched = [];
        await secretsVariablesResource.effect(
            {
                type: secretsVariablesResource.events.ITEM_REQUESTED,
                payload: { variable_key: 'GET_ME' },
                id: 'g1',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );
        const loaded = dispatched.find((d) => d.type === secretsVariablesResource.events.ITEM_LOADED);
        expect(loaded.payload.item.variable_key).toBe('GET_ME');
    });

    it('CREATE_REQUESTED → CREATED + toast', async () => {
        const raw = minimalVariablePayload({ variable_key: 'NEW_VAR' });
        fetchMock.respondJson('POST', '/secrets/api/v1/variables', raw);
        const dispatched = [];
        await secretsVariablesResource.effect(
            {
                type: secretsVariablesResource.events.CREATE_REQUESTED,
                payload: raw,
                id: 'c1',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );
        const created = dispatched.find((d) => d.type === secretsVariablesResource.events.CREATED);
        expect(created.payload.item.variable_key).toBe('NEW_VAR');
        const toast = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(toast.payload.i18n_key).toBe('company_variables:toast.created');
    });

    it('REMOVE_REQUESTED → REMOVED + toast', async () => {
        fetchMock.respondStatus('DELETE', '/secrets/api/v1/variables/DEL_ME', 204);
        fetchMock.respondJson('GET', '/secrets/api/v1/variables?limit=200', { items: [] });
        const dispatched = [];
        await secretsVariablesResource.effect(
            {
                type: secretsVariablesResource.events.REMOVE_REQUESTED,
                payload: { variable_key: 'DEL_ME' },
                id: 'r1',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );
        const removed = dispatched.find((d) => d.type === secretsVariablesResource.events.REMOVED);
        expect(removed.payload.variable_key).toBe('DEL_ME');
        const toast = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(toast.payload.i18n_key).toBe('company_variables:toast.removed');
    });
});

describe('secretsVariableVersionsLoadOp', () => {
    it('restMirror и успешная загрузка', async () => {
        expect(secretsVariableVersionsLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/secrets/api/v1/variables/:variable_key/versions',
        });
        const raw = minimalVariablePayload({ variable_key: 'V1', version: 3 });
        fetchMock.respondJson(
            'GET',
            '/secrets/api/v1/variables/V1/versions?limit=50&offset=0',
            { items: [raw], total: 1, limit: 50, offset: 0 },
        );
        const dispatched = [];
        await secretsVariableVersionsLoadOp.effect(
            {
                type: secretsVariableVersionsLoadOp.events.REQUESTED,
                payload: { variable_key: 'V1' },
                id: 'v1',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );
        const ok = dispatched.find((d) => d.type === secretsVariableVersionsLoadOp.events.SUCCEEDED);
        expect(ok.payload.result.items[0].variable_key).toBe('V1');
        expect(ok.payload.result.total).toBe(1);
    });

    it('кастомные limit/offset в URL', async () => {
        fetchMock.respondJson(
            'GET',
            '/secrets/api/v1/variables/K/versions?limit=10&offset=5',
            { items: [], total: 0, limit: 10, offset: 5 },
        );
        const dispatched = [];
        await secretsVariableVersionsLoadOp.effect(
            {
                type: secretsVariableVersionsLoadOp.events.REQUESTED,
                payload: { variable_key: 'K', limit: 10, offset: 5 },
                id: 'v2',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );
        expect(fetchMock.calls[0].url).toBe('/secrets/api/v1/variables/K/versions?limit=10&offset=5');
        const ok = dispatched.find((d) => d.type === secretsVariableVersionsLoadOp.events.SUCCEEDED);
        expect(ok.payload.result.items).toEqual([]);
    });

    it('ошибки валидации payload и response', async () => {
        await expect(
            secretsVariableVersionsLoadOp.effect(
                {
                    type: secretsVariableVersionsLoadOp.events.REQUESTED,
                    payload: null,
                    id: 'e1',
                    meta: {},
                },
                buildCtx(() => ({}), []),
            ),
        ).rejects.toThrow(/payload required/);

        await expect(
            secretsVariableVersionsLoadOp.effect(
                {
                    type: secretsVariableVersionsLoadOp.events.REQUESTED,
                    payload: { variable_key: '  ' },
                    id: 'e2',
                    meta: {},
                },
                buildCtx(() => ({}), []),
            ),
        ).rejects.toThrow(/variable_key required/);

        fetchMock.respondJson('GET', '/secrets/api/v1/variables/BAD/versions?limit=50&offset=0', {});
        await expect(
            secretsVariableVersionsLoadOp.effect(
                {
                    type: secretsVariableVersionsLoadOp.events.REQUESTED,
                    payload: { variable_key: 'BAD' },
                    id: 'e3',
                    meta: {},
                },
                buildCtx(() => ({}), []),
            ),
        ).rejects.toThrow(/invalid response/);
    });
});

describe('secretsVariablesResolveOp', () => {
    it('restMirror и POST resolve', async () => {
        expect(secretsVariablesResolveOp.restMirror).toEqual({
            method: 'POST',
            path: '/secrets/api/v1/variables/resolve',
        });
        const body = { context: { flow_id: 'f1' }, keys: ['MY_VAR'] };
        fetchMock.respondJson('POST', '/secrets/api/v1/variables/resolve', { MY_VAR: 'resolved' });
        const dispatched = [];
        await secretsVariablesResolveOp.effect(
            {
                type: secretsVariablesResolveOp.events.REQUESTED,
                payload: body,
                id: 'rs1',
                meta: {},
            },
            buildCtx(() => ({}), dispatched),
        );
        const ok = dispatched.find((d) => d.type === secretsVariablesResolveOp.events.SUCCEEDED);
        expect(ok.payload.result).toEqual({ MY_VAR: 'resolved' });
        expect(JSON.parse(fetchMock.calls[0].init.body)).toEqual(body);
    });

    it('payload required', async () => {
        await expect(
            secretsVariablesResolveOp.effect(
                {
                    type: secretsVariablesResolveOp.events.REQUESTED,
                    payload: null,
                    id: 'e1',
                    meta: {},
                },
                buildCtx(() => ({}), []),
            ),
        ).rejects.toThrow(/payload required/);
    });
});
