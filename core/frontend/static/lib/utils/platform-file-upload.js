/**
 * Единый upload файла на платформу: только chunked session.
 *
 * Байты → POST /uploads → PUT parts → POST complete на Files API
 * текущего сервиса (`/{segment}/api/v1/files`).
 * Возвращает FileResponse JSON (file_id, url, original_name, …).
 */

import { resolvePlatformFilesApiBase } from './platform-files-url.js';

/** Defaults совпадают с FilesConfig (Pydantic). */
export const PLATFORM_FILES_UPLOAD_DEFAULTS = Object.freeze({
    maxUploadBytes: 512 * 1024 * 1024,
    chunkSizeBytes: 5 * 1024 * 1024,
});

/**
 * @param {Response} response
 * @param {string} context
 */
async function _readJsonOrThrow(response, context) {
    const text = await response.text();
    let body = null;
    if (text.trim() !== '') {
        body = JSON.parse(text);
    }
    if (!response.ok) {
        const detail =
            body && typeof body === 'object' && typeof body.detail === 'string'
                ? body.detail
                : `HTTP ${response.status}`;
        throw new Error(`${context}: ${detail}`);
    }
    if (body === null || typeof body !== 'object') {
        throw new Error(`${context}: JSON object required`);
    }
    return body;
}

/**
 * @param {{
 *   fetchImpl?: typeof fetch,
 *   credentials?: RequestCredentials,
 *   headers?: Record<string, string>,
 *   filesApiBase?: string,
 *   routeSegment?: string,
 * }} [opts]
 */
export async function fetchPlatformFilesUploadConfig(opts = {}) {
    const fetchImpl = typeof opts.fetchImpl === 'function' ? opts.fetchImpl : fetch;
    const credentials = opts.credentials != null ? opts.credentials : 'include';
    const headers = opts.headers && typeof opts.headers === 'object' ? opts.headers : {};
    const filesBase = resolvePlatformFilesApiBase(opts);
    const response = await fetchImpl(`${filesBase}/upload-config`, {
        method: 'GET',
        credentials,
        headers: { Accept: 'application/json', ...headers },
    });
    const body = await _readJsonOrThrow(response, 'upload-config');
    return {
        maxUploadBytes: body.max_upload_bytes,
        chunkSizeBytes: body.chunk_size_bytes,
    };
}

/**
 * @param {File} file
 * @param {string} specJson
 * @param {{
 *   fetchImpl: typeof fetch,
 *   credentials: RequestCredentials,
 *   headers: Record<string, string>,
 *   chunkSizeBytes: number,
 *   filesApiBase: string,
 *   onProgress?: (p: { loaded: number, total: number }) => void,
 * }} opts
 */
async function _uploadChunked(file, specJson, opts) {
    const fetchImpl = opts.fetchImpl;
    const filesBase = opts.filesApiBase;
    const initResponse = await fetchImpl(`${filesBase}/uploads`, {
        method: 'POST',
        credentials: opts.credentials,
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
            ...opts.headers,
        },
        body: JSON.stringify({
            spec: JSON.parse(specJson),
            original_name: file.name,
            content_type: file.type || 'application/octet-stream',
            file_size: file.size,
        }),
    });
    const initBody = await _readJsonOrThrow(initResponse, 'chunked upload init');
    const uploadId = initBody.upload_id;
    if (typeof uploadId !== 'string' || uploadId.length === 0) {
        throw new Error('chunked upload init: upload_id required');
    }
    const chunkSize =
        typeof initBody.chunk_size_bytes === 'number' && initBody.chunk_size_bytes > 0
            ? initBody.chunk_size_bytes
            : opts.chunkSizeBytes;

    let offset = 0;
    let partNumber = 1;
    try {
        while (offset < file.size) {
            const end = Math.min(offset + chunkSize, file.size);
            const blob = file.slice(offset, end);
            const putResponse = await fetchImpl(
                `${filesBase}/uploads/${encodeURIComponent(uploadId)}/parts/${partNumber}`,
                {
                    method: 'PUT',
                    credentials: opts.credentials,
                    headers: {
                        'Content-Type': 'application/octet-stream',
                        'Content-Length': String(blob.size),
                        ...opts.headers,
                    },
                    body: blob,
                },
            );
            await _readJsonOrThrow(putResponse, `chunked upload part ${partNumber}`);
            offset = end;
            partNumber += 1;
            if (typeof opts.onProgress === 'function') {
                opts.onProgress({ loaded: offset, total: file.size });
            }
        }
        const completeResponse = await fetchImpl(
            `${filesBase}/uploads/${encodeURIComponent(uploadId)}/complete`,
            {
                method: 'POST',
                credentials: opts.credentials,
                headers: { Accept: 'application/json', ...opts.headers },
            },
        );
        return _readJsonOrThrow(completeResponse, 'chunked upload complete');
    } catch (err) {
        try {
            await fetchImpl(`${filesBase}/uploads/${encodeURIComponent(uploadId)}`, {
                method: 'DELETE',
                credentials: opts.credentials,
                headers: { ...opts.headers },
            });
        } catch {
            // abort best-effort; original error is raised
        }
        throw err;
    }
}

