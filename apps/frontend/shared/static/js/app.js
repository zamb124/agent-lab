/**
 * Agents Lab - Главный JavaScript файл
 */

import { getCookie } from '/static/js/utils/cookies.js';
import { showNotification } from '/static/js/components/notification.js';
import PluginManager from '/static/js/plugin-manager.js';

class APP {
    constructor() {
        this.authToken = null;
        this.themeManager = null;
        this.layoutManager = null;
        this.pluginManager = null;
        this.init();
    }
    
    async init() {
        this.setupAuth();
        this.setupHTMX();
        await this.setupManagers();
        this.setupUI();
        this.loadUserProfile();
        await this.loadPlugins();
    }
    
    async setupManagers() {
        try {
            console.log('🔄 Загружаем модули менеджеров...');
            const { default: ThemeManager } = await import('/static/js/theme-manager.js');
            const { default: LanguageManager } = await import('/static/js/language-manager.js');
            const { default: LayoutManager } = await import('/static/js/layout-manager.js');
            const { default: HTMXManager } = await import('/static/js/htmx-manager.js');
            const { default: ChatManager } = await import('/static/js/chat/manager.js');
            
            console.log('✅ Модули загружены, создаем экземпляры...');
            this.themeManager = new ThemeManager();
            this.languageManager = new LanguageManager();
            this.layoutManager = new LayoutManager();
            this.htmxManager = new HTMXManager();
            this.chatManager = new ChatManager(this);
            
            // Инициализируем все менеджеры  
            console.log('🔄 Инициализируем language manager...');
            await this.languageManager.init();
            console.log('🔄 Инициализируем layout manager...');
            this.layoutManager.init();
            console.log('🔄 Инициализируем chat manager...');
            this.chatManager.init();
            
            // Ждем полной инициализации переводов перед загрузкой плагинов
            console.log('🔄 Ждем инициализации переводов...');
            await this.languageManager.refreshTranslations();
            console.log('✅ Переводы загружены');
            
            // Создаем глобальный API для интернационализации
            this.i18n = {
                t: (key, params) => this.languageManager.t(key, params),
                setLanguage: async (lang) => await this.languageManager.setLanguage(lang),
                getCurrentLanguage: () => this.languageManager.getCurrentLanguage(),
                getSupportedLanguages: () => this.languageManager.getSupportedLanguages(),
                refreshTranslations: async () => await this.languageManager.refreshTranslations()
            };

            // Создаем глобальный API для чата
            this.chat = {
                open: async (options) => await this.chatManager.open(options),
                openExistingSession: async (agent_id, session_id) => await this.chatManager.openExistingSession(agent_id, session_id),
                close: () => this.chatManager.closeChat(),
                send: (message) => this.chatManager.sendUserMessage(message)
            };

            // Загружаем PromptEditor
            if (typeof PromptEditor !== 'undefined') {
                this.PromptEditor = PromptEditor;
                console.log('✅ PromptEditor загружен');
            }
            
            // Создаем глобальный доступ к app
            window.app = this;
            
        } catch (error) {
            console.warn('Не удалось загрузить модули менеджеров:', error);
            // Fallback к встроенным методам
            this.setupFallbackManagers();
        }
    }
    
    setupFallbackManagers() {
        // Простые fallback методы если модули не загрузились
        console.log('⚠️ Используем fallback менеджеры');
        
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
                console.log('🔥 FALLBACK toggleSidebar вызван!');
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
        
        // Fallback для чата
        this.chat = {
            open: (options) => console.log('Chat fallback: open', options),
            openExistingSession: (agent_id, session_id) => console.log('Chat fallback: openExistingSession', agent_id, session_id),
            close: () => console.log('Chat fallback: close'),
            send: (message) => console.log('Chat fallback: send', message)
        };
        
        // PromptEditor fallback
        if (typeof PromptEditor !== 'undefined') {
            this.PromptEditor = PromptEditor;
        }
        
        // Устанавливаем глобальный доступ
        window.app = this;
    }
    
    /**
     * Создать prompt editor
     */
    createPromptEditor(containerElement, options = {}) {
        if (!this.PromptEditor) {
            console.error('PromptEditor не загружен');
            return null;
        }
        
        return new this.PromptEditor(containerElement, options);
    }
    
    setupAuth() {
        console.log('🔐 Setting up auth...');
        this.authToken = getCookie('auth_token') || localStorage.getItem('authToken');
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
        // Анимации управляются через CSS и dashboard.html
    }
    setAuthToken(token) {
        this.authToken = token;
        localStorage.setItem('authToken', token);
    }
    
    logout() {
        this.authToken = null;
        localStorage.removeItem('authToken');
        document.cookie = 'auth_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        document.cookie = 'session_id=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    }
    
    showNotification(message, type = 'info', duration = 5000) {
        showNotification(message, type, duration);
    }
    
    async loadUserProfile() {
        try {
            const response = await fetch('/frontend/api/admin/me', {
                headers: {
                    'Authorization': this.authToken ? `Bearer ${this.authToken}` : '',
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) {
                console.warn('Не удалось загрузить профиль пользователя');
                return;
            }
            
            const userData = await response.json();
            
            const avatarElement = document.getElementById('user-avatar');
            const nameElement = document.getElementById('user-name');
            
            if (userData.avatar_url && avatarElement) {
                avatarElement.src = userData.avatar_url;
                avatarElement.style.display = 'block';
            }
            
            if (userData.name && nameElement) {
                nameElement.textContent = userData.name;
            }
            
            console.log('✅ Профиль пользователя загружен:', userData.name);
        } catch (error) {
            console.error('Ошибка загрузки профиля пользователя:', error);
        }
    }
    
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
    
    /**
     * Загрузка плагинов
     */
    async loadPlugins() {
        console.log('🔌 Инициализация плагинной системы...');
        
        this.pluginManager = new PluginManager(this);
        
        const pluginsMetadata = window.__PLUGINS__ || [];
        
        if (pluginsMetadata.length === 0) {
            console.warn('⚠️ Нет метаданных плагинов (window.__PLUGINS__)');
            return;
        }
        
        console.log(`🔍 Найдено плагинов: ${pluginsMetadata.length}`);
        
        for (const pluginMeta of pluginsMetadata) {
            if (!pluginMeta.has_js || !pluginMeta.main_js) {
                console.log(`⏭️  ${pluginMeta.name} - нет JS модуля`);
                continue;
            }
            
            try {
                const modulePath = `/static/${pluginMeta.name}/js/${pluginMeta.main_js}`;
                await this.pluginManager.register(pluginMeta.name, modulePath);
            } catch (error) {
                console.error(`❌ Не удалось загрузить плагин ${pluginMeta.name}:`, error);
            }
        }
        
        console.log(`✅ Загружено плагинов: ${this.pluginManager.getLoadedNames().length}`);
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
