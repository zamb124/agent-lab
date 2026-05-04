/**
 * voice-agent-bridge — мост voice WS ↔ A2A SSE.
 *
 * Проверяется:
 *  - на финальный `transcript{final:true}` от VoiceMediaSession bridge
 *    отправляет `message/stream` в A2A через streamEmbedA2A;
 *  - speakable `TaskArtifactUpdateEvent` → `mediaSession.speak(text,...)`;
 *  - `TaskStatusUpdateEvent{final:true}` → `mediaSession.endUtterance()`;
 *  - `vad{state:"started"}` во время TTS → `mediaSession.stopPlayback()`
 *    + `AbortController.abort` над текущим A2A fetch + `tasks/cancel`.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const streamMock = vi.fn();

vi.mock('@platform/lib/embed-chat/embed-a2a-stream.js', () => ({
    streamEmbedA2A: (options, onEvent) => streamMock(options, onEvent),
}));

import { VoiceAgentBridge } from '@platform/lib/voice/voice-agent-bridge.js';

class FakeMediaSession extends EventTarget {
    constructor() {
        super();
        this.spoken = [];
        this.endUtteranceCount = 0;
        this.stopPlaybackCount = 0;
    }
    speak(text, opts) { this.spoken.push({ text, opts }); }
    endUtterance() { this.endUtteranceCount += 1; }
    stopPlayback() { this.stopPlaybackCount += 1; }
}

function emitTranscript(mediaSession, text, final = true) {
    mediaSession.dispatchEvent(
        new CustomEvent('transcript', { detail: { text, final, language: 'ru' } })
    );
}
function emitVad(mediaSession, state) {
    mediaSession.dispatchEvent(new CustomEvent('vad', { detail: { state } }));
}
function emitTts(mediaSession, state) {
    mediaSession.dispatchEvent(new CustomEvent('ttsState', { detail: { state } }));
}

let originalFetch;
beforeEach(() => {
    streamMock.mockReset();
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }));
});
afterEach(() => {
    globalThis.fetch = originalFetch;
});

describe('VoiceAgentBridge: construction', () => {
    it('требует mediaSession', () => {
        expect(() => new VoiceAgentBridge({ a2aBaseUrl: 'https://h/flows', flowId: 'f1' })).toThrow(
            /mediaSession required/
        );
    });

    it('требует a2aBaseUrl', () => {
        expect(() => new VoiceAgentBridge({ mediaSession: new FakeMediaSession(), flowId: 'f1' })).toThrow(
            /a2aBaseUrl required/
        );
    });

    it('требует flowId или embedId', () => {
        expect(() => new VoiceAgentBridge({
            mediaSession: new FakeMediaSession(),
            a2aBaseUrl: 'https://h/flows',
        })).toThrow(/flowId or embedId required/);
    });
});

describe('VoiceAgentBridge: voice → flows', () => {
    it('на transcript{final:true} вызывает streamEmbedA2A с текстом', async () => {
        streamMock.mockResolvedValue(undefined);
        const media = new FakeMediaSession();
        const bridge = new VoiceAgentBridge({
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        });
        bridge.start();

        const userMsgs = [];
        bridge.addEventListener('userMessage', (e) => userMsgs.push(e.detail));

        emitTranscript(media, '  Привет агент.  ', true);
        await Promise.resolve();

        expect(userMsgs).toEqual([{ text: 'Привет агент.' }]);
        expect(streamMock).toHaveBeenCalledTimes(1);
        const [opts] = streamMock.mock.calls[0];
        expect(opts.baseUrl).toBe('https://h/flows');
        expect(opts.flowId).toBe('flow-1');
        expect(opts.message).toBe('Привет агент.');
        expect(opts.signal).toBeInstanceOf(AbortSignal);
    });

    it('игнорирует transcript{final:false} и пустые', async () => {
        streamMock.mockResolvedValue(undefined);
        const media = new FakeMediaSession();
        const bridge = new VoiceAgentBridge({
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        });
        bridge.start();

        emitTranscript(media, 'частичный', false);
        emitTranscript(media, '   ', true);
        await Promise.resolve();
        expect(streamMock).not.toHaveBeenCalled();
    });
});

describe('VoiceAgentBridge: flows → voice', () => {
    it('speakable artifact-update → mediaSession.speak', async () => {
        /** @type {(ev:any)=>void} */
        let capturedOnEvent = () => {};
        streamMock.mockImplementation(async (_opts, onEvent) => {
            capturedOnEvent = onEvent;
            await new Promise(() => {});
        });
        const media = new FakeMediaSession();
        const bridge = new VoiceAgentBridge({
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        });
        bridge.start();
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();

        capturedOnEvent({
            result: {
                kind: 'task',
                id: 'task-1',
                contextId: 'ctx-1',
            },
        });
        capturedOnEvent({
            result: {
                kind: 'artifact-update',
                taskId: 'task-1',
                artifact: {
                    name: 'response',
                    parts: [{ root: { kind: 'text', text: 'Ответ агента.' } }],
                },
                lastChunk: false,
            },
        });

        expect(media.spoken).toEqual([
            { text: 'Ответ агента.', opts: { final: false } },
        ]);
    });

    it('status-update final:true → mediaSession.endUtterance', async () => {
        let capturedOnEvent = () => {};
        streamMock.mockImplementation(async (_opts, onEvent) => {
            capturedOnEvent = onEvent;
            await new Promise(() => {});
        });
        const media = new FakeMediaSession();
        const bridge = new VoiceAgentBridge({
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        });
        bridge.start();
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();

        capturedOnEvent({
            result: { kind: 'status-update', taskId: 'task-1', final: true },
        });

        expect(media.endUtteranceCount).toBe(1);
    });

    it('не-speakable artifact (thinking) — speak не вызывается', async () => {
        let capturedOnEvent = () => {};
        streamMock.mockImplementation(async (_opts, onEvent) => {
            capturedOnEvent = onEvent;
            await new Promise(() => {});
        });
        const media = new FakeMediaSession();
        const bridge = new VoiceAgentBridge({
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        });
        bridge.start();
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();

        capturedOnEvent({
            result: {
                kind: 'artifact-update',
                taskId: 'task-1',
                artifact: {
                    name: 'thinking',
                    parts: [{ root: { kind: 'text', text: 'скрытый ход мысли' } }],
                },
            },
        });

        expect(media.spoken).toEqual([]);
    });
});

