/**
 * Эффект UI — побочные эффекты для sidebar / namespace / documents.
 *
 * Зона ответственности:
 *   - UI_NAMESPACE_SELECT_REQUESTED: персистим выбор в localStorage и эмитим
 *     UI_NAMESPACE_CHANGED + UI_DOCUMENTS_RELOAD_REQUESTED.
 *   - UI_NAMESPACE_CHANGED: при смене активного namespace в текущей компании
 *     просим перезагрузку документов (для слушателей в office/rag/crm).
 *
 * Сайдбар (mobileOpen/collapsed) — pure state, без побочных эффектов:
 *   событие меняет state, компоненты подписаны через select.
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { copyTextToClipboard } from '../../utils/clipboard.js';
import { storageGet, storageSetJson } from '../../utils/platform-storage.js';

import { LAST_NAMESPACE_STORAGE_KEY as NAMESPACE_STORAGE_KEY } from '../../utils/platform-namespace.js';
const ALL_SENTINEL = '__ALL__';

function _readMap(): Record<string, string> {
    try {
        const raw = storageGet(NAMESPACE_STORAGE_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw) as unknown;
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
        return parsed as Record<string, string>;
    } catch {
        return {};
    }
}

function _writeMap(map: Record<string, string>): void {
    storageSetJson(NAMESPACE_STORAGE_KEY, map);
}

export function createUiEffect(): (event: PlatformEvent, ctx: EffectCtx) => Promise<void> {
    return async function uiEffect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        switch (event.type) {
            case CoreEvents.UI_NAMESPACE_SELECT_REQUESTED: {
                const p = (event.payload ?? {}) as { company_id?: unknown; selection?: unknown };
                const cid = p.company_id;
                const raw = p.selection;
                if (typeof cid !== 'string' || cid.trim().length === 0) {
                    throw new Error('ui.effect: company_id is required for UI_NAMESPACE_SELECT_REQUESTED');
                }
                const useAll =
                    raw === null ||
                    raw === undefined ||
                    raw === 'all' ||
                    (typeof raw === 'string' && raw.trim().length === 0);
                const value = useAll ? ALL_SENTINEL : String(raw).trim();
                const map = _readMap();
                map[cid.trim()] = value;
                _writeMap(map);
                ctx.dispatch(
                    CoreEvents.UI_NAMESPACE_CHANGED,
                    { company_id: cid.trim(), selection: useAll ? 'all' : value },
                    { causation_id: event.id, source: 'storage' },
                );
                ctx.dispatch(
                    CoreEvents.UI_DOCUMENTS_RELOAD_REQUESTED,
                    { reason: 'namespace_changed' },
                    { causation_id: event.id, source: 'local' },
                );
                return;
            }
            case CoreEvents.UI_CLIPBOARD_COPY_REQUESTED: {
                const text = ((event.payload ?? {}) as { text?: unknown }).text;
                if (typeof text !== 'string' || text.length === 0) {
                    throw new Error('ui.effect: text is required for UI_CLIPBOARD_COPY_REQUESTED');
                }
                const pp = event.payload as { success_i18n_key?: unknown; error_i18n_key?: unknown };
                const successKey = pp.success_i18n_key;
                const errorKey = pp.error_i18n_key;
                try {
                    await copyTextToClipboard(text);
                    ctx.dispatch(
                        CoreEvents.UI_CLIPBOARD_COPIED,
                        { length: text.length },
                        { causation_id: event.id },
                    );
                    if (successKey) {
                        ctx.dispatch(
                            CoreEvents.UI_TOAST_SHOW,
                            { type: 'success', i18n_key: successKey },
                            { causation_id: event.id },
                        );
                    }
                } catch (err) {
                    const message = String(err && (err as Error).message ? (err as Error).message : err);
                    ctx.dispatch(
                        CoreEvents.UI_CLIPBOARD_COPY_FAILED,
                        { message },
                        { causation_id: event.id },
                    );
                    if (errorKey) {
                        ctx.dispatch(
                            CoreEvents.UI_TOAST_SHOW,
                            { type: 'error', i18n_key: errorKey, i18n_vars: { msg: message } },
                            { causation_id: event.id },
                        );
                    }
                }
                return;
            }
            default:
                return;
        }
    };
}
