/**
 * LanguageManager - управление переводами и языком интерфейса
 */

import { getCookie, setCookie } from '/static/js/utils/cookies.js';

class LanguageManager {
    constructor() {
        this.currentLanguage = 'ru';
        this.translations = {};
        this.fallbackLanguage = 'ru';
        this.supportedLanguages = ['ru', 'en', 'es'];
        this.isInitialized = false;
    }
    
    async init() {
        console.log('🌐 Инициализация LanguageManager...');
        
        // Определяем текущий язык
        await this.detectLanguage();
        
        // Загружаем переводы для текущего языка
        await this.loadTranslations(this.currentLanguage);
        
        // Настраиваем перехват HTMX запросов
        this.setupHTMXIntercept();
        
        // Обновляем UI индикаторы языка
        this.updateLanguageIndicators();
        
        // Настраиваем обработчики dropdown
        setTimeout(() => this.setupDropdownHandlers(), 100);
        
        this.isInitialized = true;
        console.log(`✅ LanguageManager инициализирован (язык: ${this.currentLanguage})`);
    }
    
    async detectLanguage() {
        // 1. Cookie (синхронизировано с сервером - высший приоритет)
        let cookieLang = getCookie('language');
        if (cookieLang && this.isValidLanguage(cookieLang)) {
            this.currentLanguage = cookieLang;
            // Синхронизируем localStorage с cookie
            localStorage.setItem('language', cookieLang);
            console.log(`🌐 Язык определен из cookie: ${cookieLang}`);
            return;
        }
        
        // 2. localStorage (быстрый клиентский доступ)
        let savedLang = localStorage.getItem('language');
        if (savedLang && this.isValidLanguage(savedLang)) {
            this.currentLanguage = savedLang;
            // Устанавливаем cookie для синхронизации с сервером
            setCookie('language', savedLang, 365);
            console.log(`🌐 Язык определен из localStorage: ${savedLang}`);
            return;
        }
        
        // 3. Из браузера
        let browserLang = navigator.language.split('-')[0].toLowerCase();
        if (this.isValidLanguage(browserLang)) {
            this.currentLanguage = browserLang;
            console.log(`🌐 Язык определен из браузера: ${browserLang}`);
            return;
        }
        
        // 4. По умолчанию
        this.currentLanguage = this.fallbackLanguage;
        console.log(`🌐 Используем язык по умолчанию: ${this.fallbackLanguage}`);
    }
    
    isValidLanguage(lang) {
        return this.supportedLanguages.includes(lang.toLowerCase());
    }
    
    async setLanguage(lang) {
        if (!this.isValidLanguage(lang)) {
            console.warn(`❌ Неподдерживаемый язык: ${lang}`);
            return;
        }
        
        const oldLanguage = this.currentLanguage;
        this.currentLanguage = lang;
        
        console.log(`🔄 Смена языка: ${oldLanguage} → ${lang}`);
        
        // Устанавливаем и cookie, и localStorage для двойной синхронизации
        localStorage.setItem('language', lang);
        setCookie('language', lang, 365);
        
        // Загружаем переводы для нового языка
        await this.loadTranslations(lang);
        
        // Обновляем UI индикаторы
        this.updateLanguageIndicators();
        
        // Уведомляем сервер об изменении языка
        await this.notifyServerLanguageChange(lang);
        
        // Перезагружаем текущую страницу с новым языком
        await this.reloadCurrentPage();
        
        // Событие для других компонентов
        this.dispatchLanguageChangeEvent(oldLanguage, lang);
        
        console.log(`✅ Язык изменен на: ${lang}`);
    }
    
    async loadTranslations(lang) {
        console.log(`🔄 Загрузка переводов для языка: ${lang}`);
        
        try {
            // Пытаемся загрузить автогенерированный JS модуль
            const response = await fetch(`/static/i18n/generated/${lang}.js?v=${Date.now()}`);
            
            if (response.ok) {
                const jsContent = await response.text();
                
                // Выполняем JS код в безопасной среде
                const script = document.createElement('script');
                script.textContent = jsContent;
                document.head.appendChild(script);
                document.head.removeChild(script);
                
                // Извлекаем переводы из глобальной переменной
                if (window.translations && window.translations[lang]) {
                    this.translations = window.translations[lang];
                    console.log(`✅ Переводы загружены: ${Object.keys(this.translations).length} ключей`);
                } else {
                    throw new Error('Переводы не найдены в JS модуле');
                }
            } else {
                // Fallback: загружаем через API
                await this.loadTranslationsFromAPI(lang);
            }
            
        } catch (error) {
            console.warn(`⚠️ Ошибка загрузки переводов для ${lang}:`, error);
            
            // Fallback: загружаем через API
            await this.loadTranslationsFromAPI(lang);
        }
    }
    
    async loadTranslationsFromAPI(lang) {
        try {
            const response = await fetch(`/frontend/api/i18n/translations/${lang}`);
            if (response.ok) {
                this.translations = await response.json();
                console.log(`✅ Переводы загружены через API: ${Object.keys(this.translations).length} ключей`);
            } else {
                console.warn(`⚠️ Не удалось загрузить переводы через API для ${lang}`);
                this.translations = {};
            }
        } catch (error) {
            console.warn(`⚠️ Ошибка загрузки переводов через API:`, error);
            this.translations = {};
        }
    }
    
