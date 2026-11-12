/**
 * Persist-эффект ТСД — офлайн-outbox переживает перезагрузку/свап
 * приложения через core storage-effect (localStorage).
 *
 * Подписывается на мутации `stock/tsd_outbox` и `stock/tsd_session`
 * → STORAGE_PERSIST_REQUESTED; на bootstrap диспатчит
 * STORAGE_LOAD_REQUESTED и на STORAGE_LOADED гидратирует слайсы
 * событиями `outbox_hydrated`/`session_hydrated`. Записи старше
 * TSD_OUTBOX_TTL_MS не гидратируются — устаревшая команда после суток
 * в мёртвой зоне опаснее повторного скана. Сессия прогона персистится,
 * чтобы перезагрузка терминала не стирала набранные строки.
 */

import { CoreEvents } from '@platform/lib/events/index.js';
import type { EffectCtx, PlatformEvent } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';

const KEY = platformStorageKey('stock', 'tsd.outbox');
const SESSION_KEY = platformStorageKey('stock', 'tsd.session');
const CONTEXT_KEY = platformStorageKey('stock', 'tsd.context');
const TSD_OUTBOX_TTL_MS = 24 * 60 * 60 * 1000;

const MUTATED = new Set([
    'stock/tsd_outbox/outbox_enqueued',
    'stock/tsd_outbox/outbox_delivered',
    'stock/tsd_outbox/outbox_attempt_failed',
    'stock/tsd_outbox/outbox_dropped',
    'stock/tsd_outbox/outbox_hydrated',
]);

const SESSION_MUTATED = new Set([
    'stock/tsd_session/step_applied',
    'stock/tsd_session/run_opened',
    'stock/tsd_session/line_removed',
    'stock/tsd_session/session_cleared',
    'stock/tsd_session/session_hydrated',
]);

const CONTEXT_MUTATED = new Set([
    'stock/tsd_context/warehouse_set',
    'stock/tsd_context/zone_set',
    'stock/tsd_context/resource_set',
    'stock/tsd_context/wave_set',
    'stock/tsd_context/context_reset',
    'stock/tsd_context/context_hydrated',
]);

function _outboxItems(getState: () => unknown): unknown[] {
    const state = getState();
    const slice = isPlainRecord(state) ? state.stockTsdOutbox : null;
    const items = isPlainRecord(slice) ? slice.items : null;
    return Array.isArray(items) ? items : [];
}

function _sessionSnapshot(getState: () => unknown): Record<string, unknown> {
    const state = getState();
    const slice = isPlainRecord(state) ? state.stockTsdSession : null;
    const context = isPlainRecord(slice) ? slice.context : null;
    const moveId = isPlainRecord(slice) && typeof slice.move_id === 'string' ? slice.move_id : '';
    return { at: new Date().toISOString(), context, move_id: moveId };
}

function _contextSnapshot(getState: () => unknown): Record<string, unknown> {
    const state = getState();
    const slice = isPlainRecord(state) ? state.stockTsdContext : null;
    const fields = isPlainRecord(slice) ? slice : {};
    const read = (field: string): string =>
        typeof fields[field] === 'string' ? fields[field] as string : '';
    return {
        at: new Date().toISOString(),
        warehouse_id: read('warehouse_id'),
        warehouse_name: read('warehouse_name'),
        zone_location_id: read('zone_location_id'),
        zone_code: read('zone_code'),
        resource_id: read('resource_id'),
        resource_code: read('resource_code'),
        wave_id: read('wave_id'),
        wave_name: read('wave_name'),
    };
}

function _snapshotFresh(value: unknown): value is Record<string, unknown> {
    return isPlainRecord(value)
        && typeof value.at === 'string'
        && Date.now() - Date.parse(value.at) <= TSD_OUTBOX_TTL_MS;
}

function _freshItems(items: unknown[]): unknown[] {
    const now = Date.now();
    return items.filter((item) => {
        if (!isPlainRecord(item) || typeof item.enqueued_at !== 'string') return false;
        const enqueued = Date.parse(item.enqueued_at);
        return Number.isFinite(enqueued) && now - enqueued <= TSD_OUTBOX_TTL_MS;
    });
}

export function createTsdPersistEffect() {
    let bootstrapDispatched = false;

    return async function tsdPersistEffect(event: PlatformEvent, ctx: EffectCtx) {
        // ТСД рендерится без platform-сессии (бейдж-логин) — гидратация
        // не ждёт auth-событий, читает storage на первом же событии.
        if (!bootstrapDispatched) {
            bootstrapDispatched = true;
            ctx.dispatch(CoreEvents.STORAGE_LOAD_REQUESTED, { key: KEY }, { source: 'system' });
            ctx.dispatch(CoreEvents.STORAGE_LOAD_REQUESTED, { key: SESSION_KEY }, { source: 'system' });
            ctx.dispatch(CoreEvents.STORAGE_LOAD_REQUESTED, { key: CONTEXT_KEY }, { source: 'system' });
        }

        if (event.type === CoreEvents.AUTH_COMPANY_SWITCHED) {
            // Очередь, сессия и контекст принадлежат складу прошлого
            // tenant'а — команды не доставятся, сбрасываем с persisted-
            // снапшотами.
            ctx.dispatch('stock/tsd_outbox/outbox_hydrated', { items: [] }, { source: 'system' });
            ctx.dispatch('stock/tsd_session/session_hydrated', { context: null, move_id: '' }, { source: 'system' });
            ctx.dispatch('stock/tsd_context/context_hydrated', {}, { source: 'system' });
            return;
        }

        if (event.type === CoreEvents.STORAGE_LOADED) {
            if (!isPlainRecord(event.payload)) return;
            const raw = event.payload.value;
            if (event.payload.key === KEY) {
                if (!isPlainRecord(raw) || !Array.isArray(raw.items)) return;
                const items = _freshItems(raw.items);
                ctx.dispatch('stock/tsd_outbox/outbox_hydrated', { items }, { source: 'storage' });
                return;
            }
            if (event.payload.key === CONTEXT_KEY) {
                ctx.dispatch(
                    'stock/tsd_context/context_hydrated',
                    _snapshotFresh(raw) ? raw : {},
                    { source: 'storage' },
                );
                return;
            }
            if (event.payload.key !== SESSION_KEY) return;
            const context = _snapshotFresh(raw) && isPlainRecord(raw.context)
                ? raw.context
                : null;
            const moveId = isPlainRecord(raw) && typeof raw.move_id === 'string' ? raw.move_id : '';
            ctx.dispatch(
                'stock/tsd_session/session_hydrated',
                { context, move_id: context !== null ? moveId : '' },
                { source: 'storage' },
            );
            return;
        }

        if (CONTEXT_MUTATED.has(event.type)) {
            ctx.dispatch(
                CoreEvents.STORAGE_PERSIST_REQUESTED,
                { key: CONTEXT_KEY, value: _contextSnapshot(ctx.getState) },
                { source: 'system', causation_id: event.id },
            );
            return;
        }

        if (SESSION_MUTATED.has(event.type)) {
            ctx.dispatch(
                CoreEvents.STORAGE_PERSIST_REQUESTED,
                { key: SESSION_KEY, value: _sessionSnapshot(ctx.getState) },
                { source: 'system', causation_id: event.id },
            );
            return;
        }

        if (!MUTATED.has(event.type)) return;
        ctx.dispatch(
            CoreEvents.STORAGE_PERSIST_REQUESTED,
            { key: KEY, value: { items: _outboxItems(ctx.getState) } },
            { source: 'system', causation_id: event.id },
        );
    };
}
