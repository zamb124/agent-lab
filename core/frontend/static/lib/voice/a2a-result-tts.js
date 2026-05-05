/**
 * Единая клиентская логика авто-TTS из кадра A2A SSE (`frame.result`).
 * Артефакты — контракт `speakable.js` / `speakable.py`. Финальный `status-update`
 * с текстом в `status.message` (interrupt, `input-required`) — только на клиенте:
 * сервер не дублирует этот текст артефактом `response`.
 */

import { extractSpeakableText } from './speakable.js';

/**
 * Текст для TTS из финального `TaskStatusUpdateEvent`, когда ответ пользователю
 * в `status.message.parts` (ask_user / platform interrupt), а не в whitelisted артефакте.
 *
 * @param {object} result — `frame.result`, ожидается `kind: 'status-update'`, `final === true`.
 * @returns {string|null}
 */
export function extractSpeakableTextFromFinalStatusUpdate(result) {
    if (result === null || typeof result !== 'object') {
        return null;
    }
    if (result.final !== true) {
        return null;
    }
    const status = result.status;
    if (status === null || typeof status !== 'object') {
        return null;
    }
    const taskState = typeof status.state === 'string' ? status.state : '';
    const meta = result.metadata;
    const hasInterruptMeta =
        meta !== null &&
        typeof meta === 'object' &&
        'platform_interrupt' in meta &&
        meta.platform_interrupt != null;
    if (taskState !== 'input-required' && !hasInterruptMeta) {
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
        const root = part.root !== undefined ? part.root : part;
        if (root === null || typeof root !== 'object') {
            continue;
        }
        const kind = typeof root.kind === 'string' ? root.kind : '';
        if (kind !== 'text') {
            continue;
        }
        if (typeof root.text === 'string' && root.text !== '') {
            chunks.push(root.text);
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
 * @param {object} result — `frame.result` из JSON-RPC по SSE (`kind`, `artifact`, `final`, …).
 * @param {() => boolean} getTtsOutputEnabled
 */
export function feedSpeakableTtsFromA2aResult(media, result, getTtsOutputEnabled) {
    if (!media || result === null || typeof result !== 'object') {
        return;
    }
    const kind = typeof result.kind === 'string' ? result.kind : '';

    if (kind === 'artifact-update') {
        const text = extractSpeakableText(result);
        if (text === null) {
            return;
        }
        if (!getTtsOutputEnabled()) {
            return;
        }
        media.speak(text, { final: result.lastChunk === true });
        return;
    }

    if (kind === 'status-update' && result.final === true) {
        if (getTtsOutputEnabled()) {
            const interruptText = extractSpeakableTextFromFinalStatusUpdate(result);
            if (interruptText !== null) {
                media.speak(interruptText, { final: true });
            }
        }
        media.endUtterance();
    }
}
