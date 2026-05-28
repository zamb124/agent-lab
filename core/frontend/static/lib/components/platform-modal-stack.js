/**
 * platform-modal-stack — единственное место, где модалка попадает в DOM.
 *
 * Подписан на state.modals.stack. Для каждого элемента стека создаёт компонент
 * по реестру kind -> tagName, проставляет _modalId, _modalKind, props и open=true.
 * Закрытие двухфазное: reducer помечает элемент как closing, компонент доигрывает
 * CSS exit-motion, затем stack диспатчит UI_MODAL_CLOSED и только тогда снимает DOM.
 *
 * Light DOM (createRenderRoot=this), чтобы внутренние модалки могли портироваться
 * в document.body своими _attachPortalToBody() (см. glass-modal.js).
 */

import { html } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { getModalTag } from '../utils/modal-registry.js';
import { CoreEvents } from '../events/contract.js';
import { waitForPlatformMotion } from '../utils/motion.js';

export class PlatformModalStack extends PlatformElement {
    constructor() {
        super();
        this._stackSel = this.select((s) => s.modals.stack);
        /** @type {Map<string, HTMLElement>} */
        this._mounted = new Map();
        /** @type {Set<string>} */
        this._closing = new Set();
    }

    createRenderRoot() {
        return this;
    }

    updated() {
        const stack = this._stackSel ? this._stackSel.value || [] : [];
        const wantIds = new Set(stack.map((m) => m.id));

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
            const tag = getModalTag(item.kind);
            const el = document.createElement(tag);
            this._applyProps(el, item);
            this.appendChild(el);
            this._mounted.set(item.id, el);
            if (item.closing === true) {
                this._scheduleClosed(item.id, el);
            }
        }
    }

    _applyProps(el, item) {
        el._modalId = item.id;
        el._modalKind = item.kind;
        el.closing = item.closing === true;
        if (item.closing === true) {
            if (el.open) {
                el.open = false;
            }
            return;
        }
        const props = item.props || {};
        for (const key of Object.keys(props)) {
            el[key] = props[key];
        }
        if (!el.open) {
            el.open = true;
        }
    }

    _scheduleClosed(id, el) {
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
            const item = stack.find((m) => m.id === id);
            if (!item || item.closing !== true) return;
            this.dispatch(CoreEvents.UI_MODAL_CLOSED, { id });
        };
        void finish();
    }

    render() {
        return html``;
    }
}

customElements.define('platform-modal-stack', PlatformModalStack);
