import { LitElement, html, css } from '../lit-shim.js';
import { getFlowChatBlockEntry } from './block-registry.js';
import './blocks/flows-chat-ui-fallback.js';

/**
 * Имена полей JSON → свойства Lit-компонента (избегаем конфликта с HTMLElement, например title у table).
 */
function mapBlockPropertyToElementKey(blockType, key) {
    if (blockType === 'table' && key === 'title') {
        return 'caption';
    }
    return key;
}

/**
 * Рендерит один блок: createElement по tagName из реестра, прокидывает поля JSON (кроме type).
 */
export class FlowsChatBlockRenderer extends LitElement {
    static properties = {
        block: { type: Object },
    };

    static styles = css`
        :host {
            display: block;
            margin-top: 10px;
        }
        #dyn {
            display: block;
        }
    `;

    firstUpdated() {
        this._syncHost();
    }

    updated(changed) {
        if (changed.has('block')) {
            this._syncHost();
        }
    }

    _syncHost() {
        const root = this.shadowRoot?.getElementById('dyn');
        if (!root) {
            return;
        }
        root.replaceChildren();
        const b = this.block;
        if (!b || typeof b !== 'object' || !b.type) {
            return;
        }
        const entry = getFlowChatBlockEntry(b.type);
        if (!entry) {
            const fb = document.createElement('flows-chat-ui-fallback');
            fb.setAttribute('type-id', b.type);
            root.append(fb);
            return;
        }
        const el = document.createElement(entry.tagName);
        for (const [k, v] of Object.entries(b)) {
            if (k === 'type') {
                continue;
            }
            const propKey = mapBlockPropertyToElementKey(b.type, k);
            try {
                el[propKey] = v;
            } catch {
                /* игнорируем невалидный prop */
            }
        }
        el.addEventListener('flows-chat-block-action', (e) => {
            if (typeof e.stopPropagation === 'function') {
                e.stopPropagation();
            }
            if (typeof e.stopImmediatePropagation === 'function') {
                e.stopImmediatePropagation();
            }
            this.dispatchEvent(
                new CustomEvent('flows-chat-block-action', {
                    detail: e.detail,
                    bubbles: true,
                    composed: true,
                }),
            );
        });
        root.append(el);
    }

    render() {
        return html`<div id="dyn"></div>`;
    }
}

customElements.define('flows-chat-block-renderer', FlowsChatBlockRenderer);
