import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

/**
 * PlatformBreadcrumbs - Универсальный компонент хлебных крошек
 * 
 * Автоматически строит цепочку навигации на основе конфигурации Router.
 * Работает со всеми приложениями платформы (CRM, sync, rag и др.).
 */
export class PlatformBreadcrumbs extends PlatformElement {
    static properties = {
        _items: { state: true },
        _separator: { type: String },
    };
    
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .breadcrumbs {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            
            .breadcrumb-item {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                cursor: pointer;
                transition: color var(--duration-fast);
            }
            
            .breadcrumb-item:hover {
                color: var(--text-primary);
            }
            
            .breadcrumb-separator {
                color: var(--text-tertiary);
            }
            
            .breadcrumb-current {
                color: var(--text-primary);
                font-weight: 500;
                cursor: default;
            }
            
            .breadcrumb-current:hover {
                color: var(--text-primary);
            }

            @media (max-width: 767px) {
                .breadcrumbs {
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    max-width: 100%;
                }

                .breadcrumb-item {
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    max-width: 200px;
                }

                .breadcrumb-current {
                    max-width: 250px;
                }
            }
        `
    ];
    
    constructor() {
        super();
        this._items = [];
        this._separator = '/';
        this._router = null;
        this._unsubscribe = null;
    }
    
    connectedCallback() {
        super.connectedCallback();
        
        // Получаем router из PlatformApp или наследника
        this._findRouter();
        
        if (this._router) {
            this._syncFromRouter();
            
            // Подписываемся на изменения router
            this._unsubscribe = this._router.subscribe?.(() => this._syncFromRouter());
        } else {
            // Если router ещё не инициализирован, пробуем снова через requestAnimationFrame
            requestAnimationFrame(() => {
                this._findRouter();
                if (this._router) {
                    this._syncFromRouter();
                    this._unsubscribe = this._router.subscribe?.(() => this._syncFromRouter());
                }
            });
        }
    }
    
    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
        this._unsubscribe = null;
    }
    
    _findRouter() {
        // Используем только глобальную ссылку на router
        this._router = window.__PLATFORM_ROUTER__;
    }
    
    _syncFromRouter() {
        if (!this._router) return;
        this._items = this._router.buildBreadcrumbs();
    }

    /**
     * Обновляет заголовок текущей (последней) хлебной крошки
     * @param {string} label - Новый заголовок
     */
    updateCurrentLabel(label) {
        if (!this._items || this._items.length === 0) return;
        this._items = this._items.map((item, index) => {
            if (index === this._items.length - 1) {
                return { ...item, label };
            }
            return item;
        });
    }
    
    _handleClick(item) {
        if (!item.clickable) return;
        
        if (this._router) {
            this._router.navigateByRoute(item.routeKey, item.itemId ? { itemId: item.itemId } : {});
        } else {
            // Fallback через кастомное событие
            window.dispatchEvent(new CustomEvent('navigate', {
                detail: { routeKey: item.routeKey, params: item.itemId ? { itemId: item.itemId } : {} }
            }));
        }
    }
    
    render() {
        if (!this._items || this._items.length === 0) return html``;
        
        return html`
            <nav class="breadcrumbs" aria-label="Breadcrumb">
                ${this._items.map((item, index) => html`
                    <span
                        class="breadcrumb-item ${item.clickable ? '' : 'breadcrumb-current'}"
                        @click=${() => this._handleClick(item)}
                        aria-current=${!item.clickable ? 'page' : undefined}
                    >
                        ${item.label}
                    </span>
                    ${index < this._items.length - 1
                        ? html`<span class="breadcrumb-separator" aria-hidden="true">${this._separator}</span>`
                        : html``
                    }
                `)}
            </nav>
        `;
    }
}

customElements.define('platform-breadcrumbs', PlatformBreadcrumbs);
