/**
 * Менеджер JS плагинов
 * Загружает и управляет модулями фронтенда
 */

class PluginManager {
    constructor(app) {
        this.app = app;
        this.plugins = new Map();
        this.loaded = new Set();
        this.loading = new Map();
    }
    
    /**
     * Регистрация плагина
     */
    async register(name, modulePath) {
        if (this.plugins.has(name)) {
            console.warn(`⚠️ Плагин ${name} уже зарегистрирован`);
            return this.plugins.get(name);
        }
        
        if (this.loading.has(name)) {
            return await this.loading.get(name);
        }
        
        const loadPromise = this._loadPlugin(name, modulePath);
        this.loading.set(name, loadPromise);
        
        try {
            const instance = await loadPromise;
            this.loading.delete(name);
            return instance;
        } catch (error) {
            this.loading.delete(name);
            throw error;
        }
    }
    
    /**
     * Внутренняя загрузка плагина
     */
    async _loadPlugin(name, modulePath) {
        try {
            console.log(`📦 Загружаем плагин: ${name}`);
            
            const module = await import(modulePath);
            const PluginClass = module.default;
            
            if (!PluginClass) {
                throw new Error(`Плагин ${name} не экспортирует default класс`);
            }
            
            const instance = new PluginClass(this.app);
            
            if (typeof instance.init === 'function') {
                await instance.init();
            }
            
            this.plugins.set(name, instance);
            this.loaded.add(name);
            
            this.app[name] = instance;
            
            console.log(`✅ Плагин ${name} загружен`);
            
            return instance;
            
        } catch (error) {
            console.error(`❌ Ошибка загрузки плагина ${name}:`, error);
            throw error;
        }
    }
    
    /**
     * Получить плагин
     */
    get(name) {
        return this.plugins.get(name);
    }
    
    /**
     * Проверить загружен ли плагин
     */
    isLoaded(name) {
        return this.loaded.has(name);
    }
    
    /**
     * Выгрузить плагин
     */
    async unload(name) {
        const plugin = this.plugins.get(name);
        if (!plugin) {
            console.warn(`⚠️ Плагин ${name} не найден`);
            return;
        }
        
        if (typeof plugin.destroy === 'function') {
            try {
                await plugin.destroy();
            } catch (error) {
                console.error(`Ошибка при выгрузке плагина ${name}:`, error);
            }
        }
        
        this.plugins.delete(name);
        this.loaded.delete(name);
        delete this.app[name];
        
        console.log(`🗑️ Плагин ${name} выгружен`);
    }
    
    /**
     * Перезагрузить плагин (для разработки)
     */
    async reload(name) {
        const plugin = this.plugins.get(name);
        if (!plugin) {
            console.warn(`⚠️ Плагин ${name} не найден`);
            return;
        }
        
        const modulePath = `/static/${name}/js/${name}.module.js?t=${Date.now()}`;
        
        await this.unload(name);
        return await this.register(name, modulePath);
    }
    
    /**
     * Получить все загруженные плагины
     */
    getAll() {
        return Array.from(this.plugins.values());
    }
    
    /**
     * Получить имена всех загруженных плагинов
     */
    getLoadedNames() {
        return Array.from(this.loaded);
    }
}

export default PluginManager;

