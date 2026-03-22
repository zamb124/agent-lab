/**
 * Хост для модальных окон - контейнер для всех модалок
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { AppEvents } from '@platform/lib/utils/types.js';

export class PlatformModalHost extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: contents;
            }
        `
    ];

    static properties = {};

    constructor() {
        super();
        this._activeModals = [];
    }

    connectedCallback() {
        super.connectedCallback();
        
        window.addEventListener(AppEvents.MODAL_OPEN, (e) => {
            const modal = e.detail?.modal;
            if (modal && !this._activeModals.includes(modal)) {
                this._activeModals = [...this._activeModals, modal];
            }
        });

        window.addEventListener(AppEvents.MODAL_CLOSE, (e) => {
            const modal = e.detail?.modal;
            this._activeModals = this._activeModals.filter(m => m !== modal);
        });
    }

    render() {
        return html`<slot></slot>`;
    }
}

customElements.define('platform-modal-host', PlatformModalHost);