/**
 * @param {{
 *   file: File,
 *   spec: string,
 *   credentials?: RequestCredentials,
 *   headers?: Record<string, string>,
 *   fetchImpl?: typeof fetch,
 *   onProgress?: (p: { loaded: number, total: number }) => void,
 *   chunkSizeBytes?: number,
 *   maxUploadBytes?: number,
 *   filesApiBase?: string,
 *   routeSegment?: string,
 * }} input
 */
export async function uploadPlatformFile(input) {
    if (!input || typeof input !== 'object') {
        throw new Error('uploadPlatformFile: input required');
    }
    if (!(input.file instanceof File)) {
        throw new Error('uploadPlatformFile: file (File) required');
    }
    if (typeof input.spec !== 'string' || input.spec.length === 0) {
        throw new Error('uploadPlatformFile: spec (JSON FileCreateSpec) required');
    }
    const file = input.file;
    const filesApiBase = resolvePlatformFilesApiBase(input);
    const maxUpload =
        typeof input.maxUploadBytes === 'number' && input.maxUploadBytes > 0
            ? input.maxUploadBytes
            : PLATFORM_FILES_UPLOAD_DEFAULTS.maxUploadBytes;
    if (file.size <= 0) {
        throw new Error('uploadPlatformFile: empty file');
    }
    if (file.size > maxUpload) {
        throw new Error(
            `uploadPlatformFile: file size ${file.size} exceeds max_upload_bytes ${maxUpload}`,
        );
    }
    const chunkSizeBytes =
        typeof input.chunkSizeBytes === 'number' && input.chunkSizeBytes > 0
            ? input.chunkSizeBytes
            : PLATFORM_FILES_UPLOAD_DEFAULTS.chunkSizeBytes;
    const fetchImpl = typeof input.fetchImpl === 'function' ? input.fetchImpl : fetch;
    const credentials = input.credentials != null ? input.credentials : 'include';
    const headers = input.headers && typeof input.headers === 'object' ? input.headers : {};
    return _uploadChunked(file, input.spec, {
        fetchImpl,
        credentials,
        headers,
        chunkSizeBytes,
        filesApiBase,
        onProgress: input.onProgress,
    });
}

/**
 * @param {unknown} value
 * @returns {value is {
 *   file_id: string,
 *   original_name: string,
 *   content_type: string,
 *   file_size: number,
 *   url?: string|null,
 * }}
 */
export function isPlatformFileRef(value) {
    if (!value || typeof value !== 'object') {
        return false;
    }
    const ref = /** @type {Record<string, unknown>} */ (value);
    return (
        typeof ref.file_id === 'string'
        && ref.file_id.length > 0
        && typeof ref.original_name === 'string'
        && typeof ref.content_type === 'string'
        && typeof ref.file_size === 'number'
    );
}

/**
 * Resolve Browser File → upload; already FileRef → passthrough (no re-upload).
 *
 * @param {unknown[]} files
 * @param {{
 *   buildSpec: (file: File) => string,
 *   credentials?: RequestCredentials,
 *   headers?: Record<string, string>,
 *   fetchImpl?: typeof fetch,
 *   onProgress?: (p: { loaded: number, total: number, fileName: string }) => void,
 *   chunkSizeBytes?: number,
 *   maxUploadBytes?: number,
 *   filesApiBase?: string,
 *   routeSegment?: string,
 * }} opts
 */
export async function resolvePlatformFileRefs(files, opts) {
    if (!opts || typeof opts !== 'object' || typeof opts.buildSpec !== 'function') {
        throw new Error('resolvePlatformFileRefs: buildSpec required');
    }
    const list = Array.isArray(files) ? files : [];
    /** @type {Array<{
     *   file_id: string,
     *   original_name: string,
     *   content_type: string,
     *   file_size: number,
     *   url: string|null,
     * }>} */
    const refs = [];
    for (const item of list) {
        if (isPlatformFileRef(item)) {
            refs.push({
                file_id: item.file_id,
                original_name: item.original_name,
                content_type: item.content_type,
                file_size: item.file_size,
                url: typeof item.url === 'string' ? item.url : null,
            });
            continue;
        }
        if (!(item instanceof File)) {
            throw new Error('resolvePlatformFileRefs: files must be File or FileRef');
        }
        const uploaded = await uploadPlatformFile({
            file: item,
            spec: opts.buildSpec(item),
            credentials: opts.credentials,
            headers: opts.headers,
            fetchImpl: opts.fetchImpl,
            chunkSizeBytes: opts.chunkSizeBytes,
            maxUploadBytes: opts.maxUploadBytes,
            filesApiBase: opts.filesApiBase,
            routeSegment: opts.routeSegment,
            onProgress:
                typeof opts.onProgress === 'function'
                    ? (p) => opts.onProgress({ ...p, fileName: item.name })
                    : undefined,
        });
        if (typeof uploaded.file_id !== 'string' || uploaded.file_id.length === 0) {
            throw new Error('resolvePlatformFileRefs: upload result.file_id required');
        }
        refs.push({
            file_id: uploaded.file_id,
            original_name:
                typeof uploaded.original_name === 'string' ? uploaded.original_name : item.name,
            content_type:
                typeof uploaded.content_type === 'string'
                    ? uploaded.content_type
                    : item.type || 'application/octet-stream',
            file_size:
                typeof uploaded.file_size === 'number' ? uploaded.file_size : item.size,
            url: typeof uploaded.url === 'string' ? uploaded.url : null,
        });
    }
    return refs;
}
