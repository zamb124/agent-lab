/**
 * voice-agent-bridge — мост voice WS ↔ A2A SSE.
 *
 * Проверяется:
 *  - на финальный `transcript{final:true}` от VoiceMediaSession bridge
 *    отправляет `SendStreamingMessage` в A2A через consumeA2AStream (a2a/a2a-stream.js);
 *  - speakable `TaskArtifactUpdateEvent` → `feedStreamTtsFromA2aResult` + registry → `mediaSession.speak`;
 *  - финальный `statusUpdate`: текст в `status.message` при `TASK_STATE_INPUT_REQUIRED` / `metadata.platform_interrupt`
 *    → `speak` (interrupt ask_user и т.п.), затем `endUtterance`; иначе только `endUtterance`;
 *  - `vad{state:"started"}` с ≥ ~300 мс непрерывной речи (до `ended`) во время
 *    активного A2A fetch и/или TTS → `mediaSession.stopPlayback()`, `abort`, `CancelTask`;
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const streamMock = vi.fn();

vi.mock('@platform/lib/a2a/a2a-stream.js', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@platform/lib/a2a/a2a-stream.js')>();
    return {
        ...actual,
        consumeA2AStream: (options: unknown, onFrame: (frame: { result: Record<string, unknown> }) => void) => streamMock(options, onFrame),
    };
});

import { VoiceAgentBridge } from '@platform/lib/voice/voice-agent-bridge.js';
import { dig, prop } from '../../helpers/prop.js';
import {
    clearStreamTtsTarget,
    feedStreamTtsFromA2aResult,
    setStreamTtsTarget,
} from '@platform/lib/voice/stream-tts-registry.js';

interface SpokenCall {
    text: string;
    opts: unknown;
}

class FakeMediaSession extends EventTarget {
    spoken: SpokenCall[] = [];
    endUtteranceCount = 0;
    stopPlaybackCount = 0;
    speak(text: string, opts?: unknown) { this.spoken.push({ text, opts }); }
    endUtterance() { this.endUtteranceCount += 1; }
    stopPlayback() { this.stopPlaybackCount += 1; }
}

function emitTranscript(mediaSession: EventTarget, text: string, final = true) {
    mediaSession.dispatchEvent(
        new CustomEvent('transcript', { detail: { text, final, language: 'ru' } })
    );
}
function emitVad(mediaSession: EventTarget, state: string) {
    mediaSession.dispatchEvent(new CustomEvent('vad', { detail: { state } }));
}
function emitTts(mediaSession: EventTarget, state: string) {
    mediaSession.dispatchEvent(new CustomEvent('ttsState', { detail: { state } }));
}

let originalFetch: typeof fetch;
beforeEach(() => {
    streamMock.mockReset();
    originalFetch = globalThis.fetch;
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) })));
});
afterEach(() => {
    vi.stubGlobal('fetch', originalFetch);
    clearStreamTtsTarget();
});

/**
 * Имитация relay после `_handleA2AEvent`: тот же кадр уходит в `feedStreamTtsFromA2aResult`.
 * @param {(frame: object) => void} onEv
 * @param {object} frame
 */
function relayVoiceStreamFrame(onEv: (frame: { result: Record<string, unknown> }) => void, frame: { result: Record<string, unknown> }) {
    onEv(frame);
    feedStreamTtsFromA2aResult(frame.result);
}

describe('VoiceAgentBridge: construction', () => {
    it('требует mediaSession', () => {
        expect(() => Reflect.construct(VoiceAgentBridge, [{ a2aBaseUrl: 'https://h/flows', flowId: 'f1' }])).toThrow(
            /mediaSession required/
        );
    });

    it('требует a2aBaseUrl', () => {
        expect(() => Reflect.construct(VoiceAgentBridge, [{ mediaSession: new FakeMediaSession(), flowId: 'f1' }])).toThrow(
            /a2aBaseUrl required/
        );
    });

    it('требует flowId или embedId', () => {
        expect(() => Reflect.construct(VoiceAgentBridge, [{
            mediaSession: new FakeMediaSession(),
            a2aBaseUrl: 'https://h/flows',
        }])).toThrow(/flowId or embedId required/);
    });
});

