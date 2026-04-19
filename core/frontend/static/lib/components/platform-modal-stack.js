/**
 * platform-modal-stack — единственное место, где модалка попадает в DOM.
 *
 * Подписан на state.modals.stack. Для каждого элемента стека создаёт компонент
 * по реестру kind -> tagName, проставляет _modalId, _modalKind, props и open=true.
 * При удалении элемента из стека снимает соответствующий узел из DOM.
 *
 * Light DOM (createRenderRoot=this), чтобы внутренние модалки могли портироваться
 * в document.body своими _attachPortalToBody() (см. glass-modal.js).
 */

import { html } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { getModalTag } from '../utils/modal-registry.js';

export class PlatformModalStack extends PlatformElement {
    constructor() {
        super();
        this._stackSel = this.select((s) => s.modals.stack);
        /** @type {Map<string, HTMLElement>} */
        this._mounted = new Map();
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
                continue;
            }
            const tag = getModalTag(item.kind);
            const el = document.createElement(tag);
            this._applyProps(el, item);
            this.appendChild(el);
            this._mounted.set(item.id, el);
        }
    }

    _applyProps(el, item) {
        el._modalId = item.id;
        el._modalKind = item.kind;
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

customElements.define('platform-modal-stack', PlatformModalStack);
