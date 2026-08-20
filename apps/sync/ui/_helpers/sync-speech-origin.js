export function isSpeechOriginText(content) {
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

export function messageHasSpeechOriginText(contents) {
    if (!Array.isArray(contents)) {
        throw new Error('contents должен быть массивом');
    }
    for (const content of contents) {
        if (!isSpeechOriginText(content)) {
            continue;
        }
        if (typeof content.data.body !== 'string') {
            throw new Error('text/plain origin=speech: body обязателен');
        }
        if (content.data.body.trim() !== '') {
            return true;
        }
    }
    return false;
}
