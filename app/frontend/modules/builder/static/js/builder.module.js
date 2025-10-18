/**
 * Builder Module - Визуальный редактор flows
 */

export default class BuilderModule {
    constructor(app) {
        this.app = app;
        this.name = 'builder';
        this.version = '1.0.0';
        
        this.Canvas = null;
        this.DragDrop = null;
        this.Palette = null;
        this.PropertiesPanel = null;
        this.ElementSelector = null;
        
        this.currentCanvas = null;
        this.currentDragDrop = null;
    }
    
    /**
     * Инициализация модуля
     */
    async init() {
        console.log('🎨 Инициализация Builder модуля');
        
        this.setupEventListeners();
        
        if (this.isBuilderPage()) {
            await this.loadDependencies();
            await this.initializeBuilder();
        }
        
        return this;
    }
    
    /**
     * Проверка, находимся ли на странице builder
     */
    isBuilderPage() {
        return window.location.pathname.startsWith('/frontend/builder');
    }
    
    /**
     * Lazy loading зависимостей
     */
    async loadDependencies() {
        if (this.Canvas) {
            return;
        }
        
        console.log('📦 Загружаем зависимости Builder...');
        
        try {
            const [Canvas, DragDrop, Palette, PropertiesPanel, ElementSelector] = await Promise.all([
                import('/static/builder/js/canvas.js'),
                import('/static/builder/js/drag-drop.js'),
                import('/static/builder/js/palette.js'),
                import('/static/builder/js/properties-panel.js'),
                import('/static/builder/js/element-selector.js')
            ]);
            
            this.Canvas = Canvas.default;
            this.DragDrop = DragDrop.default;
            this.Palette = Palette.default;
            this.PropertiesPanel = PropertiesPanel.default;
            this.ElementSelector = ElementSelector.default;
            
            console.log('✅ Зависимости Builder загружены');
        } catch (error) {
            console.error('❌ Ошибка загрузки зависимостей Builder:', error);
            throw error;
        }
    }
    
    /**
     * Инициализация Builder на странице
     */
    async initializeBuilder() {
        console.log('🎨 Инициализация Builder на странице');
        
        const canvasContainer = document.querySelector('.builder-canvas');
        if (!canvasContainer) {
            console.warn('⚠️ Builder canvas не найден на странице');
            return;
        }
        
        try {
            await this.loadDependencies();
            
            this.currentCanvas = new this.Canvas();
            this.currentDragDrop = new this.DragDrop(this.currentCanvas);
            
            console.log('✅ Builder инициализирован');
        } catch (error) {
            console.error('❌ Ошибка инициализации Builder:', error);
        }
    }
    
    /**
     * События модуля
     */
    setupEventListeners() {
        document.addEventListener('htmx:afterSettle', (e) => {
            if (e.target.id === 'content' && this.isBuilderPage()) {
                this.onPageLoad();
            }
        });
        
        window.addEventListener('popstate', () => {
            if (this.isBuilderPage()) {
                this.onPageLoad();
            } else {
                this.onPageUnload();
            }
        });
    }
    
    /**
     * Вызывается при загрузке страницы Builder
     */
    async onPageLoad() {
        console.log('📄 Builder страница загружена');
        await this.initializeBuilder();
    }
    
    /**
     * Вызывается при уходе со страницы Builder
     */
    onPageUnload() {
        console.log('👋 Уход со страницы Builder');
        this.cleanup();
    }
    
    /**
     * Публичный API
     */
    
    openFlow(flowId) {
        window.location.href = `/frontend/builder/flow/${flowId}`;
    }
    
    createNewFlow() {
        console.log('Creating new flow');
    }
    
    saveCurrentFlow() {
        if (this.currentCanvas) {
            return this.currentCanvas.save();
        }
        console.warn('⚠️ Нет активного canvas для сохранения');
        return null;
    }
    
    /**
     * Cleanup при выгрузке
     */
    cleanup() {
        if (this.currentCanvas && typeof this.currentCanvas.destroy === 'function') {
            this.currentCanvas.destroy();
        }
        if (this.currentDragDrop && typeof this.currentDragDrop.destroy === 'function') {
            this.currentDragDrop.destroy();
        }
        
        this.currentCanvas = null;
        this.currentDragDrop = null;
    }
    
    /**
     * Полное уничтожение модуля
     */
    destroy() {
        console.log('🧹 Builder модуль выгружен');
        this.cleanup();
    }
}

