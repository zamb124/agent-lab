/**
 * Кэш для загрузки CSS стилей и создания CSSStyleSheet
 */

class StyleCacheClass {
    cache: Map<string, CSSStyleSheet>;

    constructor() {
        this.cache = new Map();
    }

    /**
     * Загрузить стили и создать CSSStyleSheet
     * @param {string} path - путь к CSS файлу
     * @returns {Promise<CSSStyleSheet>}
     */
    async load(path: string): Promise<CSSStyleSheet> {
        if (this.cache.has(path)) {
            const cached = this.cache.get(path);
            if (cached === undefined) {
                throw new Error(`style cache: ${path} missing`);
            }
            return cached;
        }

        const url = path.startsWith('/') ? path : `/ui/static/styles/${path}`;
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`Stylesheet not found: ${path}`);
        }

        const cssText = await response.text();
        const sheet = new CSSStyleSheet();
        sheet.replaceSync(cssText);
        
        this.cache.set(path, sheet);
        return sheet;
    }

    /**
     * Получить уже загруженный стиль (синхронно)
     * @param {string} path
     * @returns {CSSStyleSheet|null}
     */
    get(path: string): CSSStyleSheet | null {
        const sheet = this.cache.get(path);
        return sheet === undefined ? null : sheet;
    }

    /**
     * Создать inline CSSStyleSheet из строки
     * @param {string} css - CSS строка
     * @param {string} [key] - ключ для кэширования
     * @returns {CSSStyleSheet}
     */
    fromString(css: string, key?: string): CSSStyleSheet {
        if (key && this.cache.has(key)) {
            const cached = this.cache.get(key);
            if (cached === undefined) {
                throw new Error(`style cache: ${key} missing`);
            }
            return cached;
        }

        const sheet = new CSSStyleSheet();
        sheet.replaceSync(css);
        
        if (key) {
            this.cache.set(key, sheet);
        }
        
        return sheet;
    }

    /**
     * Очистить кэш
     */
    clear() {
        this.cache.clear();
    }
}

export const StyleCache = new StyleCacheClass();


