/**
 * Единый SSE-клиент A2A чата платформы.
 *
 * Один транспорт для всех поверхностей: фабрика `flows/chat` (SPA/editor),
 * standalone `<platform-chat>` (embed на внешнем сайте), API-console.
 * Только fetch, без EventBus и без импортов app; относительные импорты —
 * файл входит в ESM-замыкание embed (scripts/check_embed_esm_closure.py).
 */

import { HttpError } from '../../events/http.js';

/**
 * URL A2A endpoint. `embedId` приоритетен (внешний embed-route).
 *
 * @param {{ baseUrl?: string, flowId?: string, embedId?: string }} target
 *   baseUrl — origin+префикс flows без завершающего слэша (например `https://host/flows`);
 *   пустая строка — same-origin `/flows`.
 */
export function a2aEndpointUrl(target) {
    const baseUrl = typeof target.baseUrl === 'string' ? target.baseUrl.trim().replace(/\/$/, '') : '';
    const root = baseUrl !== '' ? baseUrl : '/flows';
    const embedId = typeof target.embedId === 'string' ? target.embedId.trim() : '';
    const flowId = typeof target.flowId === 'string' ? target.flowId.trim() : '';
    if (embedId !== '') {
        return `${root}/api/v1/embed/${encodeURIComponent(embedId)}`;
    }
    if (flowId === '') {
        throw new Error('a2a-stream: flowId or embedId required');
    }
    return `${root}/api/v1/${encodeURIComponent(flowId)}`;
}

/**
 * A2A file parts из host-файлов: либо `{ name, mimeType|type, data: base64 }`,
 * либо уже A2A `{ file: { bytes, name, mimeType } }`.
 */
export function buildA2aFileParts(files) {
    return (Array.isArray(files) ? files : []).map((f) => {
        if (f && typeof f === 'object' && f.file && typeof f.file === 'object' && f.file.bytes != null) {
            const fw = f.file;
            return {
                kind: 'file',
                file: {
                    bytes: String(fw.bytes),
                    name: fw.name != null ? String(fw.name) : 'file',
                    mimeType:
                        fw.mimeType != null && String(fw.mimeType) !== ''
                            ? String(fw.mimeType)
                            : fw.mime_type != null && String(fw.mime_type) !== ''
                              ? String(fw.mime_type)
                              : 'application/octet-stream',
                },
            };
        }
        const bytes = f && f.data != null ? String(f.data) : '';
        const name = f && f.name != null ? String(f.name) : 'file';
        const mimeType =
            f && f.mimeType != null && String(f.mimeType) !== ''
                ? String(f.mimeType)
                : f && f.type != null && String(f.type) !== ''
                  ? String(f.type)
                  : 'application/octet-stream';
        return {
            kind: 'file',
            file: { bytes, name, mimeType },
        };
    });
}

/**
 * JSON-RPC body `message/stream` из простого пользовательского сообщения.
 *
 * @param {{ message?: string, contextId?: string|null, branchId?: string|null,
 *   files?: Array<object>, metadata?: object|null }} input
 */
export function buildA2aMessageStreamBody(input) {
    const a2aMessage = {
        messageId: `${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
        role: 'user',
        parts: [
            { kind: 'text', text: typeof input.message === 'string' ? input.message : '' },
            ...buildA2aFileParts(input.files),
        ],
    };
    if (typeof input.contextId === 'string' && input.contextId.length > 0) {
        a2aMessage.contextId = input.contextId;
    }
    const body = {
        jsonrpc: '2.0',
        id: String(Date.now()),
        method: 'message/stream',
        params: { message: a2aMessage },
    };
    const metadata =
        input.metadata && typeof input.metadata === 'object' ? { ...input.metadata } : {};
    const branchId =
        input.branchId != null && String(input.branchId).trim() !== ''
            ? String(input.branchId).trim()
            : null;
    if (branchId) {
        metadata.branch = branchId;
    }
    if (Object.keys(metadata).length > 0) {
        body.params.metadata = metadata;
    }
    return body;
}

/** JSON-RPC body `tasks/cancel`. */
export function buildA2aCancelBody(taskId) {
    if (typeof taskId !== 'string' || taskId.trim() === '') {
        throw new Error('a2a-stream: taskId required for cancel');
    }
    return {
        jsonrpc: '2.0',
        id: String(Date.now()),
        method: 'tasks/cancel',
        params: { id: taskId },
    };
}

function _headersObject(headers) {
    const out = {};
    headers.forEach((value, key) => {
        out[key] = value;
    });
    return out;
}

async function _throwHttpErrorFromResponse(response) {
    let body = null;
    try {
        body = await response.json();
    } catch {
        body = null;
    }
    let detail = `HTTP ${response.status}`;
    if (body && typeof body === 'object') {
        if (typeof body.detail === 'string') {
            detail = body.detail;
        } else if (body.detail != null) {
            detail = JSON.stringify(body.detail);
        } else if (typeof body.message === 'string') {
            detail = body.message;
        }
    }
    throw new HttpError(detail, response.status, body);
}

function _throwFromNonSseText(text) {
    let parsed;
    try {
        parsed = JSON.parse(text);
    } catch {
        throw new Error(text.trim().slice(0, 800) || 'Invalid server response');
    }
    if (parsed && parsed.error) {
        const errorMessage =
            parsed.error.message != null ? String(parsed.error.message) : JSON.stringify(parsed.error);
        throw new HttpError(errorMessage, 0, parsed.error);
    }
    throw new Error('Expected text/event-stream, got another response');
}

/**
 * Стримит SSE-ответ A2A: для каждой строки `data: <json>` парсит JSON-RPC frame
 * и вызывает `onFrame(frame)`. `[DONE]` завершает стрим.
 *
 * @param {{
 *   url: string,
 *   body: object,
 *   headers?: Record<string, string>,
 *   credentials?: RequestCredentials,
 *   signal?: AbortSignal,
 *   captureRaw?: boolean,
 * }} options
 * @param {(frame: object) => void} onFrame
 * @returns {Promise<{ status: number, statusText: string, headers: Record<string, string>, raw: string }>}
 */
export async function consumeA2aStream(options, onFrame) {
    if (typeof onFrame !== 'function') {
        throw new Error('a2a-stream: onFrame function required');
    }
    if (!options || typeof options.url !== 'string' || options.url === '') {
        throw new Error('a2a-stream: url required');
    }
    const response = await fetch(options.url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            ...(options.headers || {}),
        },
        credentials: options.credentials || 'include',
        body: JSON.stringify(options.body),
        signal: options.signal,
    });

    if (!response.ok) {
        await _throwHttpErrorFromResponse(response);
    }

    const contentType = (response.headers.get('content-type') || '').toLowerCase();
    if (!contentType.includes('text/event-stream')) {
        _throwFromNonSseText(await response.text());
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let raw = '';
    const envelope = () => ({
        status: response.status,
        statusText: response.statusText,
        headers: _headersObject(response.headers),
        raw,
    });

    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            break;
        }
        const decoded = decoder.decode(value, { stream: true });
        if (options.captureRaw === true) {
            raw += decoded;
        }
        buffer += decoded;
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const payload = line.slice(6);
                if (payload === '[DONE]') {
                    return envelope();
                }
                onFrame(JSON.parse(payload));
            }
        }
    }
    return envelope();
}
