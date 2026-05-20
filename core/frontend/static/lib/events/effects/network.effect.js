/**
 * Эффект сети.
 *
 * Подписка на window online/offline с эмиссией NETWORK_ONLINE / NETWORK_OFFLINE.
 * Подключается один раз на бутстрапе.
 */

import { CoreEvents } from '../contract.js';

export function createNetworkEffect() {
    let attached = false;
    return async function networkEffect(event, ctx) {
        if (event.type !== CoreEvents.APP_BOOTSTRAP_STARTED) return;
        if (attached) return;
        attached = true;
        window.addEventListener('online', () => ctx.dispatch(CoreEvents.NETWORK_ONLINE, null, { source: 'system' }));
        window.addEventListener('offline', () => ctx.dispatch(CoreEvents.NETWORK_OFFLINE, null, { source: 'system' }));
    };
}
