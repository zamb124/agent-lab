/**
 * Эффект fileTypes — единоразовая загрузка реестра типов файлов на bootstrap.
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { httpRequest } from '../http.js';
import { isPlainRecord } from '../payload.js';
import { FILE_TYPES_EVENTS } from '../reducers/file-types.js';
import { embedSafeFetchCredentials, platformAbsoluteUrl } from './embed-request-helpers.js';

function errorMessage(err: unknown): string {
    if (err instanceof Error && err.message.length > 0) return err.message;
    if (isPlainRecord(err) && typeof err.message === 'string' && err.message.length > 0) return err.message;
    throw new Error('file-types: failure has no message');
}

export function createFileTypesEffect({ platformApexOrigin }: { platformApexOrigin?: string } = {}): (event: PlatformEvent, ctx: EffectCtx<{ fileTypes?: { loaded?: boolean } }>) => Promise<void> {
    const apex = typeof platformApexOrigin === 'string' ? platformApexOrigin.trim() : '';
    return async function fileTypesEffect(event: PlatformEvent, ctx: EffectCtx<{ fileTypes?: { loaded?: boolean } }>): Promise<void> {
        if (event.type !== CoreEvents.APP_BOOTSTRAP_STARTED) return;
        if (ctx.getState().fileTypes?.loaded) return;
        try {
            const ftUrl = platformAbsoluteUrl('/api/platform/file-types', apex);
            const data = await httpRequest({
                method: 'GET',
                url: ftUrl,
                credentials: embedSafeFetchCredentials(ftUrl),
            });
            if (!isPlainRecord(data)) {
                throw new Error('file-types: response must be an object');
            }
            ctx.dispatch(FILE_TYPES_EVENTS.LOADED, {
                categories: data.categories,
                registry: data.registry,
            }, { causation_id: event.id, source: 'http' });
        } catch (err) {
            ctx.dispatch(FILE_TYPES_EVENTS.LOAD_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
        }
    };
}
