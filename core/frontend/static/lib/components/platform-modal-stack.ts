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
import type { TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { getModalTag } from '../utils/modal-registry.js';
import { CoreEvents } from '../events/contract.js';
import type { ModalStackItem } from '../events/reducers/modals.js';
import type { SelectController } from '../events/select-controller.js';
import { waitForPlatformMotion } from '../utils/motion.js';

function isStackModal(node: unknown): node is StackModalElement {
    return node instanceof HTMLElement;
}

interface StackModalElement extends HTMLElement {
    _modalId?: string;
    _modalKind?: string;
    open?: boolean;
    closing?: boolean;
    requestPlatformClose?: () => Promise<void>;
    [key: string]: unknown;
}

export class PlatformModalStack extends PlatformElement {
    _stackSel: SelectController<ModalStackItem[]>;
    _mounted: Map<string, StackModalElement>;
    _closing: Set<string>;

    constructor() {
        super();
        this._stackSel = this.select((s) => s.modals.stack);
        this._mounted = new Map();
        this._closing = new Set();
    }

    override createRenderRoot(): this {
        return this;
    }

    override updated(): void {
        const stack = this._stackSel.value;
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
            const created = document.createElement(tag);
            if (!isStackModal(created)) {
                throw new Error(`platform-modal-stack: ${tag} did not create an element`);
            }
            const el = created;
            this._applyProps(el, item);
            this.appendChild(el);
            this._mounted.set(item.id, el);
            if (item.closing === true) {
                this._scheduleClosed(item.id, el);
            }
        }
    }

    _applyProps(el: StackModalElement, item: ModalStackItem): void {
        el._modalId = item.id;
        el._modalKind = item.kind;
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

    _scheduleClosed(id: string, el: StackModalElement): void {
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
            const stack = this._stackSel.value;
            const item = stack.find((m) => m.id === id);
            if (!item || item.closing !== true) return;
            this.dispatch(CoreEvents.UI_MODAL_CLOSED, { id });
        };
        void finish();
    }

    override render(): TemplateResult {
        return html``;
    }
}

customElements.define('platform-modal-stack', PlatformModalStack);
