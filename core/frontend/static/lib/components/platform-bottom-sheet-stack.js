/**
 * platform-bottom-sheet-stack — единственное место, где нижние экраны попадают в DOM (mobile shell 2026).
 *
 * Подписан на state.bottomSheets.stack. Для каждого элемента создаёт компонент по реестру
 * kind -> tagName (bottom-sheet-registry), проставляет _sheetId, _sheetKind, props и open=true.
 * При удалении элемента из стека снимает узел из DOM.
 *
 * Light DOM (createRenderRoot=this), чтобы конкретный лист мог сам портироваться в document.body
 * через _attachPortalToBody() (см. platform-bottom-sheet.js).
 */

import { html } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { getBottomSheetTag } from '../utils/bottom-sheet-registry.js';

export class PlatformBottomSheetStack extends PlatformElement {
    constructor() {
        super();
        this._stackSel = this.select((s) => s.bottomSheets.stack);
        /** @type {Map<string, HTMLElement>} */
        this._mounted = new Map();
    }

    createRenderRoot() {
        return this;
    }

    updated() {
        const stack = this._stackSel ? this._stackSel.value || [] : [];
        const wantIds = new Set(stack.map((s) => s.id));

        for (const [id, el] of Array.from(this._mounted.entries())) {
            if (wantIds.has(id)) continue;
            this._mounted.delete(id);
            el.remove();
        }

        for (const item of stack) {
            const existing = this._mounted.get(item.id);
            if (existing) {
                this._applyProps(existing, item);
                continue;
            }
            const tag = getBottomSheetTag(item.kind);
            const el = document.createElement(tag);
            this._applyProps(el, item);
            this.appendChild(el);
            this._mounted.set(item.id, el);
        }
    }

    _applyProps(el, item) {
        el._sheetId = item.id;
        el._sheetKind = item.kind;
        const props = item.props || {};
        for (const key of Object.keys(props)) {
            el[key] = props[key];
        }
        if (!el.open) {
            el.open = true;
        }
    }

    render() {
        return html``;
    }
}

customElements.define('platform-bottom-sheet-stack', PlatformBottomSheetStack);
