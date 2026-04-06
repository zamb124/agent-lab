/**
 * Полный URL скачивания файла flows: агент возвращает путь вида /flows/api/v1/files/download/{id}
 * или с мусорной схемой sandbox: — хост чата другой origin, нужен абсолютный URL на flowsBaseUrl.
 */

const FLOWS_DOWNLOAD_FILE_ID_RE = /(?:\/flows)?\/api\/v1\/files\/download\/([^/?#]+)/;

/**
 * @param {string|null|undefined} raw
 * @returns {string|null} file_id
 */
export function extractFlowsDownloadFileId(raw) {
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
            const m = (u.pathname || '').match(FLOWS_DOWNLOAD_FILE_ID_RE);
            return m ? m[1] : null;
        }
    } catch {
        /* ignore */
    }
    const m = s.match(FLOWS_DOWNLOAD_FILE_ID_RE);
    return m ? m[1] : null;
}

/**
 * @param {string|null|undefined} raw — как в ответе tool / тексте модели
 * @param {string} flowsBaseUrl — без завершающего слэша, например https://host:8001/flows
 * @returns {string}
 */
export function resolveFlowsFileDownloadUrl(raw, flowsBaseUrl) {
    if (!flowsBaseUrl || typeof flowsBaseUrl !== 'string' || !flowsBaseUrl.trim()) {
        return raw == null ? '' : String(raw);
    }
    if (raw == null || raw === '') {
        return '';
    }
    const fileId = extractFlowsDownloadFileId(raw);
    if (!fileId) {
        return String(raw).trim();
    }
    const base = flowsBaseUrl.replace(/\/$/, '');
    return `${base}/api/v1/files/download/${encodeURIComponent(fileId)}`;
}

/**
 * @param {string} html
 * @param {string} flowsBaseUrl
 * @returns {string}
 */
export function rewriteFlowsFileUrlsInHtml(html, flowsBaseUrl) {
    if (!html || !flowsBaseUrl || typeof flowsBaseUrl !== 'string' || !flowsBaseUrl.trim()) {
        return html;
    }
    return html.replace(/\b(href|src)=(["'])([^"']*)\2/gi, (match, attr, q, url) => {
        const next = resolveFlowsFileDownloadUrl(url, flowsBaseUrl);
        if (next === url) {
            return match;
        }
        return `${attr}=${q}${next}${q}`;
    });
}

/**
 * @param {object} block
 * @param {string} flowsBaseUrl
 * @returns {object}
 */
export function normalizeEmbedBlockForFlowsUrls(block, flowsBaseUrl) {
    if (!block || typeof block !== 'object' || !flowsBaseUrl || !String(flowsBaseUrl).trim()) {
        return block;
    }
    if (block.type !== 'file_card') {
        return block;
    }
    const out = { ...block };
    if (out.url) {
        out.url = resolveFlowsFileDownloadUrl(out.url, flowsBaseUrl);
    }
    if (out.preview_url) {
        out.preview_url = resolveFlowsFileDownloadUrl(out.preview_url, flowsBaseUrl);
    }
    return out;
}
