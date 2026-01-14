/**
 * Сервис управления темой
 */
import { AppEvents } from '../lib/utils/types.js';

const THEME_KEY = 'platform_theme';

export class ThemeService {
    constructor() {
        /** @type {'dark'|'light'} */
        this.theme = 'dark';
        this._loadFromStorage();
    }

    /**
     * Инициализация
     */
    init() {
        this._applyTheme();
        
        // Следим за системными настройками
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!localStorage.getItem(THEME_KEY)) {
                this.theme = e.matches ? 'dark' : 'light';
                this._applyTheme();
            }
        });
    }

    /**
     * Загрузить из localStorage или системных настроек
     */
    _loadFromStorage() {
        const saved = localStorage.getItem(THEME_KEY);
        
        if (saved) {
            this.theme = saved;
        } else {
            // Используем системную тему
            this.theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
    }

    /**
     * Применить тему к документу
     */
    _applyTheme() {
        document.documentElement.setAttribute('data-theme', this.theme);
        
        // Обновляем meta theme-color для PWA
        const themeColor = this.theme === 'dark' ? '#0a0a0c' : '#ffffff';
        document.querySelector('meta[name="theme-color"]')?.setAttribute('content', themeColor);
    }

    /**
     * Переключить тему
     */
    toggle() {
        this.theme = this.theme === 'dark' ? 'light' : 'dark';
        localStorage.setItem(THEME_KEY, this.theme);
        this._applyTheme();
        this._dispatchChange();
    }

    /**
     * Установить конкретную тему
     * @param {'dark'|'light'} theme
     */
    setTheme(theme) {
        this.theme = theme;
        localStorage.setItem(THEME_KEY, theme);
        this._applyTheme();
        this._dispatchChange();
    }

    /**
     * Текущая тема тёмная?
     */
    get isDark() {
        return this.theme === 'dark';
    }

    /**
     * Получить текущую тему
     */
    get currentTheme() {
        return this.theme;
    }

    /**
     * Диспатчить событие изменения темы
     */
    _dispatchChange() {
        window.dispatchEvent(new CustomEvent(AppEvents.THEME_CHANGE, {
            detail: { theme: this.theme }
        }));
    }
}


