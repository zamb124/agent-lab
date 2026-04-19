/**
 * PlatformLightModal - базовый класс для модалок с Light DOM
 * Используется для компонентов требующих совместимости с библиотеками
 * работающими с глобальными стилями (например, Drawflow)
 */
import { PlatformElement } from '../platform-element/index.js';
import { CoreEvents } from '../events/contract.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';

let lightModalStylesInjected = false;

function injectLightModalStyles() {
    if (lightModalStylesInjected) return;
    lightModalStylesInjected = true;
    
    const style = document.createElement('style');
    style.id = 'platform-light-modal-styles';
    style.textContent = `
        platform-light-modal, 
        [extends-platform-light-modal] {
            display: none;
            position: fixed;
            inset: 0;
            z-index: var(--platform-modal-layer-z, var(--z-modal, 1000));
        }
        
        platform-light-modal[open],
        [extends-platform-light-modal][open] {
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .light-modal-backdrop {
            position: absolute;
            inset: 0;
            background: rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(4px);
            -webkit-backdrop-filter: blur(4px);
            z-index: -1;
            animation: backdropFadeIn 0.3s ease-out;
        }
        
        @keyframes backdropFadeIn {
            from {
                opacity: 0;
            }
            to {
                opacity: 1;
            }
        }
        
        .light-modal-container {
            position: relative;
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            background: var(--bg-primary, #0d0d14);
            overflow: hidden;
        }
    `;
    document.head.appendChild(style);
}

export class PlatformLightModal extends PlatformElement {
    createRenderRoot() {
        return this;
    }

    static properties = {
        open: { type: Boolean, reflect: true },
        modalTitle: { type: String },
    };

    constructor() {
        super();
        this.open = false;
        this.modalTitle = '';
    }

    willUpdate(changedProperties) {
        super.willUpdate(changedProperties);
        if (changedProperties.has('open') && this.open) {
            this.style.setProperty(
                '--platform-modal-layer-z',
                String(nextModalLayerZIndex()),
            );
        }
    }

    connectedCallback() {
        super.connectedCallback();
        injectLightModalStyles();
        if (this.localName !== 'platform-light-modal' && this.localName !== 'glass-light-modal') {
            this.setAttribute('extends-platform-light-modal', '');
        }
        this._handleKeyDown = this._handleKeyDown.bind(this);
        document.addEventListener('keydown', this._handleKeyDown);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('keydown', this._handleKeyDown);
    }

    showModal() {
        this.open = true;
        this.dispatch(CoreEvents.UI_MODAL_OPEN, { kind: this.localName });
        document.body.style.overflow = 'hidden';
    }

    close() {
        this.open = false;
        this.dispatch(CoreEvents.UI_MODAL_CLOSED, { kind: this.localName });
        document.body.style.overflow = '';
    }

    _handleKeyDown(e) {
        if (e.key === 'Escape' && this.open) {
            this.close();
        }
    }

    _onBackdropClick(e) {
        if (e.target === e.currentTarget) {
            this.close();
        }
    }
}

customElements.define('glass-light-modal', PlatformLightModal);

