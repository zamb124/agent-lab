/**
 * Agent Platform - Главный JavaScript файл
 */

class APP {
    constructor() {
        this.authToken = null;
        this.themeManager = null;
        this.layoutManager = null;
        this.init();
    }
    
    init() {
        this.setupAuth();
        this.setupHTMX();
        this.setupManagers();
        this.setupUI();
    }
    
    async setupManagers() {
        // Инициализируем менеджеры
        try {
            const { default: ThemeManager } = await import('./theme-manager.js');
            const { default: LayoutManager } = await import('./layout-manager.js');
            const { default: HTMXManager } = await import('./htmx-manager.js');
            
            this.themeManager = new ThemeManager();
            this.layoutManager = new LayoutManager();
            this.htmxManager = new HTMXManager();
        } catch (error) {
            console.warn('Не удалось загрузить модули менеджеров:', error);
            // Fallback к встроенным методам
            this.setupFallbackManagers();
        }
    }
    
    setupFallbackManagers() {
        // Простые fallback методы если модули не загрузились
        this.themeManager = {
            toggleTheme: () => {
                const html = document.documentElement;
                const currentTheme = html.getAttribute('data-theme');
                const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
                html.setAttribute('data-theme', newTheme);
                localStorage.setItem('theme', newTheme);
            }
        };
        
        this.layoutManager = {
            toggleSidebar: () => {
                const sidebar = document.querySelector('.sidebar');
                const mainContent = document.querySelector('.main-content');
                sidebar?.classList.toggle('collapsed');
                mainContent?.classList.toggle('sidebar-collapsed');
            }
        };
        
        this.htmxManager = {
            showModal: () => console.log('HTMXManager fallback: showModal'),
            closeModal: () => console.log('HTMXManager fallback: closeModal')
        };
    }
    
    setupAuth() {
        console.log('🔐 Setting up auth...');
        this.authToken = this.getCookie('auth_token') || localStorage.getItem('authToken');
        console.log('🔑 Auth token:', this.authToken ? 'exists' : 'missing');
        
        document.addEventListener('htmx:configRequest', (e) => {
            console.log('📤 HTMX request config');
            if (this.authToken) {
                e.detail.headers["Authorization"] = `Bearer ${this.authToken}`;
            }
        });
        
        document.addEventListener('htmx:responseError', (e) => {
            console.log('❌ HTMX Error:', e.detail.xhr.status, e.detail.xhr.responseText);
            if (e.detail.xhr.status === 401) {
                console.log('🚫 401 detected, redirecting to auth...');
                this.logout();
                window.location.href = '/frontend/auth';
            }
        });
        
        // Также обрабатываем обычные fetch ошибки
        document.addEventListener('htmx:afterRequest', (e) => {
            console.log('📥 HTMX after request:', e.detail.xhr.status);
            if (e.detail.xhr.status === 401) {
                console.log('🚫 401 in afterRequest, redirecting...');
                this.logout();
                window.location.href = '/frontend/auth';
            }
        });
        
        console.log('✅ Auth setup complete');
    }
    
    setupHTMX() {
        // Настройки HTMX для темной темы
        document.body.setAttribute('hx-ext', 'json-enc');
    }
    
    setupUI() {
        // Плавные анимации для HTMX
        document.addEventListener('htmx:beforeSwap', (e) => {
            e.target.style.opacity = '0';
            e.target.style.transform = 'translateY(10px)';
        });
        
        document.addEventListener('htmx:afterSwap', (e) => {
            setTimeout(() => {
                e.target.style.opacity = '1';
                e.target.style.transform = 'translateY(0)';
            }, 50);
        });
    }
    setAuthToken(token) {
        this.authToken = token;
        localStorage.setItem('authToken', token);
    }
    
    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }
    
    logout() {
        this.authToken = null;
        localStorage.removeItem('authToken');
        document.cookie = 'auth_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        document.cookie = 'session_id=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    }
    
    // Утилиты для работы с UI
    showNotification(message, type = 'info') {
        // Создаем уведомление
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} notification`;
        notification.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="bi bi-info-circle me-2"></i>
                <span>${message}</span>
                <button class="btn btn-ghost btn-sm ms-auto" onclick="this.parentElement.parentElement.remove()">
                    <i class="bi bi-x"></i>
                </button>
            </div>
        `;
        
        // Добавляем в контейнер уведомлений или создаем его
        let container = document.querySelector('.notifications-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'notifications-container';
            container.style.cssText = `
                position: fixed;
                top: 2rem;
                right: 2rem;
                z-index: 1050;
                max-width: 300px;
            `;
            document.body.appendChild(container);
        }
        
        container.appendChild(notification);
        
        // Автоудаление через 5 секунд
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }
    
    // Загрузка данных
    async loadData(url, options = {}) {
        try {
            const response = await fetch(url, {
                headers: {
                    'Authorization': this.authToken ? `Bearer ${this.authToken}` : '',
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('Ошибка загрузки данных:', error);
            this.showNotification('Ошибка загрузки данных', 'danger');
            throw error;
        }
    }
}

// Инициализируем APP после загрузки DOM
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 DOM loaded, initializing APP...');
    
    // Проверяем, загружен ли HTMX
    if (typeof htmx === 'undefined') {
        console.error('❌ HTMX не загружен!');
        return;
    } else {
        console.log('✅ HTMX загружен');
    }
    
    window.app = new APP();
    console.log('✅ APP инициализирован');
    
    // Восстанавливаем тему из localStorage
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
        console.log('🎨 Тема восстановлена:', savedTheme);
    }
});

// Экспортируем для использования в других модулях
if (typeof module !== 'undefined' && module.exports) {
    module.exports = APP;
}
