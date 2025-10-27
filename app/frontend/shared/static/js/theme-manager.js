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
            themeBtn.className = this.currentTheme === 'dark' ? 'bi bi-sun' : 'bi bi-moon';
        }
    }
    
    setupThemeToggle() {
        const toggleBtn = document.querySelector('[data-theme-toggle]');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggleTheme());
        }
    }
}

export default ThemeManager;
