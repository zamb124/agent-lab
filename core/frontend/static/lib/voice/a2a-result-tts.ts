/**
 * Единая клиентская логика авто-TTS из кадра A2A SSE (`frame.result`).
 * Артефакты — контракт `speakable.js` / `speakable.py`. Interrupted `statusUpdate`
 * с текстом в `status.message` (ask_user / platform interrupt) — только на клиенте:
 * сервер не дублирует этот текст артефактом `response`.
 */

import { isInterruptedTaskState, isSettledTaskState, unwrapA2aStreamResult } from '../flow-ui/protocol/a2a-stream.js';
import { isPlainRecord } from '../events/payload.js';
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
    if (!isPlainRecord(statusUpdate)) {
        return null;
    }
    const status = statusUpdate.status;
    if (!isPlainRecord(status)) {
        return null;
    }
    const taskState = typeof status.state === 'string' ? status.state : '';
    const meta = statusUpdate.metadata;
    const hasInterruptMeta = isPlainRecord(meta)
        && 'platform_interrupt' in meta
        && meta.platform_interrupt != null;
    if (!isInterruptedTaskState(taskState) && !hasInterruptMeta) {
        return null;
    }
    const message = status.message;
    if (!isPlainRecord(message)) {
        return null;
    }
    const parts = Array.isArray(message.parts) ? message.parts : [];
    const chunks: string[] = [];
    for (const part of parts) {
        if (!isPlainRecord(part)) {
            continue;
        }
        // A2A 1.0 Part: presence `text`, без kind / nested root
        const text = part.text;
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
        const status = unwrapped.event.status;
        const state = isPlainRecord(status) && typeof status.state === 'string' ? status.state : '';
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
