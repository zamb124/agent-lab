/**
 * Эффект notify.
 *
 * При каждом UI_TOAST_SHOW ставит таймер на UI_TOAST_DISMISS по истечении duration.
 * Время жизни хранится в самом payload события — никаких локальных карт.
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';

export function createNotifyEffect() {
    return async function notifyEffect(event: PlatformEvent, ctx: EffectCtx<{ notify?: { toasts?: Array<{ id?: string }> } }>): Promise<void> {
        if (event.type !== CoreEvents.UI_TOAST_SHOW) return;
        const p = (event.payload ?? {}) as { duration?: unknown; id?: unknown };
        const duration = typeof p.duration === 'number' ? p.duration : 3000;
        if (duration <= 0) return;
        const id = (typeof p.id === 'string' && p.id) || _findLatestToastId(ctx);
        if (!id) return;
        setTimeout(() => {
            ctx.dispatch(CoreEvents.UI_TOAST_DISMISS, { id }, { causation_id: event.id, source: 'timer' });
        }, duration);
    };
}

function _findLatestToastId(ctx: EffectCtx<{ notify?: { toasts?: Array<{ id?: string }> } }>): string | null {
    const toasts = ctx.getState().notify?.toasts;
    if (!toasts || toasts.length === 0) return null;
    const last = toasts[toasts.length - 1];
    return last && typeof last.id === 'string' ? last.id : null;
}
