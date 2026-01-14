/**
 * GlassModal - Базовый компонент модального окна
 * Apple Liquid Glass Design
 * Поддержка темной и светлой темы
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { modalStyles } from '../styles/shared/modal.styles.js';
import './platform-icon.js';
import './platform-button.js';

export class GlassModal extends PlatformElement {
    static properties = {
        ...PlatformElement.properties,
        open: { type: Boolean, reflect: true },
        size: { type: String },
        title: { type: String },
        _isFullscreen: { type: Boolean, state: true },
        _isDragging: { type: Boolean, state: true },
        _position: { type: Object, state: true },
    };

    static styles = [
        PlatformElement.styles,
        modalStyles,
        css`
            :host {
                display: contents;
            }

            /* Overlay */
            .modal-overlay {
                position: fixed;
                inset: 0;
                background: rgba(0, 0, 0, 0.3);
                backdrop-filter: blur(var(--glass-blur-subtle, 20px)) saturate(180%);
                -webkit-backdrop-filter: blur(var(--glass-blur-subtle, 20px)) saturate(180%);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: var(--z-modal, 1000);
                opacity: 0;
                visibility: hidden;
                transition: opacity var(--duration-normal, 0.3s), visibility var(--duration-normal, 0.3s);
            }

            :host([open]) .modal-overlay {
                opacity: 1;
                visibility: visible;
            }

            /* LIQUID GLASS Modal */
            .modal {
                position: absolute;
                width: 90%;
                max-height: 90vh;
                overflow-y: auto;
                overflow-x: hidden;
                border-radius: var(--radius-3xl, 28px);
                padding: 0;
                
                background: var(--glass-solid-strong, rgba(40, 40, 64, 0.92));
                border: 1px solid var(--glass-border-medium, rgba(255, 255, 255, 0.12));
                
                backdrop-filter: blur(var(--glass-blur-medium, 40px)) saturate(180%);
                -webkit-backdrop-filter: blur(var(--glass-blur-medium, 40px)) saturate(180%);
                
                box-shadow: var(--glass-shadow-strong, 
                    0 16px 48px rgba(0, 0, 0, 0.4),
                    0 4px 16px rgba(0, 0, 0, 0.25));
                
                transform: translateY(24px) scale(0.95);
                opacity: 0;
                transition: transform var(--duration-slow, 0.4s) var(--easing-spring, cubic-bezier(0.34, 1.56, 0.64, 1)), 
                            opacity var(--duration-normal, 0.3s),
                            width var(--duration-normal, 0.3s) ease,
                            height var(--duration-normal, 0.3s) ease,
                            max-width var(--duration-normal, 0.3s) ease,
                            max-height var(--duration-normal, 0.3s) ease;
            }

            :host([open]) .modal {
                transform: translateY(0) scale(1);
                opacity: 1;
            }

            .modal.dragging {
                transition: none;
                user-select: none;
            }

            /* Световой блик сверху */
            .modal::before {
                content: '';
                position: absolute;
                top: 0;
                left: var(--space-4, 16px);
                right: var(--space-4, 16px);
                height: 1px;
                background: linear-gradient(
                    90deg,
                    transparent 0%,
                    rgba(255, 255, 255, 0.15) 20%,
                    rgba(255, 255, 255, 0.15) 80%,
                    transparent 100%
                );
                z-index: 1;
            }

            /* Gradient shine overlay */
            .modal::after {
                content: '';
                position: absolute;
                inset: 0;
                border-radius: var(--radius-3xl, 28px);
                background: linear-gradient(
                    135deg,
                    rgba(255, 255, 255, 0.04) 0%,
                    rgba(255, 255, 255, 0.01) 40%,
                    transparent 100%
                );
                pointer-events: none;
                z-index: 0;
            }

            /* Sizes */
            .modal.sm { max-width: 400px; }
            .modal.md { max-width: 500px; }
            .modal.lg { max-width: 640px; }
            .modal.xl { max-width: 900px; }
            .modal.full { 
                max-width: 95vw; 
                width: 95vw;
                max-height: 95vh;
                height: 90vh;
            }

            /* Fullscreen mode */
            .modal.fullscreen {
                max-width: 96vw !important;
                width: 96vw !important;
                max-height: 94vh !important;
                height: 94vh !important;
                border-radius: var(--radius-lg, 16px);
            }

            .modal-header {
                position: relative;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3, 12px);
                padding: var(--space-4, 16px) var(--space-4, 16px) 0 var(--space-4, 16px);
                z-index: 2;
                cursor: grab;
                user-select: none;
            }

            .modal-header:active {
                cursor: grabbing;
            }

            .modal-title {
                flex: 1;
                font-size: var(--text-xl, 20px);
                font-weight: var(--font-semibold, 600);
                color: var(--text-primary, rgba(255, 255, 255, 0.95));
                margin: 0;
                letter-spacing: var(--tracking-tight, -0.02em);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .header-buttons {
                display: flex;
                align-items: center;
                gap: var(--space-2, 8px);
                flex-shrink: 0;
            }

            .header-btn {
                width: 28px;
                height: 28px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-tint-medium, rgba(255, 255, 255, 0.05));
                border: none;
                border-radius: var(--radius-full, 50%);
                color: var(--text-secondary, rgba(255, 255, 255, 0.65));
                font-size: var(--text-sm, 14px);
                cursor: pointer;
                transition: all var(--duration-fast, 0.2s) ease;
                flex-shrink: 0;
            }

            .header-btn:hover {
                background: var(--glass-tint-strong, rgba(255, 255, 255, 0.08));
                color: var(--text-primary, rgba(255, 255, 255, 0.95));
                transform: scale(1.08);
            }

            .header-btn platform-icon {
                display: flex;
            }

            .modal-content {
                position: relative;
                color: var(--text-primary, rgba(255, 255, 255, 0.95));
                z-index: 2;
                flex: 1;
                overflow-y: auto;
                padding: var(--space-4, 16px);
            }

            .modal.fullscreen .modal-content,
            .modal.full .modal-content {
                height: calc(100% - 120px);
            }

            .modal-actions {
                position: relative;
                display: flex;
                gap: var(--space-3, 12px);
                padding: var(--space-4, 16px);
                padding-top: 0;
                z-index: 2;
            }

            .modal-actions:empty {
                display: none;
            }

            ::slotted([slot="actions"]) {
                display: flex;
                gap: var(--space-3, 12px);
                width: 100%;
            }

            /* Responsive - Tablet */
            @media (max-width: 768px) {
                .modal {
                    width: 95%;
                    border-radius: var(--radius-2xl, 24px);
                }
                
                .modal::before {
                    left: var(--space-3, 12px);
                    right: var(--space-3, 12px);
                }
                
                .modal-header {
                    padding: var(--space-3, 12px) var(--space-3, 12px) 0 var(--space-3, 12px);
                }
                
                .modal-content {
                    padding: var(--space-3, 12px);
                }
                
                .modal-actions {
                    padding: var(--space-3, 12px);
                    padding-top: 0;
                }
            }

            /* Responsive - Mobile */
            @media (max-width: 480px) {
                .modal {
                    border-radius: var(--radius-xl, 20px);
                }

                .modal-header {
                    padding: var(--space-2, 8px) var(--space-2, 8px) 0 var(--space-2, 8px);
                }
                
                .modal-content {
                    padding: var(--space-2, 8px);
                }
                
                .modal-actions {
                    padding: var(--space-2, 8px);
                    padding-top: 0;
                    flex-direction: column;
                }

                .modal-title {
                    font-size: var(--text-lg, 18px);
                }
            }

            /* Light Theme */
            :host-context([data-theme="light"]) .modal-overlay {
                background: rgba(100, 100, 120, 0.25);
                backdrop-filter: blur(20px) saturate(120%);
                -webkit-backdrop-filter: blur(20px) saturate(120%);
            }

            :host-context([data-theme="light"]) .modal {
                background: linear-gradient(
                    145deg,
                    rgba(255, 255, 255, 0.95) 0%,
                    rgba(248, 250, 252, 0.98) 100%
                );
                border: 1px solid rgba(0, 0, 0, 0.06);
                box-shadow: 
                    0 25px 60px rgba(0, 0, 0, 0.15),
                    0 10px 25px rgba(0, 0, 0, 0.08),
                    inset 0 1px 0 rgba(255, 255, 255, 1),
                    inset 0 -1px 0 rgba(0, 0, 0, 0.03);
            }

            :host-context([data-theme="light"]) .modal::before {
                background: linear-gradient(
                    90deg,
                    transparent 0%,
                    rgba(255, 255, 255, 1) 20%,
                    rgba(255, 255, 255, 1) 80%,
                    transparent 100%
                );
            }

            :host-context([data-theme="light"]) .modal::after {
                background: linear-gradient(
                    135deg,
                    rgba(255, 255, 255, 0.8) 0%,
                    rgba(255, 255, 255, 0.2) 50%,
                    transparent 100%
                );
            }

            :host-context([data-theme="light"]) .header-btn {
                background: rgba(15, 23, 42, 0.06);
                color: rgba(15, 23, 42, 0.5);
            }

            :host-context([data-theme="light"]) .header-btn:hover {
                background: rgba(15, 23, 42, 0.12);
                color: rgba(15, 23, 42, 0.9);
            }
        `
    ];

    constructor() {
        super();
        this.open = false;
        this.size = 'md';
        this.title = '';
        this._isFullscreen = false;
        this._isDragging = false;
        this._position = { x: null, y: null };
        this._dragStart = { x: 0, y: 0 };
        this._boundKeyHandler = this._handleKeyDown.bind(this);
        this._boundMouseMove = this._handleMouseMove.bind(this);
        this._boundMouseUp = this._handleMouseUp.bind(this);
    }

    showModal() {
        this.open = true;
        this._position = { x: null, y: null };
    }

    close() {
        this.open = false;
        this._isFullscreen = false;
        this._position = { x: null, y: null };
        this.emit('close');
    }

    toggleFullscreen() {
        this._isFullscreen = !this._isFullscreen;
        if (this._isFullscreen) {
            this._position = { x: null, y: null };
        }
    }

    _handleOverlayClick(e) {
        if (e.target === e.currentTarget) {
            this.close();
        }
    }

    _handleKeyDown(e) {
        if (e.key === 'Escape' && this.open) {
            this.close();
        }
    }

    _handleMouseDown(e) {
        if (this._isFullscreen) return;
        
        const modal = this.shadowRoot.querySelector('.modal');
        if (!modal) return;

        this._isDragging = true;
        const rect = modal.getBoundingClientRect();
        
        if (this._position.x === null) {
            this._position = {
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2
            };
        }
        
        this._dragStart = {
            x: e.clientX - this._position.x,
            y: e.clientY - this._position.y
        };

        document.addEventListener('mousemove', this._boundMouseMove);
        document.addEventListener('mouseup', this._boundMouseUp);
    }

    _handleMouseMove(e) {
        if (!this._isDragging) return;
        
        this._position = {
            x: e.clientX - this._dragStart.x,
            y: e.clientY - this._dragStart.y
        };
        this.requestUpdate();
    }

    _handleMouseUp() {
        this._isDragging = false;
        document.removeEventListener('mousemove', this._boundMouseMove);
        document.removeEventListener('mouseup', this._boundMouseUp);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('keydown', this._boundKeyHandler);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('keydown', this._boundKeyHandler);
        document.removeEventListener('mousemove', this._boundMouseMove);
        document.removeEventListener('mouseup', this._boundMouseUp);
    }

    renderHeader() {
        return this.title || '';
    }

    renderHeaderActions() {
        return '';
    }

    renderBody() {
        return html`<slot name="content"></slot>`;
    }

    renderFooter() {
        return html`<slot name="actions"></slot>`;
    }

    _getModalStyle() {
        if (this._position.x !== null && this._position.y !== null && !this._isFullscreen) {
            return `left: ${this._position.x}px; top: ${this._position.y}px; transform: translate(-50%, -50%) ${this.open ? 'scale(1)' : 'scale(0.95)'};`;
        }
        return '';
    }

    render() {
        const modalClasses = [
            'modal',
            this.size,
            this._isFullscreen ? 'fullscreen' : '',
            this._isDragging ? 'dragging' : ''
        ].filter(Boolean).join(' ');

        return html`
            <svg style="position: absolute; width: 0; height: 0; overflow: hidden;">
                <defs>
                    <filter id="liquidGlassFilter" x="-10%" y="-10%" width="120%" height="120%">
                        <feTurbulence 
                            type="fractalNoise" 
                            baseFrequency="0.012 0.012" 
                            numOctaves="3" 
                            seed="15"
                            result="noise"
                        />
                        <feDisplacementMap 
                            in="SourceGraphic" 
                            in2="noise" 
                            scale="6" 
                            xChannelSelector="R" 
                            yChannelSelector="G"
                        />
                    </filter>
                </defs>
            </svg>

            <div class="modal-overlay" @click=${this._handleOverlayClick}>
                <div class="${modalClasses}" style="${this._getModalStyle()}">
                    <div class="modal-header" @mousedown=${this._handleMouseDown}>
                        <h2 class="modal-title">${this.renderHeader()}</h2>
                        <div class="header-buttons">
                            ${this.renderHeaderActions()}
                            <button 
                                class="header-btn fullscreen-btn" 
                                @click=${this.toggleFullscreen}
                                title="${this._isFullscreen ? 'Свернуть' : 'На весь экран'}"
                            >
                                <platform-icon 
                                    name="${this._isFullscreen ? 'minimize' : 'maximize'}" 
                                    size="16"
                                ></platform-icon>
                            </button>
                            <button 
                                class="header-btn" 
                                @click=${() => this.close()}
                                title="Закрыть"
                            >
                                <platform-icon name="close" size="16"></platform-icon>
                            </button>
                        </div>
                    </div>
                    
                    <div class="modal-content">
                        ${this.renderBody()}
                    </div>
                    
                    <div class="modal-actions">
                        ${this.renderFooter()}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('glass-modal', GlassModal);

export { GlassModal as PlatformModal };
