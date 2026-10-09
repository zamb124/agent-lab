/**
 * Единая клиентская логика авто-TTS из кадра A2A SSE (`frame.result`).
 * Артефакты — контракт `speakable.js` / `speakable.py`. Interrupted `statusUpdate`
 * с текстом в `status.message` (ask_user / platform interrupt) — только на клиенте:
 * сервер не дублирует этот текст артефактом `response`.
 */

import { isInterruptedTaskState, isSettledTaskState, unwrapA2aStreamResult } from '../flow-ui/protocol/a2a-stream.js';
import { extractSpeakableText } from './speakable.js';
import type { VoiceMediaSession } from './voice-media-session.js';

/**
 * Текст для TTS из interrupted `TaskStatusUpdateEvent`, когда ответ пользователю
 * в `status.message.parts` (ask_user / platform interrupt), а не в whitelisted артефакте.
 *
 * @param {object} statusUpdate — `result.statusUpdate` (A2A 1.0).
 * @returns {string|null}
 */
export function extractSpeakableTextFromFinalStatusUpdate(statusUpdate: unknown): string | null {
    if (statusUpdate === null || typeof statusUpdate !== 'object') {
        return null;
    }
    const update = statusUpdate as Record<string, unknown>;
    const status = update.status;
    if (status === null || typeof status !== 'object') {
        return null;
    }
    const statusRecord = status as Record<string, unknown>;
    const taskState = typeof statusRecord.state === 'string' ? statusRecord.state : '';
    const meta = update.metadata;
    const hasInterruptMeta =
        meta !== null &&
        typeof meta === 'object' &&
        'platform_interrupt' in meta &&
        (meta as Record<string, unknown>).platform_interrupt != null;
    if (!isInterruptedTaskState(taskState) && !hasInterruptMeta) {
        return null;
    }
    const message = statusRecord.message;
    if (message === null || typeof message !== 'object') {
        return null;
    }
    const parts = Array.isArray((message as Record<string, unknown>).parts)
        ? (message as Record<string, unknown>).parts as unknown[]
        : [];
    const chunks: string[] = [];
    for (const part of parts) {
        if (part === null || typeof part !== 'object') {
            continue;
        }
        // A2A 1.0 Part: presence `text`, без kind / nested root
        const text = (part as Record<string, unknown>).text;
        if (typeof text === 'string' && text !== '') {
            chunks.push(text);
        }
    }
    if (chunks.length === 0) {
        return null;
    }
    const joined = chunks.join('');
    return joined === '' ? null : joined;
}

/**
 * @param {import('./voice-media-session.js').VoiceMediaSession} media
 * @param {object} result — `frame.result` из JSON-RPC по SSE (StreamResponse 1.0).
 * @param {() => boolean} getTtsOutputEnabled
 */
export function feedSpeakableTtsFromA2aResult(
    media: VoiceMediaSession | null,
    result: object | null | undefined,
    getTtsOutputEnabled: () => boolean,
): void {
    if (!media || result === null || typeof result !== 'object') {
        return;
    }
    const unwrapped = unwrapA2aStreamResult(result);
    if (!unwrapped) {
        return;
    }

    if (unwrapped.frameKind === 'artifactUpdate') {
        const text = extractSpeakableText(unwrapped.event);
        if (text === null) {
            return;
        }
        if (!getTtsOutputEnabled()) {
            return;
        }
        media.speak(text, { final: unwrapped.event.lastChunk === true });
        return;
    }

    if (unwrapped.frameKind === 'statusUpdate') {
        const status = unwrapped.event.status as Record<string, unknown> | undefined;
        const state =
            status && typeof status.state === 'string'
                ? status.state
                : '';
        if (!isSettledTaskState(state)) {
            return;
        }
        if (getTtsOutputEnabled()) {
            const interruptText = extractSpeakableTextFromFinalStatusUpdate(unwrapped.event);
            if (interruptText !== null) {
                media.speak(interruptText, { final: true });
            }
        }
        media.endUtterance();
    }
}