describe('VoiceAgentBridge: barge-in', () => {
    it('vad started во время TTS → stopPlayback + abort + tasks/cancel', async () => {
        let abortedSignal = null;
        streamMock.mockImplementation(async (opts) => {
            abortedSignal = opts.signal;
            await new Promise((_res, rej) => {
                opts.signal.addEventListener('abort', () => {
                    const err = new DOMException('aborted', 'AbortError');
                    rej(err);
                });
            });
        });
        const media = new FakeMediaSession();
        const bridge = new VoiceAgentBridge({
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        });
        bridge.start();

        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();
        await Promise.resolve();
        expect(streamMock).toHaveBeenCalledTimes(1);

        bridge._currentTaskId = 'task-active-1';
        emitTts(media, 'playing');
        emitVad(media, 'started');
        await Promise.resolve();
        await Promise.resolve();

        expect(media.stopPlaybackCount).toBe(1);
        expect(abortedSignal.aborted).toBe(true);
        expect(globalThis.fetch).toHaveBeenCalledTimes(1);
        const [url, init] = globalThis.fetch.mock.calls[0];
        expect(url).toBe('https://h/flows/api/v1/flow-1');
        expect(init.method).toBe('POST');
        const body = JSON.parse(init.body);
        expect(body.method).toBe('tasks/cancel');
        expect(body.params).toEqual({ id: 'task-active-1' });
    });

    it('vad started без активного TTS не триггерит barge-in', async () => {
        streamMock.mockImplementation(async () => new Promise(() => {}));
        const media = new FakeMediaSession();
        const bridge = new VoiceAgentBridge({
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        });
        bridge.start();
        emitVad(media, 'started');
        await Promise.resolve();
        expect(media.stopPlaybackCount).toBe(0);
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });

    it('stop() отменяет текущий fetch', async () => {
        let signal = null;
        streamMock.mockImplementation(async (opts) => {
            signal = opts.signal;
            await new Promise((_res, rej) => {
                opts.signal.addEventListener('abort', () =>
                    rej(new DOMException('aborted', 'AbortError'))
                );
            });
        });
        const media = new FakeMediaSession();
        const bridge = new VoiceAgentBridge({
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        });
        bridge.start();
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();
        expect(signal).toBeTruthy();
        expect(signal.aborted).toBe(false);
        bridge.stop();
        expect(signal.aborted).toBe(true);
    });
});
