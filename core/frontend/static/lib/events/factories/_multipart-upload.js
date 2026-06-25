/**
 * Legacy helper для service-local multipart upload.
 *
 * Канон платформы — `platform/file_create` (`platform-file-create.js`):
 * payload `{ file: File, spec: string }` → POST `/frontend/api/v1/files/` с полями
 * `file` + JSON `spec` (FileCreateSpec). REST-only.
 *
 * `createMultipartFileUploadOp` оставлен только для исключений вне unified files API.
 */

import { createAsyncOp } from './async-op.js';

const _NAME_RE = /^[a-z][a-z0-9_]*\/[a-z][a-z0-9_]*$/;

function _validateConfig(config) {
    if (!config || typeof config !== 'object') {
        throw new Error('createMultipartFileUploadOp: config object required');
    }
    if (typeof config.name !== 'string' || !_NAME_RE.test(config.name)) {
        throw new Error(
            `createMultipartFileUploadOp: name must match ${_NAME_RE.source}; got "${config.name}"`,
        );
    }
    if (typeof config.url !== 'string' || config.url.length === 0 || !config.url.startsWith('/')) {
        throw new Error(`createMultipartFileUploadOp: url must start with "/"; got "${config.url}"`);
    }
}

/**
 * @param {{
 *   name: string,                          // '<svc>/<entity>'
 *   url: string,                           // '/<svc>/api/v1/files/'
 *   extraFields?: ReadonlyArray<string>,   // имена опциональных string-полей в payload
 *   restMirror?: { method?: string, path?: string },
 * }} config
 */
export function createMultipartFileUploadOp(config) {
    _validateConfig(config);
    const url = config.url;
    const extra = Array.isArray(config.extraFields) ? config.extraFields.slice() : [];
    let restMirror;
    if (config.restMirror && typeof config.restMirror === 'object') {
        const m = typeof config.restMirror.method === 'string' && config.restMirror.method.length > 0
            ? config.restMirror.method
            : 'POST';
        const p = typeof config.restMirror.path === 'string' && config.restMirror.path.length > 0
            ? config.restMirror.path
            : url;
        restMirror = { method: m, path: p };
    } else {
        restMirror = { method: 'POST', path: url };
    }

    return createAsyncOp({
        name: config.name,
        transport: 'http',
        silent: true,
        restMirror,
        request: async ({ payload }) => {
            const { httpRequest } = await import('../http.js');
            if (!payload || typeof payload !== 'object' || !(payload.file instanceof File)) {
                throw new Error(`${config.name}: payload.file (File) required`);
            }
            const formData = new FormData();
            formData.append('file', payload.file, payload.file.name);
            for (const key of extra) {
                const value = payload[key];
                if (typeof value === 'string') {
                    formData.append(key, value);
                }
            }
            return httpRequest({
                method: 'POST',
                url,
                body: formData,
            });
        },
    });
}
