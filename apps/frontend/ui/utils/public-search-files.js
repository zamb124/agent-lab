const PUBLIC_SEARCH_FALLBACK_MIME_TYPE = 'application/octet-stream';

export const PUBLIC_SEARCH_MAX_FILE_SIZE = 10 * 1024 * 1024;

let pendingPublicSearchFiles = [];

function _isFile(value) {
    return typeof File !== 'undefined' && value instanceof File;
}

function _requireFile(file, label) {
    if (!_isFile(file)) {
        throw new Error(`${label} must be a File`);
    }
    return file;
}

function _mimeType(file) {
    const rawType = typeof file.type === 'string' ? file.type.trim() : '';
    return rawType !== '' ? rawType : PUBLIC_SEARCH_FALLBACK_MIME_TYPE;
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

export function fileToPublicSearchA2aPart(file) {
    const item = validatePublicSearchFile(file);
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(new Error(`Could not read file: ${item.name}`));
        reader.onload = () => {
            const result = reader.result;
            if (typeof result !== 'string') {
                reject(new Error(`FileReader returned non-string result: ${item.name}`));
                return;
            }
            const marker = 'base64,';
            const markerIndex = result.indexOf(marker);
            if (markerIndex < 0) {
                reject(new Error(`FileReader result is not base64 data URL: ${item.name}`));
                return;
            }
            resolve({
                name: item.name,
                mimeType: _mimeType(item),
                size: item.size,
                data: result.slice(markerIndex + marker.length),
            });
        };
        reader.readAsDataURL(item);
    });
}

export async function filesToPublicSearchA2aParts(files) {
    if (!Array.isArray(files)) {
        throw new Error('filesToPublicSearchA2aParts: files must be array');
    }
    return Promise.all(files.map((file) => fileToPublicSearchA2aPart(file)));
}
