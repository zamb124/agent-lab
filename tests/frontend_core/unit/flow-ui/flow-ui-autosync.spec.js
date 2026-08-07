import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FlowUIAutosync } from '../../../../core/frontend/static/lib/flow-ui/runtime/flow-ui-autosync.js';

describe('FlowUIAutosync', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('coalesces scheduled flushes into one delayed call', async () => {
        const calls = [];
        const autosync = new FlowUIAutosync(async () => {
            calls.push('flush');
        }, 100);
        autosync.schedule();
        autosync.schedule();
        expect(calls).toEqual([]);
        await vi.advanceTimersByTimeAsync(100);
        expect(calls).toEqual(['flush']);
        autosync.dispose();
    });

    it('flushNow cancels debounce and awaits the in-flight flush', async () => {
        const calls = [];
        const autosync = new FlowUIAutosync(async () => {
            calls.push('flush');
        }, 500);
        autosync.schedule();
        await autosync.flushNow();
        expect(calls).toEqual(['flush']);
        await vi.advanceTimersByTimeAsync(500);
        expect(calls).toEqual(['flush']);
        autosync.dispose();
    });

    it('serializes overlapping flush and scheduled flush', async () => {
        let active = 0;
        let maxActive = 0;
        const calls = [];
        const autosync = new FlowUIAutosync(async () => {
            active += 1;
            maxActive = Math.max(maxActive, active);
            calls.push(`start-${calls.length}`);
            await Promise.resolve();
            active -= 1;
        }, 50);
        const first = autosync.flushNow();
        autosync.schedule();
        await vi.advanceTimersByTimeAsync(50);
        await first;
        await autosync.chain;
        expect(maxActive).toBe(1);
        expect(calls.length).toBeGreaterThanOrEqual(1);
        autosync.dispose();
    });

    it('dispose swallows AbortError from in-flight flush', async () => {
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        const autosync = new FlowUIAutosync(async () => {
            await gate;
            throw new DOMException('Aborted', 'AbortError');
        }, 10);
        const pending = autosync.flushNow();
        autosync.dispose();
        release();
        await expect(pending).resolves.toBeUndefined();
        await expect(autosync.chain).resolves.toBeUndefined();
        autosync.schedule();
        await vi.advanceTimersByTimeAsync(20);
        expect(autosync.disposed).toBe(true);
    });
});
