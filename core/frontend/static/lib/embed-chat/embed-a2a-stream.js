/**
 * A2A message/stream через fetch + SSE (data: JSON).
 * Автономный модуль: только fetch, без BaseService и без apps/*.
 */

/**
 * @param {object} options
 * @param {string} options.baseUrl - origin + префикс flows, без завершающего слэша (например https://host/flows)
 * @param {string} options.flowId
 * @param {string} options.message
 * @param {string} [options.contextId]
 * @param {string|null} [options.skillId]
 * @param {Array<object>} [options.files] - либо { name, mimeType|type, data: base64 }, либо уже A2A: { file: { bytes, name, mimeType } }
 * @param {object|null} [options.metadata]
 * @param {() => Promise<Record<string, string>>} [options.getHeaders] - доп. заголовки (Authorization)
 * @param {RequestCredentials} [options.credentials='omit'] - 'include' если хост шлёт session cookie (origin или тот же hostname)
 * @param {(ev: object) => void} onEvent
 */
export async function streamEmbedA2A(options, onEvent) {
    const {
        baseUrl,
        flowId,
        message,
        contextId = null,
        skillId = null,
        files = [],
        metadata = null,
        getHeaders = async () => ({}),
        credentials = 'omit',
    } = options;

    if (!baseUrl || !flowId) {
        throw new Error('baseUrl and flowId are required');
    }

    const root = baseUrl.replace(/\/$/, '');
    const url = `${root}/api/v1/${encodeURIComponent(flowId)}`;

    const a2aFileParts = (files || []).map((f) => {
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

    const a2aMessage = {
        messageId: `${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
        role: 'user',
        parts: [{ kind: 'text', text: message || '' }, ...a2aFileParts],
    };
    if (contextId) {
        a2aMessage.contextId = contextId;
    }

    const body = {
        jsonrpc: '2.0',
        id: String(Date.now()),
        method: 'message/stream',
        params: { message: a2aMessage },
    };

    const meta = metadata && typeof metadata === 'object' ? { ...metadata } : {};
    if (skillId) {
        meta.skill = skillId;
    }
    if (Object.keys(meta).length > 0) {
        body.params.metadata = meta;
    }

    const extra = await getHeaders();
    const headers = {
        'Content-Type': 'application/json',
        ...extra,
    };

    const response = await fetch(url, {
        method: 'POST',
        headers,
        credentials,
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
            const errJson = await response.json();
            if (errJson?.detail) {
                detail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
            }
        } catch {
            /* ignore */
        }
        throw new Error(detail);
    }

    const contentType = (response.headers.get('content-type') || '').toLowerCase();
    if (!contentType.includes('text/event-stream')) {
        const text = await response.text();
        let parsed;
        try {
            parsed = JSON.parse(text);
        } catch {
            throw new Error(text.trim().slice(0, 800) || 'Invalid server response');
        }
        if (parsed && parsed.error) {
            const em =
                parsed.error.message != null
                    ? String(parsed.error.message)
                    : JSON.stringify(parsed.error);
            throw new Error(em);
        }
        throw new Error('Expected text/event-stream, got another response');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            break;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const payload = line.slice(6);
                if (payload === '[DONE]') {
                    return;
                }
                try {
                    onEvent(JSON.parse(payload));
                } catch (e) {
                    console.error('[embed-a2a-stream] SSE parse error', e);
                }
            }
        }
    }
}
