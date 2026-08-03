/**
 * Same-origin URL файлов: `/{segment}/api/v1/files/download/{file_id}`.
 * Segment — текущий сервис SPA; исторические пути других сервисов
 * переписываются на текущий (shared FileRepository).
 */

import {
    buildPlatformFileDownloadUrl,
    extractPlatformFileDownloadId,
    resolvePlatformFilesApiBase,
} from '../utils/platform-files-url.js';

export {
    extractPlatformFileDownloadId,
    resolvePlatformFilesApiBase,
} from '../utils/platform-files-url.js';

/**
 * @param {string|null|undefined} raw
 * @returns {string}
 */
export function resolvePlatformFileDownloadUrl(raw) {
    if (raw == null || raw === '') {
        return '';
    }
    const fileId = extractPlatformFileDownloadId(raw);
    if (!fileId) {
        return String(raw).trim();
    }
    return buildPlatformFileDownloadUrl(fileId);
}

/**
 * @param {string} html
 * @returns {string}
 */
export function rewritePlatformFileUrlsInHtml(html) {
    if (!html) {
        return html;
    }
    return html.replace(/\b(href|src)=(["'])([^"']*)\2/gi, (match, attr, q, url) => {
        const next = resolvePlatformFileDownloadUrl(url);
        if (next === url) {
            return match;
        }
        return `${attr}=${q}${next}${q}`;
    });
}

/**
 * @param {object} block
 * @returns {object}
 */
export function normalizeFlowChatBlockForPlatformUrls(block) {
    if (!block || typeof block !== 'object') {
        return block;
    }
    if (block.type !== 'file_card') {
        return block;
    }
    const out = { ...block };
    if (out.url) {
        out.url = resolvePlatformFileDownloadUrl(out.url);
    }
    if (out.preview_url) {
        out.preview_url = resolvePlatformFileDownloadUrl(out.preview_url);
    }
    return out;
}
