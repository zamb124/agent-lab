/**
 * Router - Универсальный роутер для SPA
 * 
 * Предоставляет:
 * - Простой роутинг на базе window.location.pathname
 * - Динамический импорт страниц
 * - History API integration
 * - Поддержка query parameters
 */
import { html } from 'lit';

export class Router {
    /**
     * @param {Object} appElement - Корневой элемент приложения (extends PlatformApp)
     * @param {Object} routes - Map путей к динамическим импортам
     * @example
     * new Router(this, {
     *     '/': () => import('./pages/HomePage.js'),
     *     '/dashboard': () => import('./pages/DashboardPage.js')
     * })
     */
    constructor(appElement, routes) {
        this.appElement = appElement;
        this.routes = routes;
        this.currentPath = window.location.pathname;
        this.currentPage = null;
        
        // Bind методов для event listeners
        this._onPopState = this._onPopState.bind(this);
        this._onNavigate = this._onNavigate.bind(this);
    }

    /**
     * Запустить роутер
     */
    start() {
        // Слушаем изменения истории браузера
        window.addEventListener('popstate', this._onPopState);
        
        // Слушаем кастомное событие навигации
        window.addEventListener('navigate', this._onNavigate);
        
        // Загружаем текущую страницу
        this._loadPage(this.currentPath);
    }

    /**
     * Остановить роутер
     */
    stop() {
        window.removeEventListener('popstate', this._onPopState);
        window.removeEventListener('navigate', this._onNavigate);
    }

    /**
     * Навигация на новый путь
     * @param {string} path - Путь для навигации
     */
    navigate(path) {
        if (path === this.currentPath) return;
        
        // Добавляем в историю
        window.history.pushState({}, '', path);
        this.currentPath = path;
        
        // Загружаем новую страницу
        this._loadPage(path);
    }

    /**
     * Обработчик popstate (кнопки назад/вперед в браузере)
     * @private
     */
    _onPopState(event) {
        this.currentPath = window.location.pathname;
        this._loadPage(this.currentPath);
    }

    /**
     * Обработчик кастомного события navigate
     * @private
     */
    _onNavigate(event) {
        const { path } = event.detail;
        this.navigate(path);
    }

    /**
     * Загрузить страницу для указанного пути
     * @private
     */
    async _loadPage(path) {
        // Находим подходящий роут
        const loader = this.routes[path] || this.routes['/'] || null;
        
        if (!loader) {
            console.error(`[Router] No route found for path: ${path}`);
            this.currentPage = null;
            this.appElement.requestUpdate();
            return;
        }

        try {
            // Динамически импортируем модуль страницы
            await loader();
            
            // После импорта компонент зарегистрирован в customElements
            // Запрашиваем обновление app элемента для ре-рендера
            this.appElement.requestUpdate();
            
        } catch (error) {
            console.error(`[Router] Failed to load page for path: ${path}`, error);
            this.currentPage = null;
            this.appElement.requestUpdate();
        }
    }

    /**
     * Получить текущий путь
     * @returns {string}
     */
    getCurrentPath() {
        return this.currentPath;
    }

    /**
     * Получить query параметры
     * @returns {URLSearchParams}
     */
    getQueryParams() {
        return new URLSearchParams(window.location.search);
    }

    /**
     * Render метод для использования в PlatformApp
     * Рендерит компонент страницы на основе текущего пути
     * @returns {TemplateResult}
     */
    render() {
        const path = this.currentPath;
        
        let tagName;
        switch (path) {
            case '/':
                tagName = 'landing-page';
                break;
            case '/dashboard':
                tagName = 'dashboard-page';
                break;
            case '/select-company':
                tagName = 'select-company-page';
                break;
            case '/team':
                tagName = 'team-page';
                break;
            case '/api-keys':
                tagName = 'api-keys-page';
                break;
            case '/billing':
                tagName = 'billing-page';
                break;
            case '/embed-configs':
                tagName = 'embed-configs-page';
                break;
            case '/settings':
            case '/settings/company':
            case '/settings/security':
                tagName = 'settings-page';
                break;
            default:
                tagName = 'landing-page';
        }

        if (!customElements.get(tagName)) {
            return html`<div>Loading page...</div>`;
        }

        const element = document.createElement(tagName);
        return element;
    }
}

/**
 * Хелпер для программной навигации из любого места
 * @param {string} path - Путь для навигации
 */
export function navigateTo(path) {
    window.dispatchEvent(new CustomEvent('navigate', { detail: { path } }));
}

