/**
 * disposeVoiceMediaThenBridge: шаги завершения идут по порядку, ошибка шага не отменяет следующие
 * и не теряется.
 */

import { describe, expect, it, vi } from 'vitest';
import { disposeVoiceMediaThenBridge } from '@platform/lib/voice/dispose-voice-session.js';

interface Calls {
    order: string[];
}

function fakeMedia(calls: Calls, { connected = true, closeError = null }: { connected?: boolean; closeError?: Error | null } = {}) {
    return {
        isConnected: connected,
        awaitRecordingFinalized: vi.fn(async () => {
            calls.order.push('finalize');
        }),
        close: vi.fn(() => {
            calls.order.push('close');
            if (closeError) throw closeError;
        }),
    };
}

function fakeBridge(calls: Calls, stopError: Error | null = null) {
    return {
        stop: vi.fn(() => {
            calls.order.push('stop');
            if (stopError) throw stopError;
        }),
    };
}

describe('disposeVoiceMediaThenBridge', () => {
    it('сначала flush STT, затем остановка bridge, затем закрытие media', async () => {
        const calls: Calls = { order: [] };
        await disposeVoiceMediaThenBridge(fakeMedia(calls), fakeBridge(calls));
        expect(calls.order).toEqual(['finalize', 'stop', 'close']);
    });

    it('без соединения flush пропускается', async () => {
        const calls: Calls = { order: [] };
        await disposeVoiceMediaThenBridge(fakeMedia(calls, { connected: false }), fakeBridge(calls));
        expect(calls.order).toEqual(['stop', 'close']);
    });

    it('ошибка stop пробрасывается, а media всё равно закрывается', async () => {
        const calls: Calls = { order: [] };
        const failure = new Error('stop failed');
        await expect(disposeVoiceMediaThenBridge(fakeMedia(calls), fakeBridge(calls, failure))).rejects.toBe(failure);
        expect(calls.order).toEqual(['finalize', 'stop', 'close']);
    });

    it('ошибка close пробрасывается', async () => {
        const calls: Calls = { order: [] };
        const failure = new Error('close failed');
        await expect(disposeVoiceMediaThenBridge(fakeMedia(calls, { closeError: failure }), null)).rejects.toBe(failure);
    });

    it('без media и bridge ничего не делает', async () => {
        await expect(disposeVoiceMediaThenBridge(null, null)).resolves.toBeUndefined();
    });
});
