/**
 * Открытие интерактивного browser preview: событие ``browser-preview-open`` (хост может
 * перехватить и показать модалку), иначе fallback — viewer в новой вкладке.
 */

const VIEWER_SESSION_RE = /\/browser-preview\/sessions\/([^/?#]+)\/viewer/;

export function openFlowUIBrowserPreview(host: { flowId?: unknown; contextId?: unknown; dispatchEvent(event: Event): boolean }, { url, title, status }: { url?: unknown; title?: unknown; status?: unknown }) {
    const viewerUrl = typeof url === 'string' ? url.trim() : '';
    if (viewerUrl === '') return;
    const sessionMatch = VIEWER_SESSION_RE.exec(viewerUrl);
    const sessionId = sessionMatch?.[1] !== undefined
        ? decodeURIComponent(sessionMatch[1])
        : `${typeof host.flowId === 'string' ? host.flowId : ''}:${typeof host.contextId === 'string' ? host.contextId : ''}`;
    const currentUrl = typeof title === 'string' && title.trim() !== '' ? title : viewerUrl;
    const event = new CustomEvent('browser-preview-open', {
        bubbles: true,
        composed: true,
        cancelable: true,
        detail: { viewerUrl, sessionId, currentUrl, status: typeof status === 'string' ? status : '' },
    });
    host.dispatchEvent(event);
    if (event.defaultPrevented) return;
    window.open(viewerUrl, '_blank', 'noopener,noreferrer');
}
