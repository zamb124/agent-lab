/**
 * Единая клиентская логика авто-TTS из кадра A2A SSE (`frame.result`).
 * Артефакты — контракт `speakable.js` / `speakable.py`. Interrupted `statusUpdate`
 * с текстом в `status.message` (ask_user / platform interrupt) — только на клиенте:
 * сервер не дублирует этот текст артефактом `response`.
 */

import { isInterruptedTaskState, isSettledTaskState, unwrapA2aStreamResult } from '../flow-ui/protocol/a2a-stream.js';
import { extractSpeakableText } from './speakable.js';

/**
 * Текст для TTS из interrupted `TaskStatusUpdateEvent`, когда ответ пользователю
 * в `status.message.parts` (ask_user / platform interrupt), а не в whitelisted артефакте.
 *
 * @param {object} statusUpdate — `result.statusUpdate` (A2A 1.0).
 * @returns {string|null}
 */
export function extractSpeakableTextFromFinalStatusUpdate(statusUpdate) {
    if (statusUpdate === null || typeof statusUpdate !== 'object') {
        return null;
    }
    const status = statusUpdate.status;
    if (status === null || typeof status !== 'object') {
        return null;
    }
    const taskState = typeof status.state === 'string' ? status.state : '';
    const meta = statusUpdate.metadata;
    const hasInterruptMeta =
        meta !== null &&
        typeof meta === 'object' &&
        'platform_interrupt' in meta &&
        meta.platform_interrupt != null;
    if (!isInterruptedTaskState(taskState) && !hasInterruptMeta) {
        return null;
    }
    const message = status.message;
    if (message === null || typeof message !== 'object') {
        return null;
    }
    const parts = Array.isArray(message.parts) ? message.parts : [];
    const chunks = [];
    for (const part of parts) {
        if (part === null || typeof part !== 'object') {
            continue;
        }
        // A2A 1.0 Part: presence `text`, без kind / nested root
        if (typeof part.text === 'string' && part.text !== '') {
            chunks.push(part.text);
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
export function feedSpeakableTtsFromA2aResult(media, result, getTtsOutputEnabled) {
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
        const state =
            unwrapped.event.status && typeof unwrapped.event.status.state === 'string'
                ? unwrapped.event.status.state
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
