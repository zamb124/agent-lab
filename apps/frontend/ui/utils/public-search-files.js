/**
 * Файлы публичного поиска: валидация + pending для upload после выдачи session JWT.
 * Байты → chunked Files API (`uploadPlatformFile`), в A2A только Part.url.
 */

import { uploadPlatformFile } from '@platform/lib/utils/platform-file-upload.js';
import { buildPlatformAuxiliaryFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';


export const PUBLIC_SEARCH_MAX_FILE_SIZE = 10 * 1024 * 1024;

let pendingPublicSearchFiles = [];
let pendingPublicSearchRunFiles = [];

function _isFile(value) {
    return typeof File !== 'undefined' && value instanceof File;
}

function _requireFile(file, label) {
    if (!_isFile(file)) {
        throw new Error(`${label} must be a File`);
    }
    return file;
}

export function validatePublicSearchFile(file) {
    const item = _requireFile(file, 'public search file');
    if (item.size <= 0) {
        throw new Error('public search file must not be empty');
    }
    if (item.size > PUBLIC_SEARCH_MAX_FILE_SIZE) {
        throw new Error('public search file is too large');
    }
    return item;
}

export function fileListToPublicSearchFiles(fileList) {
    if (fileList === null) {
        return [];
    }
    if (typeof fileList !== 'object' || typeof fileList.length !== 'number') {
        throw new Error('fileListToPublicSearchFiles: FileList required');
    }
    return Array.from(fileList).map((file) => validatePublicSearchFile(file));
}

export function setPendingPublicSearchFiles(files) {
    if (!Array.isArray(files)) {
        throw new Error('setPendingPublicSearchFiles: files must be array');
    }
    pendingPublicSearchFiles = files.map((file) => validatePublicSearchFile(file));
}

export function takePendingPublicSearchFiles() {
    const files = pendingPublicSearchFiles;
    pendingPublicSearchFiles = [];
    return files;
}

/**
 * Browser File[] для текущего run: забираются в resource после issue session.
 * @param {File[]} files
 */
export function setPendingPublicSearchRunFiles(files) {
    if (!Array.isArray(files)) {
        throw new Error('setPendingPublicSearchRunFiles: files must be array');
    }
    pendingPublicSearchRunFiles = files.map((file) => validatePublicSearchFile(file));
}

export function takePendingPublicSearchRunFiles() {
    const files = pendingPublicSearchRunFiles;
    pendingPublicSearchRunFiles = [];
    return files;
}

/**
 * Chunked upload под JWT публичной search-сессии → FileRef для file Parts сообщения A2A.
 *
 * @param {File[]} files
 * @param {{
 *   tokenType: string,
 *   token: string,
 *   fetchImpl?: typeof fetch,
 * }} auth
 */
export async function uploadPublicSearchFilesForA2a(files, auth) {
    if (!Array.isArray(files)) {
        throw new Error('uploadPublicSearchFilesForA2a: files must be array');
    }
    if (!auth || typeof auth !== 'object') {
        throw new Error('uploadPublicSearchFilesForA2a: auth required');
    }
    if (typeof auth.tokenType !== 'string' || auth.tokenType.trim() === '') {
        throw new Error('uploadPublicSearchFilesForA2a: auth.tokenType required');
    }
    if (typeof auth.token !== 'string' || auth.token.trim() === '') {
        throw new Error('uploadPublicSearchFilesForA2a: auth.token required');
    }
    const headers = {
        Authorization: `${auth.tokenType.trim()} ${auth.token.trim()}`,
    };
    const fetchImpl = typeof auth.fetchImpl === 'function' ? auth.fetchImpl : fetch;
    const fileRefs = [];
    for (const file of files) {
        const item = validatePublicSearchFile(file);
        const uploaded = await uploadPlatformFile({
            file: item,
            spec: buildPlatformAuxiliaryFileCreateSpecJson({
                metadata: { public_search: true },
            }),
            credentials: 'include',
            headers,
            fetchImpl,
            filesApiBase: '/frontend/api/v1/files',
            maxUploadBytes: PUBLIC_SEARCH_MAX_FILE_SIZE,
        });
        for (const key of ['url', 'original_name', 'content_type']) {
            if (typeof uploaded[key] !== 'string' || uploaded[key].trim() === '') {
                throw new Error(`uploadPublicSearchFilesForA2a: uploaded.${key} required`);
            }
        }
        fileRefs.push(uploaded);
    }
    return fileRefs;
}
