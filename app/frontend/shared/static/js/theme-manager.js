/**
 * ThemeManager - управление темой приложения
 */
class ThemeManager {
    constructor() {
        this.currentTheme = 'dark';
        this.init();
    }
    
    init() {
        this.loadTheme();
        this.setupThemeToggle();
    }
    
    loadTheme() {
        // Загружаем тему из localStorage или куки
        const savedTheme = localStorage.getItem('theme') || this.getCookie('theme') || 'dark';
        this.setTheme(savedTheme);
    }
    
    setTheme(theme) {
        this.currentTheme = theme;
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        this.setCookie('theme', theme, 365);
        
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
        // Находим кнопку переключения темы
        const toggleBtn = document.querySelector('[data-theme-toggle]');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggleTheme());
        }
    }
    
    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }
    
    setCookie(name, value, days) {
        const expires = new Date();
        expires.setTime(expires.getTime() + (days * 24 * 60 * 60 * 1000));
        document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/`;
    }
}

export default ThemeManager;
