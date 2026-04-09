import { AppEvents } from '../utils/types.js';

/**
 * BaseService - Базовый класс для API сервисов
 */
export class BaseService {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
    }

    async get(path, params = {}) {
        const url = this._buildUrlWithParams(path, params);
        return this._fetch('GET', url, null, {});
    }

    async getBlob(path, params = {}) {
        const pathWithParams = this._buildUrlWithParams(path, params);
        const url = `${this.baseUrl}${pathWithParams}`;
        const response = await fetch(url, { method: 'GET', credentials: 'include' });
        if (!response.ok) {
            const errorData = await response.json().catch(() => null);
            throw new Error(this._formatError(errorData, response.status));
        }
        return response.blob();
    }

    _buildUrlWithParams(path, params) {
        const entries = Object.entries(params).filter(([_, v]) => v != null);
        if (entries.length === 0) {
            return path;
        }
        const queryString = entries
            .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
            .join('&');
        return `${path}?${queryString}`;
    }

    _formatError(errorData, status) {
        if (!errorData) return `HTTP ${status}`;

        if (Array.isArray(errorData.detail)) {
            const messages = errorData.detail.map(err => {
                if (err.field && err.error) {
                    return `${err.field}: ${err.error}`;
                }
                const field = err.loc?.slice(1).join('.') || 'field';
                return `${field}: ${err.msg}`;
            });
            return messages.join('; ');
        }

        if (typeof errorData.detail === 'string') return errorData.detail;
        if (typeof errorData.message === 'string') return errorData.message;

        return `HTTP ${status}`;
    }

    async post(path, data, options = {}) {
        return this._fetch('POST', path, data, options);
    }

    async put(path, data, options = {}) {
        return this._fetch('PUT', path, data, options);
    }

    async patch(path, data, options = {}) {
        return this._fetch('PATCH', path, data, options);
    }

    async delete(path, options = {}) {
        return this._fetch('DELETE', path, null, options);
    }

    async postStream(url, data, onEvent, { signal } = {}) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data),
            signal,
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => null);
            throw new Error(this._formatError(errorData, response.status));
        }

        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('text/event-stream')) {
            const body = await response.json().catch(() => null);
            if (body?.error) {
                throw new Error(body.error.message || JSON.stringify(body.error));
            }
            throw new Error(`Unexpected response content-type: ${contentType}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const eventData = line.slice(6);
                    if (eventData === '[DONE]') return;
                    try {
                        onEvent(JSON.parse(eventData));
                    } catch (e) {
                        console.error('[BaseService] Failed to parse SSE:', e);
                    }
                }
            }
        }
    }

    async _fetch(method, path, data, options = {}) {
        const url = `${this.baseUrl}${path}`;
        const isFormData = data instanceof FormData;
        const { headers: optionHeaders = {}, ...restOptions } = options;

        const config = {
            method,
            headers: {
                ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
                ...optionHeaders,
            },
            credentials: 'include',
            ...restOptions,
        };

        if (data) {
            config.body = isFormData ? data : JSON.stringify(data);
        }

        const response = await fetch(url, config);
        
        if (!response.ok) {
            if (response.status === 401) {
                window.dispatchEvent(new CustomEvent(AppEvents.AUTH_UNAUTHORIZED, { bubbles: true }));
            }
            const errorData = await response.json().catch(() => null);
            throw new Error(this._formatError(errorData, response.status));
        }

        if (response.status === 204 || response.status === 205) {
            return {};
        }

        const contentType = response.headers.get('content-type') || '';
        const raw = await response.text();
        if (!raw || raw.trim() === '') {
            return {};
        }
        const trimmed = raw.trim();
        const looksJson = trimmed.startsWith('{') || trimmed.startsWith('[');
        if (contentType.includes('application/json')) {
            return JSON.parse(raw);
        }
        if (contentType.includes('text/markdown') || contentType.includes('text/plain')) {
            return raw;
        }
        if (looksJson) {
            return JSON.parse(raw);
        }

        return {};
    }
}
