/**
 * PlatformPanel - унифицированная сворачиваемая боковая панель
 * Заменяет CRMPanel и inline стили панелей в agents
 * 
 * Использование:
 * - Наследуйте этот класс и переопределите renderHeaderActions() и renderContent()
 * - Или используйте слоты: <slot name="header-actions"> и <slot>
 * 
 * События:
 * - collapse-change: { collapsed: boolean }
 */
import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { panelHostStyles, panelStyles } from '../../styles/shared/island.styles.js';
import '../platform-icon.js';

export class PlatformPanel extends PlatformElement {
    static properties = {
        panelId: { type: String, attribute: 'panel-id' },
        title: { type: String },
        icon: { type: String },
        collapsible: { type: Boolean },
        collapsed: { type: Boolean, reflect: true },
        width: { type: String },
        collapsedWidth: { type: String, attribute: 'collapsed-width' },
        _isMobile: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        panelHostStyles,
        panelStyles,
        css`
            :host {
                --panel-width: var(--_panel-width, 320px);
                --panel-collapsed-width: var(--_panel-collapsed-width, 48px);
            }
        `
    ];

    constructor() {
        super();
        this.panelId = '';
        this.title = '';
        this.icon = '';
        this.collapsible = true;
        this.collapsed = false;
        this.width = '320px';
        this.collapsedWidth = '48px';
        this._isMobile = window.innerWidth < 768;
        this._resizeHandler = this._checkMobile.bind(this);
    }
    
    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('resize', this._resizeHandler);
        this._checkMobile();
    }
    
    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener('resize', this._resizeHandler);
    }
    
    _checkMobile() {
        this._isMobile = window.innerWidth < 768;
    }
    
    _isCollapsible() {
        return this.collapsible && !this._isMobile;
    }

    updated(changedProps) {
        super.updated(changedProps);
        
        if (changedProps.has('width')) {
            this.style.setProperty('--_panel-width', this.width);
        }
        if (changedProps.has('collapsedWidth')) {
            this.style.setProperty('--_panel-collapsed-width', this.collapsedWidth);
        }
    }

    toggle() {
        if (!this.collapsible) return;
        this.collapsed = !this.collapsed;
        this.emit('collapse-change', { collapsed: this.collapsed });
    }

    expand() {
        if (this.collapsed) {
            this.collapsed = false;
            this.emit('collapse-change', { collapsed: false });
        }
    }

    collapse() {
        if (!this.collapsed && this.collapsible) {
            this.collapsed = true;
            this.emit('collapse-change', { collapsed: true });
        }
    }

    _handleToggleClick(e) {
        e?.stopPropagation();
        this.toggle();
    }

    /**
     * Переопределите для добавления кнопок в header
     */
    renderHeaderActions() {
        return html`<slot name="header-actions"></slot>`;
    }

    /**
     * Переопределите для добавления контента
     */
    renderContent() {
        return html`<slot></slot>`;
    }

    render() {
        const isCollapsible = this._isCollapsible();
        
        return html`
            <div class="panel-header">
                ${isCollapsible ? html`
                    <button 
                        class="panel-collapse-btn" 
                        @click=${this._handleToggleClick}
                        title="Свернуть"
                    >
                        <platform-icon name="chevron-left" size="14"></platform-icon>
                    </button>
                ` : ''}
                <h3 class="panel-title">${this.title}</h3>
                <div class="panel-header-actions">
                    ${this.renderHeaderActions()}
                </div>
            </div>
            
            <div class="panel-content">
                ${this.renderContent()}
            </div>
            
            <div class="panel-collapsed-view" @click=${this._handleToggleClick}>
                <button class="panel-expand-btn" title="Развернуть">
                    <platform-icon name="chevron-right" size="14"></platform-icon>
                </button>
                ${this.icon ? html`
                    <div class="panel-collapsed-icon">
                        <platform-icon name="${this.icon}" size="18"></platform-icon>
                    </div>
                ` : ''}
                <span class="panel-collapsed-title">${this.title}</span>
            </div>
        `;
    }
}

customElements.define('platform-panel', PlatformPanel);
