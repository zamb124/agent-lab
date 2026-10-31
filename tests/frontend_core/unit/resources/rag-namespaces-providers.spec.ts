import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    namespaceCreateForm,
    namespacesResource,
} from '@platform/lib/events/resources/rag-namespaces.resource.js';
import { providersResource } from '@platform/lib/events/resources/rag-providers.resource.js';
import { buildCtx, testEvent } from '../../helpers/bus-fixtures.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

beforeEach(() => {
    resetFactories();
});

afterEach(() => {
    resetFactories();
});

describe('rag/namespaces', () => {
    it('WS collection restMirror', () => {
        expect(namespacesResource.transport).toBe('ws');
        expect(namespacesResource.idField).toBe('name');
        expect(namespacesResource.restMirror).toEqual({
            list: { method: 'GET', path: '/rag/api/v1/namespaces' },
            create: { method: 'POST', path: '/rag/api/v1/namespaces' },
            remove: { method: 'DELETE', path: '/rag/api/v1/namespaces/:namespace_id' },
        });
    });

    it('create form submit trim и пустое description → null', () => {
        const opened = namespaceCreateForm.reducer(namespaceCreateForm.slice.initial, testEvent(namespaceCreateForm.events.OPENED, { initial: { name: 'kb-support', description: '  notes  ' } }));
        const dispatched: DispatchedRecord[] = [];
        namespaceCreateForm.effect(
            testEvent(namespaceCreateForm.events.SUBMIT_REQUESTED, null),
            buildCtx(() => ({ [namespaceCreateForm.sliceKey]: opened }), dispatched),
        );
        expect(dispatched[0]?.type).toBe(namespacesResource.events.CREATE_REQUESTED);
        expect(dispatched[0]?.payload).toEqual({
            name: 'kb-support',
            description: 'notes',
        });
    });

    it('create form пустое description становится null', () => {
        const opened = namespaceCreateForm.reducer(namespaceCreateForm.slice.initial, testEvent(namespaceCreateForm.events.OPENED, { initial: { name: 'kb', description: '   ' } }));
        const dispatched: DispatchedRecord[] = [];
        namespaceCreateForm.effect(
            testEvent(namespaceCreateForm.events.SUBMIT_REQUESTED, null),
            buildCtx(() => ({ [namespaceCreateForm.sliceKey]: opened }), dispatched),
        );
        expect(dispatched[0]?.payload).toEqual({ name: 'kb', description: null });
    });
});

describe('rag/providers', () => {
    it('WS restMirror и commandType', () => {
        expect(providersResource.transport).toBe('ws');
        expect(providersResource.commandType).toBe('rag/providers/list_requested');
        expect(providersResource.restMirror).toEqual({
            method: 'GET',
            path: '/rag/api/v1/providers',
        });
    });

    it('SUCCEEDED кладёт items и current_provider', () => {
        const next = providersResource.reducer(providersResource.slice.initial, testEvent(providersResource.events.SUCCEEDED, {
                result: {
                    items: [{ id: 'pgvector' }],
                    current_provider: 'pgvector',
                },
            }));
        expect(next.items).toEqual([{ id: 'pgvector' }]);
        expect(next.current).toBe('pgvector');
    });

    it('SUCCEEDED без items/current_provider — throw', () => {
        expect(() => providersResource.reducer(providersResource.slice.initial, testEvent(providersResource.events.SUCCEEDED, { result: { current_provider: 'pgvector' } }))).toThrow(/result.items must be array/);
        expect(() => providersResource.reducer(providersResource.slice.initial, testEvent(providersResource.events.SUCCEEDED, { result: { items: [], current_provider: 1 } }))).toThrow(/current_provider must be string/);
    });
});
