/**
 * Канонические URL файлов платформы: /frontend/api/v1/files/download/{file_id}
 * Нормализует исторические same-origin пути вида .../api/v1/files/download/... в канон frontend.
 */

export const CANONICAL_FILES_DOWNLOAD_PREFIX = '/frontend/api/v1/files/download';

const PLATFORM_DOWNLOAD_FILE_ID_RE =
    /\/(?:frontend|flows|sync|crm|rag|worktracker|office|browser)?\/api\/v1\/files\/download\/([^/?#]+)/;

/**
 * @param {string|null|undefined} raw
 * @returns {string|null} file_id
 */
export function extractPlatformFileDownloadId(raw) {
    if (raw == null || raw === '') {
        return null;
    }
    let s = String(raw).trim();
    if (s.toLowerCase().startsWith('sandbox:')) {
        s = s.slice(8).trim();
    }
    if (s.toLowerCase().startsWith('vscode-file:')) {
        return null;
    }
    try {
        if (/^https?:\/\//i.test(s)) {
            const u = new URL(s);
            const m = (u.pathname || '').match(PLATFORM_DOWNLOAD_FILE_ID_RE);
            return m ? m[1] : null;
        }
    } catch {
        /* ignore */
    }
    const m = s.match(PLATFORM_DOWNLOAD_FILE_ID_RE);
    return m ? m[1] : null;
}

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
    return `${CANONICAL_FILES_DOWNLOAD_PREFIX}/${encodeURIComponent(fileId)}`;
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
