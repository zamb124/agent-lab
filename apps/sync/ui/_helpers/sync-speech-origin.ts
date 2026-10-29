import { isPlainRecord } from '@platform/lib/events/payload.js';

export function isSpeechOriginText(content: { type?: unknown; data?: Record<string, unknown> } | null | undefined) {
    if (!content || typeof content !== 'object') {
        throw new Error('content обязателен');
    }
    if (content.type !== 'text/plain') {
        return false;
    }
    const data = content.data;
    if (!data || typeof data !== 'object') {
        throw new Error('text/plain: data обязателен');
    }
    return data.origin === 'speech';
}

export function messageHasSpeechOriginText(contents: unknown) {
    if (!Array.isArray(contents)) {
        throw new Error('contents должен быть массивом');
    }
    for (const content of contents) {
        if (!isSpeechOriginText(content) || !isPlainRecord(content)) {
            continue;
        }
        const data = content.data;
        if (!isPlainRecord(data)) {
            throw new Error('text/plain: data обязателен');
        }
        const body = data.body;
        if (typeof body !== 'string') {
            throw new Error('text/plain origin=speech: body обязателен');
        }
        if (body.trim() !== '') {
            return true;
        }
    }
    return false;
}
