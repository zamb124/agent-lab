/**
 * ThemeManager - управление темой приложения
 */

import { getCookie, setCookie } from '/static/js/utils/cookies.js';

class ThemeManager {
    constructor() {
        this.currentTheme = 'light';
        this.init();
    }
    
    init() {
        this.loadTheme();
        this.setupThemeToggle();
    }
    
    loadTheme() {
        const savedTheme = localStorage.getItem('theme') || getCookie('theme') || 'light';
        this.setTheme(savedTheme);
    }
    
    setTheme(theme) {
        this.currentTheme = theme;
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        setCookie('theme', theme, 365);
        
        // Обновляем иконку кнопки переключения
        this.updateThemeIcon();
    }
    
    toggleTheme() {
        const newTheme = this.currentTheme === 'dark' ? 'light' : 'dark';
        this.setTheme(newTheme);
    }
    
    updateThemeIcon() {
        const themeBtn = document.querySelector('[data-theme-toggle] i');
        if (themeBtn) {
            themeBtn.className = this.currentTheme === 'dark' ? 'ti ti-sun' : 'ti ti-moon';
        }
    }
    
    setupThemeToggle() {
        // Используем делегирование событий на уровне document
        // Это работает даже если кнопка заменяется через HTMX
        document.removeEventListener('click', this._handleThemeToggle);
        this._handleThemeToggle = (e) => {
            const toggleBtn = e.target.closest('[data-theme-toggle]');
            if (toggleBtn) {
                e.preventDefault();
                e.stopPropagation();
                this.toggleTheme();
            }
        };
        document.addEventListener('click', this._handleThemeToggle);
        this.updateThemeIcon();
    }
    
    reinitialize() {
        // При HTMX обновлениях просто обновляем иконку
        this.updateThemeIcon();
    }
}

export default ThemeManager;
