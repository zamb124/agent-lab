/**
 * Open a session FileRef via platform.file_viewer (documents editor-config).
 * SPA/host with PlatformApp bus → FILES_EVENTS.OPEN_REQUESTED.
 * Standalone embed without bus → download URL in a new tab.
 */

import { hasPlatformBus, getPlatformBus } from '../../events/bus-singleton.js';
import { FILES_EVENTS } from '../../events/reducers/files.js';
import { buildPlatformFileDownloadUrl } from '../../utils/platform-files-url.js';

/**
 * @param {object} fileRef
 * @param {string} [source]
 */
export function openFlowUISessionFile(fileRef: Record<string, unknown> | null | undefined, source = 'flow_ui_session'): void {
    if (!fileRef || typeof fileRef !== 'object') {
        throw new Error('openFlowUISessionFile: FileRef object required');
    }
    const fileId = typeof fileRef.file_id === 'string' ? fileRef.file_id.trim() : '';
    if (fileId === '') {
        throw new Error('openFlowUISessionFile: file_id required');
    }
    const file: Record<string, unknown> = { ...fileRef, file_id: fileId };
    if (hasPlatformBus()) {
        getPlatformBus().dispatch(FILES_EVENTS.OPEN_REQUESTED, {
            file,
            source: typeof source === 'string' && source !== '' ? source : 'flow_ui_session',
        });
        return;
    }
    const href = typeof file.url === 'string' && file.url.trim() !== ''
        ? file.url.trim()
        : buildPlatformFileDownloadUrl(fileId, { routeSegment: 'flows' });
    if (typeof window === 'undefined' || typeof window.open !== 'function') {
        throw new Error('openFlowUISessionFile: window.open unavailable');
    }
    window.open(href, '_blank', 'noopener');
}
