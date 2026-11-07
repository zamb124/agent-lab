/**
 * Распознавание base64-картинок в JSON (data URL, сырой base64, объект с mime + bytes).
 */

import { isPlainRecord } from '../events/payload.js';
import { formatFileSize } from './format-file-size.js';
import { jsonTreeChildPath } from './json-tree-path.js';

const DATA_IMAGE_RE = /^data:(image\/[a-z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)$/i;
const BASE64_BODY_RE = /^[A-Za-z0-9+/=\s]+$/;
const MIN_RAW_BASE64_LENGTH = 64;
const B64_FIELD_KEYS = Object.freeze(['bytes_b64', 'data_b64', 'image_b64', 'content_b64', 'b64', 'base64']);
const MIME_FIELD_KEYS = Object.freeze(['content_type', 'mime_type', 'media_type']);

export interface Base64ImageRef {
    src: string;
    mimeType: string;
    byteLength: number;
}

export interface JsonImageRef extends Base64ImageRef {
    path: string;
    label: string;
}

function _decodeBase64ToBytes(text: string): Uint8Array {
    const cleaned = text.replace(/\s+/g, '');
    if (cleaned.length === 0) {
        throw new Error('base64-image: empty base64');
    }
    if (typeof globalThis.atob !== 'function') {
        throw new Error('base64-image: atob is unavailable');
    }
    let binary: string;
    try {
        binary = globalThis.atob(cleaned);
    } catch (err) {
        if (err instanceof DOMException) {
            throw new Error('base64-image: invalid base64');
        }
        throw err;
    }
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
        out[i] = binary.charCodeAt(i);
    }
    return out;
}

function _startsWith(bytes: Uint8Array, prefix: readonly number[]): boolean {
    if (bytes.length < prefix.length) {
        return false;
    }
    for (let i = 0; i < prefix.length; i += 1) {
        if (bytes[i] !== prefix[i]) {
            return false;
        }
    }
    return true;
}

