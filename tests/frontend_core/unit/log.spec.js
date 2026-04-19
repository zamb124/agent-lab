/**
 * EventLog: append-only буфер фиксированной ёмкости + dev-trail.
 */

import { describe, it, expect } from 'vitest';
import { EventLog } from '@platform/lib/events/log.js';

const sampleEvent = (type) => ({ id: type, type, payload: null, meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });

describe('EventLog', () => {
    it('size инкрементируется на каждый append', () => {
        const log = new EventLog();
        log.append(sampleEvent('a/b/c'));
        log.append(sampleEvent('a/b/c'));
        expect(log.size).toBe(2);
        expect(log.bufferLength).toBe(2);
    });

    it('snapshot возвращает копию буфера', () => {
        const log = new EventLog();
        log.append(sampleEvent('a/b/c'));
        const snap = log.snapshot();
        snap.push('mutated');
        expect(log.snapshot()).toHaveLength(1);
    });

    it('snapshot(N) возвращает последние N', () => {
        const log = new EventLog();
        for (let i = 0; i < 5; i += 1) log.append(sampleEvent(`a/b/v${i}`));
        const last3 = log.snapshot(3);
        expect(last3.map((e) => e.type)).toEqual(['a/b/v2', 'a/b/v3', 'a/b/v4']);
    });

    it('кольцевой буфер: при превышении capacity старые вытесняются', () => {
        const log = new EventLog({ capacity: 3 });
        for (let i = 0; i < 5; i += 1) log.append(sampleEvent(`a/b/v${i}`));
        expect(log.size).toBe(5);
        expect(log.bufferLength).toBe(3);
        expect(log.snapshot().map((e) => e.type)).toEqual(['a/b/v2', 'a/b/v3', 'a/b/v4']);
    });

    it('devTrail доступен только при devMode', () => {
        const off = new EventLog({ devMode: false });
        expect(() => off.devTrail()).toThrow(/dev mode/);
        const on = new EventLog({ devMode: true });
        on.append(sampleEvent('a/b/c'));
        expect(on.devTrail()).toHaveLength(1);
    });

    it('devTrail растёт без ограничения capacity', () => {
        const log = new EventLog({ capacity: 2, devMode: true });
        for (let i = 0; i < 10; i += 1) log.append(sampleEvent(`a/b/v${i}`));
        expect(log.bufferLength).toBe(2);
        expect(log.devTrail()).toHaveLength(10);
    });

    it('reset чистит всё', () => {
        const log = new EventLog({ devMode: true });
        log.append(sampleEvent('a/b/c'));
        log.reset();
        expect(log.size).toBe(0);
        expect(log.snapshot()).toEqual([]);
        expect(log.devTrail()).toEqual([]);
    });
});
