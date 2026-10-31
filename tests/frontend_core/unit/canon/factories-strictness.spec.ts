/**
 * Канон-тест строгости фабрик: невалидный конфиг = throw на старте, никаких
 * молчаливых дефолтов и фолбеков.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createAsyncOp } from '@platform/lib/events/factories/async-op.js';
import { createResourceCollection } from '@platform/lib/events/factories/resource-collection.js';
import { createCursorList } from '@platform/lib/events/factories/cursor-list.js';
import { createFacets } from '@platform/lib/events/factories/facets.js';
import { createForm } from '@platform/lib/events/factories/form.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

beforeEach(() => resetFactories());
afterEach(() => resetFactories());

describe('canon: factory strictness', () => {
    it('createAsyncOp без options — throw', () => {
        expect(() => createAsyncOp()).toThrow();
        expect(() => createAsyncOp(null)).toThrow();
    });

    it('createAsyncOp HTTP без request — throw', () => {
        expect(() => createAsyncOp({ name: 'svc/x', silent: true })).toThrow(/request/);
    });

    it('createAsyncOp WS без wsTimeoutMs — throw', () => {
        expect(() => createAsyncOp({
            name: 'svc/x', silent: true, transport: 'ws',
            restMirror: { method: 'POST', path: '/api/x' },
        })).toThrow(/wsTimeoutMs/);
    });

    it('createAsyncOp WS без restMirror — throw', () => {
        expect(() => createAsyncOp({
            name: 'svc/x', silent: true, transport: 'ws', wsTimeoutMs: 100,
        })).toThrow(/restMirror/);
    });

    it('createAsyncOp дубль name — throw', () => {
        createAsyncOp({ name: 'svc/dup', silent: true, request: async () => ({}) });
        expect(() => createAsyncOp({ name: 'svc/dup', silent: true, request: async () => ({}) })).toThrow(/already/);
    });

    it('createResourceCollection без baseUrl/idField — throw', () => {
        expect(() => createResourceCollection({ name: 'svc/x' })).toThrow(/baseUrl/);
        expect(() => createResourceCollection({ name: 'svc/x', baseUrl: '/x' })).toThrow(/idField/);
    });

    it('createResourceCollection без toastKeys.create — throw', () => {
        expect(() => createResourceCollection({
            name: 'svc/x', baseUrl: '/x', idField: 'id',
            operations: ['list', 'create'],
            toastKeys: {},
        })).toThrow(/toastKeys.create/);
    });

    it('createCursorList без pageSize — throw', () => {
        expect(() => createCursorList({ name: 'svc/x', baseUrl: '/x', buildQuery: () => ({}) })).toThrow(/pageSize/);
    });

    it('createCursorList restMirror.method не из (GET, POST) — throw', () => {
        // Канон cursor-lists read-only: разрешены GET (по умолчанию) и POST
        // (для CRM search-операций с большими query). PATCH/PUT/DELETE — throw.
        expect(() => createCursorList({
            name: 'svc/x', baseUrl: '/x', buildQuery: () => ({}), pageSize: 50,
            restMirror: { method: 'PATCH', path: '/x' },
        })).toThrow(/GET|POST/);
    });

    it('createFacets без debounceMs/minQueryLength — throw', () => {
        expect(() => createFacets({ name: 'svc/x', baseUrl: '/x', facets: { a: 'a' }, minQueryLength: 0 })).toThrow(/debounceMs/);
        expect(() => createFacets({ name: 'svc/x', baseUrl: '/x', facets: { a: 'a' }, debounceMs: 0 })).toThrow(/minQueryLength/);
    });

    it('createForm без submitEvent — throw', () => {
        expect(() => createForm({ name: 'svc/x', schema: { a: {} }, initial: { a: '' } })).toThrow(/submitEvent/);
    });

    it('createForm: каждое поле schema должно быть в initial — throw', () => {
        expect(() => createForm({
            name: 'svc/x',
            schema: { name: {}, email: {} },
            initial: { name: '' },
            submitEvent: 'svc/x/y',
        })).toThrow(/initial.email/);
    });

    it('имя фабрики должно быть scope/entity', () => {
        const tests = ['just_one', 'three/segments/here', 'Caps/no', 'foo-bar/x'];
        for (const bad of tests) {
            expect(() => createAsyncOp({ name: bad, silent: true, request: async () => ({}) })).toThrow();
        }
    });
});
