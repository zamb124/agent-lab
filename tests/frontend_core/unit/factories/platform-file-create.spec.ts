import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    createPlatformFileCreateOp,
    platformFileCreateOp,
} from '@platform/lib/events/factories/platform-file-create.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

beforeEach(() => {
    resetFactories();
});

afterEach(() => {
    resetFactories();
});

describe('createPlatformFileCreateOp', () => {
    it('дефолтное имя platform/file_create', () => {
        expect(platformFileCreateOp.name).toBe('platform/file_create');
        expect(platformFileCreateOp.transport).toBe('http');
    });

    it('кастомное имя', () => {
        const op = createPlatformFileCreateOp({ name: 'svc/file_upload' });
        expect(op.name).toBe('svc/file_upload');
    });

    it('request без File — throw', async () => {
        await expect(platformFileCreateOp.effect(
            {
                type: platformFileCreateOp.events.REQUESTED,
                payload: { spec: '{}' },
                id: 'r1',
                meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null },
            },
            buildCtx(),
        )).rejects.toThrow(/payload.file \(File\) required/);
    });

    it('request без spec — throw', async () => {
        const file = new File([new Uint8Array([1])], 'a.txt', { type: 'text/plain' });
        await expect(platformFileCreateOp.effect(
            {
                type: platformFileCreateOp.events.REQUESTED,
                payload: { file, spec: '' },
                id: 'r2',
                meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null },
            },
            buildCtx(),
        )).rejects.toThrow(/payload.spec \(JSON FileCreateSpec\) required/);
    });
});
