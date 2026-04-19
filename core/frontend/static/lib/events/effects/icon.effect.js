/**
 * Icon effect — загрузка SVG-иконок (UI и файловых) с CDN-статики.
 *
 * Слушает:
 *   icon/ui_asset/load_requested   { name }
 *   icon/file_asset/load_requested { basename }
 * Эмитит:
 *   icon/ui_asset/loaded|failed
 *   icon/file_asset/loaded|failed
 *
 * Кэш живёт в state.icon (см. reducers/icon.js); эффект только тянет SVG и
 * нормализует. Дубликат запроса блокируется в reducer (проверка `loading[key]`).
 */

import { ICON_EVENTS } from '../reducers/icon.js';
import {
    isUiIconKnown, resolveUiIconFile, normalizeSvg, FILE_ICON_BASENAME_SET,
} from '../../utils/file-icons.js';

const UI_BASE = '/static/core/assets/icons';
const FILE_BASE = '/static/core/assets/icons/files_icons';

async function _fetchSvg(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`icon fetch ${url}: HTTP ${r.status}`);
    const text = await r.text();
    if (!text) throw new Error(`icon empty: ${url}`);
    return normalizeSvg(text);
}

export function createIconEffect() {
    return async function iconEffect(event, ctx) {
        switch (event.type) {
            case ICON_EVENTS.UI_LOAD_REQUESTED: {
                const name = event.payload && event.payload.name;
                if (!name) return;
                const state = ctx.getState();
                if (state.icon.uiCache[name]) return;
                const fileName = isUiIconKnown(name) ? resolveUiIconFile(name) : name;
                try {
                    const svg = await _fetchSvg(`${UI_BASE}/${fileName}.svg`);
                    ctx.dispatch(ICON_EVENTS.UI_LOADED, { name, svg }, { causation_id: event.id, source: 'http' });
                } catch (primaryErr) {
                    let recoveredErr = primaryErr;
                    if (fileName !== name) {
                        try {
                            const svg = await _fetchSvg(`${UI_BASE}/${name}.svg`);
                            ctx.dispatch(ICON_EVENTS.UI_LOADED, { name, svg }, { causation_id: event.id, source: 'http' });
                            return;
                        } catch (fallbackErr) {
                            recoveredErr = fallbackErr;
                        }
                    }
                    ctx.dispatch(
                        ICON_EVENTS.UI_FAILED,
                        { name, message: String(recoveredErr && recoveredErr.message ? recoveredErr.message : recoveredErr) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case ICON_EVENTS.FILE_LOAD_REQUESTED: {
                const basename = event.payload && event.payload.basename;
                if (!basename) return;
                const state = ctx.getState();
                if (state.icon.fileCache[basename]) return;
                if (!FILE_ICON_BASENAME_SET.has(basename)) {
                    ctx.dispatch(ICON_EVENTS.FILE_FAILED, { basename, message: `unknown basename: ${basename}` }, { causation_id: event.id });
                    return;
                }
                try {
                    const svg = await _fetchSvg(`${FILE_BASE}/${encodeURIComponent(basename)}.svg`);
                    ctx.dispatch(ICON_EVENTS.FILE_LOADED, { basename, svg }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(ICON_EVENTS.FILE_FAILED, { basename, message: String(err && err.message ? err.message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            default:
                return;
        }
    };
}
