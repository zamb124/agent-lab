/**
 * Эффект fileTypes — единоразовая загрузка реестра типов файлов на bootstrap.
 */

import { CoreEvents } from '../contract.js';
import { httpRequest } from '../http.js';
import { FILE_TYPES_EVENTS } from '../reducers/file-types.js';
import { embedSafeFetchCredentials, platformAbsoluteUrl } from './embed-request-helpers.js';

export function createFileTypesEffect({ platformApexOrigin } = {}) {
    const apex = typeof platformApexOrigin === 'string' ? platformApexOrigin.trim() : '';
    return async function fileTypesEffect(event, ctx) {
        if (event.type !== CoreEvents.APP_BOOTSTRAP_STARTED) return;
        if (ctx.getState().fileTypes.loaded) return;
        try {
            const ftUrl = platformAbsoluteUrl('/api/platform/file-types', apex);
            const data = await httpRequest({
                method: 'GET',
                url: ftUrl,
                credentials: embedSafeFetchCredentials(ftUrl),
            });
            ctx.dispatch(FILE_TYPES_EVENTS.LOADED, {
                categories: data.categories,
                registry: data.registry,
            }, { causation_id: event.id, source: 'http' });
        } catch (err) {
            ctx.dispatch(FILE_TYPES_EVENTS.LOAD_FAILED, { message: String(err && err.message ? err.message : err) }, { causation_id: event.id, source: 'http' });
        }
    };
}
