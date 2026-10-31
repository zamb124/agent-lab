/**
 * Публичные URL Files API текущего сервиса (без frontend-канона для peer).
 *
 * Segment берётся явно: opts → setPlatformFilesRouteSegment (PlatformApp.getBaseUrl)
 * → первый сегмент pathname, если он известный ingress Files (`/crm/...`).
 * Frontend SPA (router base ``, getBaseUrl `/frontend`) обязан bind'ить `frontend`.
 */

/** Ingress path segments с mount `/{segment}/api/v1/files`. */
export const PLATFORM_FILES_ROUTE_SEGMENTS = Object.freeze(
    new Set([
        'frontend',
        'crm',
        'sync',
        'flows',
        'rag',
        'documents',
        'wiki',
        'worktracker',
        'litserve',
        'stock',
        'search',
        'voice',
        'browser',
        'scheduler',
        'capability-gateway',
    ]),
);

/** @type {string|null} */
let boundFilesRouteSegment: string | null = null;

/**
 * @param {string} segment
 */
export function setPlatformFilesRouteSegment(segment: string): void {
    if (typeof segment !== 'string') {
        throw new Error('setPlatformFilesRouteSegment: segment string required');
    }
    const normalized = segment.trim().replace(/^\/+|\/+$/g, '');
    if (normalized === '') {
        throw new Error('setPlatformFilesRouteSegment: segment required');
    }
    if (!PLATFORM_FILES_ROUTE_SEGMENTS.has(normalized)) {
        throw new Error(`setPlatformFilesRouteSegment: unknown segment ${normalized}`);
    }
    boundFilesRouteSegment = normalized;
}

export function clearPlatformFilesRouteSegment(): void {
    boundFilesRouteSegment = null;
}

/**
 * @returns {string|null}
 */
export function getPlatformFilesRouteSegment(): string | null {
    return boundFilesRouteSegment;
}

/**
 * @param {{
 *   pathname?: string,
 *   filesApiBase?: string,
 *   routeSegment?: string,
 * }} [opts]
 * @returns {string}
 */
export interface PlatformFilesRouteOpts {
    pathname?: string | undefined;
    filesApiBase?: string | undefined;
    routeSegment?: string | undefined;
}

export function resolvePlatformFilesRouteSegment(opts: PlatformFilesRouteOpts = {}): string {
    if (typeof opts.routeSegment === 'string' && opts.routeSegment.trim() !== '') {
        const normalized = opts.routeSegment.trim().replace(/^\/+|\/+$/g, '');
        if (!PLATFORM_FILES_ROUTE_SEGMENTS.has(normalized)) {
            throw new Error(
                `resolvePlatformFilesRouteSegment: unknown routeSegment ${normalized}`,
            );
        }
        return normalized;
    }
    if (typeof opts.filesApiBase === 'string' && opts.filesApiBase.trim() !== '') {
        const base = opts.filesApiBase.trim().replace(/\/+$/, '');
        const match = base.match(/^\/([^/]+)\/api\/v1\/files$/);
        if (!match) {
            throw new Error(
                `resolvePlatformFilesRouteSegment: invalid filesApiBase ${opts.filesApiBase}`,
            );
        }
        const seg = match[1];
        if (seg === undefined) {
            throw new Error('resolvePlatformFilesRouteSegment: filesApiBase segment missing');
        }
        if (!PLATFORM_FILES_ROUTE_SEGMENTS.has(seg)) {
            throw new Error(
                `resolvePlatformFilesRouteSegment: unknown filesApiBase segment ${seg}`,
            );
        }
        return seg;
    }
    if (boundFilesRouteSegment !== null) {
        return boundFilesRouteSegment;
    }
    const pathname =
        typeof opts.pathname === 'string' && opts.pathname !== ''
            ? opts.pathname
            : typeof window !== 'undefined' && window.location && window.location.pathname
              ? window.location.pathname
              : '';
    const segments = pathname.split('/').filter(Boolean);
    const first = segments[0];
    if (first !== undefined && PLATFORM_FILES_ROUTE_SEGMENTS.has(first)) {
        return first;
    }
    throw new Error(
        'resolvePlatformFilesRouteSegment: service path segment required '
            + '(setPlatformFilesRouteSegment from PlatformApp.getBaseUrl, '
            + 'or open SPA under /crm|/sync|/flows|/documents|/frontend/...)',
    );
}

/**
 * @param {{
 *   pathname?: string,
 *   filesApiBase?: string,
 *   routeSegment?: string,
 * }} [opts]
 * @returns {string} `/crm/api/v1/files` (без trailing slash)
 */
export function resolvePlatformFilesApiBase(opts: PlatformFilesRouteOpts = {}): string {
    if (typeof opts.filesApiBase === 'string' && opts.filesApiBase.trim() !== '') {
        return opts.filesApiBase.trim().replace(/\/+$/, '');
    }
    const segment = resolvePlatformFilesRouteSegment(opts);
    return `/${segment}/api/v1/files`;
}

/**
 * @param {string} fileId
 * @param {{
 *   pathname?: string,
 *   filesApiBase?: string,
 *   routeSegment?: string,
 * }} [opts]
 * @returns {string}
 */
export function buildPlatformFileDownloadUrl(fileId: string, opts: PlatformFilesRouteOpts = {}): string {
    if (typeof fileId !== 'string' || fileId === '') {
        throw new Error('buildPlatformFileDownloadUrl: fileId required');
    }
    return `${resolvePlatformFilesApiBase(opts)}/download/${encodeURIComponent(fileId)}`;
}

/** Любой `/{segment}/api/v1/files/download/{file_id}`. */
export const PLATFORM_FILES_DOWNLOAD_PATH_RE =
    /\/[^/]+\/api\/v1\/files\/download\/([^/?#]+)/;

/**
 * @param {string|null|undefined} raw
 * @returns {string|null}
 */
export function extractPlatformFileDownloadId(raw: unknown): string | null {
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
    if (/^https?:\/\//i.test(s) && URL.canParse(s)) {
        const u = new URL(s);
        const m = u.pathname.match(PLATFORM_FILES_DOWNLOAD_PATH_RE);
        return downloadId(m);
    }
    return downloadId(s.match(PLATFORM_FILES_DOWNLOAD_PATH_RE));
}

function downloadId(match: RegExpMatchArray | null): string | null {
    if (match === null) return null;
    const id = match[1];
    return id === undefined ? null : id;
}