describe('VoiceAgentBridge: userStopActiveTurn', () => {
    it('вызывает stopPlayback и прерывает A2A fetch, шлёт CancelTask', async () => {
        let signal: AbortSignal | null = null;
        streamMock.mockImplementation(async (opts, onEvent) => {
            if (opts.signal === undefined) {
                throw new Error('opts.signal required');
            }
            signal = opts.signal;
            onEvent({ result: { task: { id: 'tid-user-stop' } } });
            await new Promise((_res, rej) => {
                opts.signal?.addEventListener('abort', () =>
                    rej(new DOMException('aborted', 'AbortError'))
                );
            });
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        emitTranscript(media, 'q', true);
        await Promise.resolve();
        if (!signal) {
            throw new Error('expected stream signal');
        }
        bridge.userStopActiveTurn();
        await Promise.resolve();
        expect(media.stopPlaybackCount).toBe(1);
        expect(prop(signal, 'aborted')).toBe(true);
        expect(globalThis.fetch).toHaveBeenCalled();
    });
});

describe('VoiceAgentBridge: voice → flows', () => {
    it('на transcript{final:true} вызывает consumeA2AStream с текстом', async () => {
        streamMock.mockResolvedValue(undefined);
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();

        const userMsgs: unknown[] = [];
        bridge.addEventListener('userMessage', (e: Event) => userMsgs.push(prop(e, 'detail')));

        emitTranscript(media, '  Привет агент.  ', true);
        await Promise.resolve();

        expect(userMsgs).toEqual([{ text: 'Привет агент.' }]);
        expect(streamMock).toHaveBeenCalledTimes(1);
        const [opts] = streamMock.mock.calls[0] ?? [];
        expect(prop(opts, 'url')).toBe('https://h/flows/api/v1/flow-1');
        expect(dig(opts, 'body', 'method')).toBe('SendStreamingMessage');
        expect(dig(opts, 'body', 'params', 'message', 'parts', '0')).toEqual({ text: 'Привет агент.' });
        expect(dig(opts, 'body', 'params', 'message', 'role')).toBe('ROLE_USER');
        expect(prop(opts, 'signal')).toBeInstanceOf(AbortSignal);
    });

    it('transcript{final:false} без stop не отправляет stream', async () => {
        streamMock.mockResolvedValue(undefined);
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();

        emitTranscript(media, 'частичный', false);
        emitTranscript(media, '   ', true);
        await Promise.resolve();
        expect(streamMock).not.toHaveBeenCalled();
    });

    it('stop после transcript{final:false} отправляет накопленный текст', async () => {
        streamMock.mockResolvedValue(undefined);
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();

        const userMsgs: unknown[] = [];
        bridge.addEventListener('userMessage', (e: Event) => userMsgs.push(prop(e, 'detail')));

        emitTranscript(media, '  сказано до выключения микрофона  ', false);
        bridge.stop();
        await Promise.resolve();
        await Promise.resolve();

        expect(userMsgs).toEqual([{ text: 'сказано до выключения микрофона' }]);
        expect(streamMock).toHaveBeenCalledTimes(1);
        const [opts] = streamMock.mock.calls[0] ?? [];
        expect(dig(opts, 'body', 'params', 'message', 'parts', '0')).toEqual({
            text: 'сказано до выключения микрофона',
        });
    });
});

describe('VoiceAgentBridge: flows → voice', () => {
    it('speakable artifactUpdate → mediaSession.speak', async () => {
        /** @type {(ev:any)=>void} */
        let capturedOnEvent = () => {};
        streamMock.mockImplementation(async (_opts, onEvent) => {
            capturedOnEvent = onEvent;
            await new Promise(() => {});
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        Reflect.apply(setStreamTtsTarget, null, [media, () => true]);
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();

        relayVoiceStreamFrame(capturedOnEvent, {
            result: {
                task: {
                    id: 'task-1',
                    contextId: 'ctx-1',
                },
            },
        });
        relayVoiceStreamFrame(capturedOnEvent, {
            result: {
                artifactUpdate: {
                    taskId: 'task-1',
                    artifact: {
                        name: 'response',
                        parts: [{ text: 'Ответ агента.' }],
                    },
                    lastChunk: false,
                },
            },
        });

        expect(media.spoken).toEqual([
            { text: 'Ответ агента.', opts: { final: false } },
        ]);
    });

    it('artifactUpdate reasoning — не вызывает speak', async () => {
        /** @type {(ev:any)=>void} */
        let capturedOnEvent = () => {};
        streamMock.mockImplementation(async (_opts, onEvent) => {
            capturedOnEvent = onEvent;
            await new Promise(() => {});
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        Reflect.apply(setStreamTtsTarget, null, [media, () => true]);
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();

        relayVoiceStreamFrame(capturedOnEvent, {
            result: {
                artifactUpdate: {
                    taskId: 'task-1',
                    artifact: {
                        name: 'reasoning',
                        parts: [{ text: 'Шаг размышления.' }],
                    },
                    lastChunk: false,
                },
            },
        });

        expect(media.spoken).toEqual([]);
    });

    it('getTtsOutputEnabled:false — speakable artifact не вызывает speak', async () => {
        let capturedOnEvent = () => {};
        streamMock.mockImplementation(async (_opts, onEvent) => {
            capturedOnEvent = onEvent;
            await new Promise(() => {});
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        Reflect.apply(setStreamTtsTarget, null, [media, () => false]);
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();

        relayVoiceStreamFrame(capturedOnEvent, {
            result: {
                artifactUpdate: {
                    taskId: 'task-1',
                    artifact: {
                        name: 'response',
                        parts: [{ text: 'Ответ агента.' }],
                    },
                    lastChunk: false,
                },
            },
        });

        expect(media.spoken).toEqual([]);
    });

    it('statusUpdate completed → mediaSession.endUtterance', async () => {
        let capturedOnEvent = () => {};
        streamMock.mockImplementation(async (_opts, onEvent) => {
            capturedOnEvent = onEvent;
            await new Promise(() => {});
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        Reflect.apply(setStreamTtsTarget, null, [media, () => true]);
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();

        relayVoiceStreamFrame(capturedOnEvent, {
            result: {
                statusUpdate: {
                    taskId: 'task-1',
                    status: { state: 'TASK_STATE_COMPLETED' },
                },
            },
        });

        expect(media.endUtteranceCount).toBe(1);
    });

    it('statusUpdate INPUT_REQUIRED с текстом в status.message → speak + endUtterance', async () => {
        let capturedOnEvent = () => {};
        streamMock.mockImplementation(async (_opts, onEvent) => {
            capturedOnEvent = onEvent;
            await new Promise(() => {});
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        Reflect.apply(setStreamTtsTarget, null, [media, () => true]);
        emitTranscript(media, 'чем?', true);
        await Promise.resolve();

        relayVoiceStreamFrame(capturedOnEvent, {
            result: {
                statusUpdate: {
                    taskId: 'task-1',
                    metadata: {
                        platform_interrupt: {
                            body: { kind: 'user_message', question: 'Я вижу…' },
                            system: {},
                        },
                    },
                    status: {
                        state: 'TASK_STATE_INPUT_REQUIRED',
                        message: {
                            role: 'ROLE_AGENT',
                            parts: [{ text: 'Я вижу, ваше сообщение обрезалось. Чем помочь?' }],
                        },
                    },
                },
            },
        });

        expect(media.spoken).toEqual([
            { text: 'Я вижу, ваше сообщение обрезалось. Чем помочь?', opts: { final: true } },
        ]);
        expect(media.endUtteranceCount).toBe(1);
    });

    it('interrupt statusUpdate при getTtsOutputEnabled:false — без speak, только endUtterance', async () => {
        let capturedOnEvent = () => {};
        streamMock.mockImplementation(async (_opts, onEvent) => {
            capturedOnEvent = onEvent;
            await new Promise(() => {});
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        Reflect.apply(setStreamTtsTarget, null, [media, () => false]);
        emitTranscript(media, 'чем?', true);
        await Promise.resolve();

        relayVoiceStreamFrame(capturedOnEvent, {
            result: {
                statusUpdate: {
                    taskId: 'task-1',
                    status: {
                        state: 'TASK_STATE_INPUT_REQUIRED',
                        message: {
                            parts: [{ text: 'Вопрос пользователю.' }],
                        },
                    },
                },
            },
        });

        expect(media.spoken).toEqual([]);
        expect(media.endUtteranceCount).toBe(1);
    });

    it('не-speakable artifact (thinking) — speak не вызывается', async () => {
        let capturedOnEvent = () => {};
        streamMock.mockImplementation(async (_opts, onEvent) => {
            capturedOnEvent = onEvent;
            await new Promise(() => {});
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        Reflect.apply(setStreamTtsTarget, null, [media, () => true]);
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();

        relayVoiceStreamFrame(capturedOnEvent, {
            result: {
                artifactUpdate: {
                    taskId: 'task-1',
                    artifact: {
                        name: 'thinking',
                        parts: [{ text: 'скрытый ход мысли' }],
                    },
                },
            },
        });

        expect(media.spoken).toEqual([]);
    });
});

describe('VoiceAgentBridge: barge-in', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('vad started во время TTS после порога речи → stopPlayback + abort + CancelTask', async () => {
        let abortedSignal: AbortSignal | null = null;
        streamMock.mockImplementation(async (opts: { signal?: AbortSignal }) => {
            if (opts.signal === undefined) {
                throw new Error('opts.signal required');
            }
            abortedSignal = opts.signal;
            await new Promise((_res, rej) => {
                opts.signal?.addEventListener('abort', () => {
                    const err = new DOMException('aborted', 'AbortError');
                    rej(err);
                });
            });
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();

        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();
        await Promise.resolve();
        expect(streamMock).toHaveBeenCalledTimes(1);

        Reflect.set(bridge, '_currentTaskId', 'task-active-1');
        emitTts(media, 'playing');
        emitVad(media, 'started');
        await vi.advanceTimersByTimeAsync(310);
        await Promise.resolve();

        expect(media.stopPlaybackCount).toBe(1);
        expect(prop(abortedSignal, 'aborted')).toBe(true);
        expect(globalThis.fetch).toHaveBeenCalledTimes(1);
        const [url, init] = vi.mocked(globalThis.fetch).mock.calls[0] ?? [];
        expect(url).toBe('https://h/flows/api/v1/flow-1');
        expect(prop(init, 'method')).toBe('POST');
        const body = JSON.parse(String(prop(init, 'body')));
        expect(body.method).toBe('CancelTask');
        expect(body.params).toEqual({ id: 'task-active-1' });
    });

    it('vad started без активного TTS и без A2A не триггерит barge-in', async () => {
        streamMock.mockImplementation(async () => new Promise(() => {}));
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        emitVad(media, 'started');
        await vi.advanceTimersByTimeAsync(310);
        await Promise.resolve();
        expect(media.stopPlaybackCount).toBe(0);
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });

    it('vad ended до порога сбрасывает ожидание barge-in', async () => {
        let abortedSignal: AbortSignal | null = null;
        streamMock.mockImplementation(async (opts: { signal?: AbortSignal }) => {
            if (opts.signal === undefined) {
                throw new Error('opts.signal required');
            }
            abortedSignal = opts.signal;
            await new Promise((_res, rej) => {
                opts.signal?.addEventListener('abort', () => {
                    const err = new DOMException('aborted', 'AbortError');
                    rej(err);
                });
            });
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();
        emitTts(media, 'playing');
        emitVad(media, 'started');
        await vi.advanceTimersByTimeAsync(100);
        emitVad(media, 'ended');
        await vi.advanceTimersByTimeAsync(400);
        await Promise.resolve();
        expect(media.stopPlaybackCount).toBe(0);
        expect(prop(abortedSignal, 'aborted')).toBe(false);
    });

    it('vad started при активном A2A без TTS после порога → stopPlayback + abort', async () => {
        let abortedSignal: AbortSignal | null = null;
        streamMock.mockImplementation(async (opts: { signal?: AbortSignal }) => {
            if (opts.signal === undefined) {
                throw new Error('opts.signal required');
            }
            abortedSignal = opts.signal;
            await new Promise((_res, rej) => {
                opts.signal?.addEventListener('abort', () => {
                    const err = new DOMException('aborted', 'AbortError');
                    rej(err);
                });
            });
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();
        Reflect.set(bridge, '_currentTaskId', 'task-active-1');
        emitVad(media, 'started');
        await vi.advanceTimersByTimeAsync(310);
        await Promise.resolve();
        expect(media.stopPlaybackCount).toBe(1);
        expect(prop(abortedSignal, 'aborted')).toBe(true);
        expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    });

    it('stop() после финального transcript не абортит активный fetch (снятие эфира)', async () => {
        let signal: AbortSignal | null = null;
        streamMock.mockImplementation(async (opts: { signal?: AbortSignal }) => {
            if (opts.signal === undefined) {
                throw new Error('opts.signal required');
            }
            signal = opts.signal;
            await new Promise((_res, rej) => {
                opts.signal?.addEventListener('abort', () =>
                    rej(new DOMException('aborted', 'AbortError'))
                );
            });
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        emitTranscript(media, 'вопрос.', true);
        await Promise.resolve();
        expect(signal).toBeTruthy();
        expect(prop(signal, 'aborted')).toBe(false);
        bridge.stop();
        expect(prop(signal, 'aborted')).toBe(false);
    });

    it('stop() с частичным transcript прерывает предыдущий fetch через _sendUserMessage', async () => {
        const signals: AbortSignal[] = [];
        streamMock.mockImplementation(async (opts: { signal?: AbortSignal }) => {
            if (opts.signal === undefined) {
                throw new Error('opts.signal required');
            }
            signals.push(opts.signal);
            await new Promise((_res, rej) => {
                opts.signal?.addEventListener('abort', () =>
                    rej(new DOMException('aborted', 'AbortError'))
                );
            });
        });
        const media = new FakeMediaSession();
        const bridge = Reflect.construct(VoiceAgentBridge, [{
            mediaSession: media,
            a2aBaseUrl: 'https://h/flows',
            flowId: 'flow-1',
        }]);
        bridge.start();
        emitTranscript(media, 'первый.', true);
        await Promise.resolve();
        expect(signals.length).toBe(1);
        expect(prop(signals[0], 'aborted')).toBe(false);

        emitTranscript(media, 'коммит при stop', false);
        bridge.stop();
        await Promise.resolve();

        expect(signals.length).toBe(2);
        expect(prop(signals[0], 'aborted')).toBe(true);
        expect(prop(signals[1], 'aborted')).toBe(false);
        expect(dig(streamMock.mock.calls, '1', '0', 'body', 'params', 'message', 'parts', '0', 'text')).toBe('коммит при stop');
    });
});