    t(key, params = {}) {
        if (!key) return '';
        
        // Ищем перевод
        let translation = this.translations[key];
        
        // Если не найден и это не основной язык, пытаемся найти в fallback
        if (!translation && this.currentLanguage !== this.fallbackLanguage) {
            // Здесь можно было бы загрузить fallback переводы, но пока просто возвращаем ключ
            console.debug(`🔍 Перевод не найден для ключа: ${key} (язык: ${this.currentLanguage})`);
            translation = key;
        }
        
        // Если все еще не найден, возвращаем ключ
        if (!translation) {
            translation = key;
        }
        
        // Подставляем параметры
        if (params && Object.keys(params).length > 0) {
            Object.keys(params).forEach(param => {
                const placeholder = `{${param}}`;
                // Экранируем специальные символы для RegExp
                const escapedPlaceholder = placeholder.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                translation = translation.replace(new RegExp(escapedPlaceholder, 'g'), params[param]);
            });
        }
        
        return translation;
    }
    
    setupHTMXIntercept() {
        // Добавляем язык ко всем HTMX запросам
        document.addEventListener('htmx:configRequest', (event) => {
            event.detail.headers['Accept-Language'] = this.currentLanguage;
        });
        
        console.log('🔌 HTMX перехватчик настроен для автоматической отправки языка');
    }
    
    async notifyServerLanguageChange(lang) {
        try {
            await fetch('/frontend/api/i18n/user-language', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept-Language': lang
                },
                body: JSON.stringify({ language: lang })
            });
        } catch (error) {
            console.warn('⚠️ Не удалось уведомить сервер о смене языка:', error);
        }
    }
    
    async reloadCurrentPage() {
        // При смене языка нужно обновлять ВСЮ страницу, включая header с навигацией
        // поскольку там тоже есть переводы {{ t('dashboard.navigation.bots') }}
        console.log('🔄 Полная перезагрузка страницы для обновления всех переводов');
        window.location.reload();
    }
    
    updateLanguageIndicators() {
        // Обновляем текст текущего языка в dropdown
        const currentLangElement = document.querySelector('#current-language');
        if (currentLangElement) {
            currentLangElement.textContent = this.currentLanguage.toUpperCase();
        }
        
        // Обновляем галочки в dropdown меню
        this.supportedLanguages.forEach(lang => {
            const indicator = document.querySelector(`#lang-${lang}`);
            if (indicator) {
                indicator.style.visibility = (lang === this.currentLanguage) ? 'visible' : 'hidden';
            }
        });
        
        // Устанавливаем атрибут lang на html элемент
        document.documentElement.setAttribute('lang', this.currentLanguage);
        
        // Обновляем класс активного языка в dropdown кнопке
        const languageBtn = document.querySelector('.header-right .dropdown .btn');
        if (languageBtn) {
            // Убираем focus состояние Bootstrap
            languageBtn.blur();
            // Гарантируем правильные классы
            languageBtn.className = 'btn btn-ghost btn-sm';
            languageBtn.setAttribute('data-bs-toggle', 'dropdown');
        }
        
        console.log(`🎨 UI индикаторы языка обновлены для: ${this.currentLanguage}`);
    }
    
    setupDropdownHandlers() {
        // Дополнительная настройка dropdown поведения
        const dropdownBtn = document.querySelector('.header-right .dropdown .btn[data-dropdown-toggle]');
        const dropdown = document.querySelector('.header-right .dropdown');
        const dropdownMenu = document.querySelector('.header-right .dropdown-menu');
        
        if (dropdownBtn && dropdown && dropdownMenu) {
            // Убеждаемся что dropdown изначально закрыт
            dropdownMenu.classList.remove('show');
            dropdownBtn.classList.remove('show');
            dropdownBtn.setAttribute('aria-expanded', 'false');
            
            // Обработчики Bootstrap событий
            dropdownBtn.addEventListener('show.bs.dropdown', () => {
                console.log('🔽 Dropdown открывается');
            });
            
            dropdownBtn.addEventListener('shown.bs.dropdown', () => {
                dropdownBtn.classList.add('show');
                console.log('✅ Dropdown открыт');
            });
            
            dropdownBtn.addEventListener('hide.bs.dropdown', () => {
                console.log('🔼 Dropdown закрывается');
            });
            
            dropdownBtn.addEventListener('hidden.bs.dropdown', () => {
                dropdownBtn.classList.remove('show');
                dropdownBtn.blur();
                console.log('✅ Dropdown закрыт');
            });
            
            // Обработчики для элементов меню
            const menuItems = dropdown.querySelectorAll('.dropdown-item');
            menuItems.forEach(item => {
                item.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    // Закрываем dropdown после клика
                    const dropdownMenu = dropdownBtn.nextElementSibling;
                    if (dropdownMenu && dropdownMenu.classList.contains('dropdown-menu')) {
                        dropdownMenu.classList.remove('show');
                    }
                });
            });
            
            console.log('✅ Dropdown handlers настроены');
        } else {
            console.warn('⚠️ Не удалось найти элементы dropdown для настройки');
        }
    }
    
    dispatchLanguageChangeEvent(oldLang, newLang) {
        const event = new CustomEvent('languageChanged', {
            detail: { oldLanguage: oldLang, newLanguage: newLang }
        });
        document.dispatchEvent(event);
    }
    
    getCurrentLanguage() {
        return this.currentLanguage;
    }
    
    getSupportedLanguages() {
        return [...this.supportedLanguages];
    }
    
    isReady() {
        return this.isInitialized;
    }
    
    // Метод для динамического обновления переводов (полезно для разработки)
    async refreshTranslations() {
        console.log('🔄 Принудительное обновление переводов...');
        await this.loadTranslations(this.currentLanguage);
        console.log('✅ Переводы обновлены');
    }
}

export default LanguageManager;
