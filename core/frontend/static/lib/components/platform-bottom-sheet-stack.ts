/**
 * platform-bottom-sheet-stack — единственное место, где нижние экраны попадают в DOM (mobile shell 2026).
 *
 * Подписан на state.bottomSheets.stack. Для каждого элемента создаёт компонент по реестру
 * kind -> tagName (bottom-sheet-registry), проставляет _sheetId, _sheetKind, props и open=true.
 * Закрытие двухфазное: close_requested ставит phase closing, CSS exit-motion
 * доигрывает в компоненте, затем stack диспатчит UI_BOTTOM_SHEET_CLOSED.
 *
 * Light DOM (createRenderRoot=this), чтобы конкретный лист мог сам портироваться в document.body
 * через _attachPortalToBody() (см. platform-bottom-sheet.js).
 */

import { html } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { getBottomSheetTag } from '../utils/bottom-sheet-registry.js';
import { CoreEvents } from '../events/contract.js';
import type { BottomSheetItem, BottomSheetsState } from '../events/reducers/bottom_sheets.js';
import type { SelectController } from '../events/select-controller.js';
import { waitForPlatformMotion } from '../utils/motion.js';

interface StackSheetElement extends HTMLElement {
    _sheetId?: string;
    _sheetKind?: string;
    open?: boolean;
    closing?: boolean;
    requestPlatformClose?: () => Promise<void>;
    [key: string]: unknown;
}

export class PlatformBottomSheetStack extends PlatformElement {
    _stackSel: SelectController<BottomSheetItem[]>;
    _mounted: Map<string, StackSheetElement>;
    _closing: Set<string>;

    constructor() {
        super();
        this._stackSel = this.select((s) => (s.bottomSheets as BottomSheetsState).stack);
        this._mounted = new Map();
        this._closing = new Set();
    }

    override createRenderRoot(): this {
        return this;
    }

    override updated(): void {
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
                if (item.closing === true) {
                    this._scheduleClosed(item.id, existing);
                }
                continue;
            }
            const tag = getBottomSheetTag(item.kind);
            const el = document.createElement(tag) as StackSheetElement;
            this._applyProps(el, item);
            this.appendChild(el);
            this._mounted.set(item.id, el);
            if (item.closing === true) {
                this._scheduleClosed(item.id, el);
            }
        }
    }

    _applyProps(el: StackSheetElement, item: BottomSheetItem): void {
        el._sheetId = item.id;
        el._sheetKind = item.kind;
        el.closing = item.closing === true;
        if (item.closing === true) {
            if (el.open) {
                el.open = false;
            }
            return;
        }
        const props = item.props;
        for (const key of Object.keys(props)) {
            el[key] = props[key];
        }
        if (!el.open) {
            el.open = true;
        }
    }

    _scheduleClosed(id: string, el: StackSheetElement): void {
        if (this._closing.has(id)) return;
        this._closing.add(id);
        const finish = async () => {
            try {
                if (typeof el.requestPlatformClose === 'function') {
                    await el.requestPlatformClose();
                } else {
                    el.open = false;
                    await waitForPlatformMotion(el, { fallbackMs: 180 });
                }
            } finally {
                this._closing.delete(id);
            }
            const stack = this._stackSel ? this._stackSel.value || [] : [];
            const item = stack.find((s) => s.id === id);
            if (!item || item.closing !== true) return;
            this.dispatch(CoreEvents.UI_BOTTOM_SHEET_CLOSED, { id });
        };
        void finish();
    }

    override render(): TemplateResult {
        return html``;
    }
}

customElements.define('platform-bottom-sheet-stack', PlatformBottomSheetStack);