function _sniffImageMime(bytes: Uint8Array): string | null {
    if (_startsWith(bytes, [0xff, 0xd8, 0xff])) {
        return 'image/jpeg';
    }
    if (_startsWith(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) {
        return 'image/png';
    }
    if (_startsWith(bytes, [0x47, 0x49, 0x46, 0x38])) {
        return 'image/gif';
    }
    if (
        bytes.length >= 12
        && _startsWith(bytes, [0x52, 0x49, 0x46, 0x46])
        && bytes[8] === 0x57
        && bytes[9] === 0x45
        && bytes[10] === 0x42
        && bytes[11] === 0x50
    ) {
        return 'image/webp';
    }
    return null;
}

function _looksLikeRawBase64(text: string): boolean {
    if (text.length < MIN_RAW_BASE64_LENGTH) {
        return false;
    }
    if (!BASE64_BODY_RE.test(text)) {
        return false;
    }
    const cleaned = text.replace(/\s+/g, '');
    if (cleaned.length < MIN_RAW_BASE64_LENGTH) {
        return false;
    }
    return cleaned.length % 4 === 0;
}

function _isImageMime(value: unknown): value is string {
    return typeof value === 'string' && value.startsWith('image/') && value.length > 'image/'.length;
}

function _readObjectMime(record: Record<string, unknown>): string | null {
    for (const key of MIME_FIELD_KEYS) {
        const mime = record[key];
        if (_isImageMime(mime)) {
            return mime;
        }
    }
    return null;
}

function _readObjectBase64(record: Record<string, unknown>): string | null {
    for (const key of B64_FIELD_KEYS) {
        const value = record[key];
        if (typeof value === 'string' && value.length > 0) {
            return value;
        }
    }
    return null;
}

function _toDataUrl(mimeType: string, base64Body: string): string {
    const cleaned = base64Body.replace(/\s+/g, '');
    return `data:${mimeType};base64,${cleaned}`;
}

/**
 * Строка data URL или сырой base64 картинки → data URL + meta.
 */
export function resolveBase64Image(value: unknown): Base64ImageRef | null {
    if (typeof value !== 'string' || value.length === 0) {
        return null;
    }
    const dataMatch = DATA_IMAGE_RE.exec(value.trim());
    if (dataMatch !== null) {
        const mimeType = dataMatch[1];
        const body = dataMatch[2];
        if (typeof mimeType !== 'string' || typeof body !== 'string') {
            throw new Error('base64-image: data URL match incomplete');
        }
        const bytes = _decodeBase64ToBytes(body);
        return { src: _toDataUrl(mimeType.toLowerCase(), body), mimeType: mimeType.toLowerCase(), byteLength: bytes.length };
    }
    if (!_looksLikeRawBase64(value)) {
        return null;
    }
    let bytes: Uint8Array;
    try {
        bytes = _decodeBase64ToBytes(value);
    } catch (err) {
        if (err instanceof Error && err.message.startsWith('base64-image:')) {
            return null;
        }
        throw err;
    }
    const mimeType = _sniffImageMime(bytes);
    if (mimeType === null) {
        return null;
    }
    return { src: _toDataUrl(mimeType, value), mimeType, byteLength: bytes.length };
}

/**
 * Объект с mime + base64-полем (bytes_b64 и т.п.) → data URL + meta.
 */
export function resolveJsonImageObject(value: unknown): Base64ImageRef | null {
    if (!isPlainRecord(value)) {
        return null;
    }
    const mime = _readObjectMime(value);
    const body = _readObjectBase64(value);
    if (body === null) {
        return null;
    }
    if (mime !== null) {
        let bytes: Uint8Array;
        try {
            bytes = _decodeBase64ToBytes(body);
        } catch (err) {
            if (err instanceof Error && err.message.startsWith('base64-image:')) {
                return null;
            }
            throw err;
        }
        return { src: _toDataUrl(mime, body), mimeType: mime, byteLength: bytes.length };
    }
    return resolveBase64Image(body);
}

/**
 * Любое JSON-значение, из которого можно показать картинку.
 */
export function resolveJsonImage(value: unknown): Base64ImageRef | null {
    const fromString = resolveBase64Image(value);
    if (fromString !== null) {
        return fromString;
    }
    return resolveJsonImageObject(value);
}

/**
 * Краткая подпись листа: скаляр, метка base64-картинки или image-payload объекта.
 */
export function formatJsonLeafPreview(value: unknown, maxLen = 64): string | null {
    if (value === null) {
        return 'null';
    }
    if (typeof value === 'boolean') {
        return value ? 'true' : 'false';
    }
    if (typeof value === 'number') {
        if (!Number.isFinite(value)) {
            throw new Error('formatJsonLeafPreview: number must be finite');
        }
        return String(value);
    }
    if (typeof value === 'bigint') {
        return String(value);
    }
    if (typeof value === 'string') {
        if (value.length === 0) {
            return '""';
        }
        const image = resolveBase64Image(value);
        if (image !== null) {
            return `${image.mimeType} · ${formatFileSize(image.byteLength)}`;
        }
        if (value.length <= maxLen) {
            return value;
        }
        return `${value.slice(0, Math.max(1, maxLen - 1))}…`;
    }
    const objectImage = resolveJsonImageObject(value);
    if (objectImage !== null) {
        return `${objectImage.mimeType} · ${formatFileSize(objectImage.byteLength)}`;
    }
    return null;
}

function _collectInto(out: JsonImageRef[], value: unknown, path: string, label: string): void {
    const objectImage = resolveJsonImageObject(value);
    if (objectImage !== null) {
        out.push({
            path,
            label,
            src: objectImage.src,
            mimeType: objectImage.mimeType,
            byteLength: objectImage.byteLength,
        });
        return;
    }
    const stringImage = resolveBase64Image(value);
    if (stringImage !== null) {
        out.push({
            path,
            label,
            src: stringImage.src,
            mimeType: stringImage.mimeType,
            byteLength: stringImage.byteLength,
        });
        return;
    }
    if (Array.isArray(value)) {
        for (let index = 0; index < value.length; index += 1) {
            const childPath = jsonTreeChildPath(path, index, true);
            _collectInto(out, value[index], childPath, `[${String(index)}]`);
        }
        return;
    }
    if (!isPlainRecord(value)) {
        return;
    }
    for (const key of Object.keys(value)) {
        const childPath = jsonTreeChildPath(path, key, false);
        _collectInto(out, value[key], childPath, key);
    }
}

/**
 * Все картинки внутри JSON-значения (объекты с mime+b64 и строковые base64).
 */
export function collectJsonImages(value: unknown, rootPath = ''): JsonImageRef[] {
    const out: JsonImageRef[] = [];
    _collectInto(out, value, rootPath, rootPath.length === 0 ? 'root' : rootPath);
    return out;
}
