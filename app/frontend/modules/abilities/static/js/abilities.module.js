/**
 * Abilities Module
 */

export default class AbilitiesModule {
    constructor(app) {
        this.app = app;
        this.name = 'abilities';
        this.version = '1.0.0';
    }
    
    async init() {
        console.log('✅ Abilities модуль инициализирован');
        
        this.setupGlobalFunctions();
        this.setupEventListeners();
        
        if (this.isAbilitiesPage()) {
            await this.initializePage();
        }
        
        return this;
    }
    
    setupGlobalFunctions() {
        window.showAbilityDetails = (id, type) => this.showDetails(id, type);
    }
    
    setupEventListeners() {
        document.addEventListener('htmx:afterSettle', (e) => {
            if (e.target.id === 'content' && this.isAbilitiesPage()) {
                this.onPageLoad();
            }
        });
        
        window.addEventListener('popstate', () => {
            if (this.isAbilitiesPage()) {
                this.onPageLoad();
            }
        });
    }
    
    isAbilitiesPage() {
        return window.location.pathname.startsWith('/frontend/abilities');
    }
    
    async initializePage() {
        console.log('🔧 Инициализация страницы Abilities');
        this.attachCardEventListeners();
    }
    
    onPageLoad() {
        console.log('📄 Abilities страница загружена');
        this.attachCardEventListeners();
    }
    
    attachCardEventListeners() {
        const cards = document.querySelectorAll('.ability-card');
        cards.forEach(card => {
            const id = card.dataset.id;
            const type = card.dataset.type;
            
            card.style.cursor = 'pointer';
        });
    }
    
    async showDetails(id, type) {
        console.log(`📋 Показываем детали ${type}: ${id}`);
        
        try {
            const modelType = type === 'agent' ? 'agent' : 'tool';
            const url = `/frontend/models/${modelType}/${encodeURIComponent(id)}?view=form`;
            
            console.log(`🔍 Загрузка формы из: ${url}`);
            
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const formHtml = await response.text();
            
            const modalHtml = `
                <div class="modal-overlay" style="display: flex;">
                    <div class="modal-content modal-lg">
                        <button class="btn btn-ghost btn-sm" 
                                style="position: absolute; top: 1rem; right: 1rem; z-index: 10;"
                                onclick="this.closest('.modal-overlay').remove(); document.body.style.overflow = '';">
                            <i class="bi bi-x"></i>
                        </button>
                        <div class="modal-body" style="padding: 0;">
                            ${formHtml}
                        </div>
                    </div>
                </div>
            `;
            
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = modalHtml;
            const modalElement = tempDiv.firstElementChild;
            
            modalElement.addEventListener('click', (e) => {
                if (e.target === modalElement) {
                    modalElement.remove();
                    document.body.style.overflow = '';
                }
            });
            
            document.body.appendChild(modalElement);
            document.body.style.overflow = 'hidden';
            
            await this.initializeFormComponents(modalElement);
            
        } catch (error) {
            console.error('Ошибка загрузки формы:', error);
            
            const errorModal = `
                <div class="modal-overlay" style="display: flex;">
                    <div class="modal-content modal-md">
                        <div class="modal-header">
                            <h4 class="modal-title">
                                <i class="bi bi-exclamation-triangle text-danger"></i>
                                Ошибка
                            </h4>
                            <button class="btn btn-ghost btn-sm" onclick="this.closest('.modal-overlay').remove(); document.body.style.overflow = '';">
                                <i class="bi bi-x"></i>
                            </button>
                        </div>
                        <div class="modal-body">
                            <div class="alert alert-danger">
                                <i class="bi bi-exclamation-triangle"></i>
                                Ошибка загрузки: ${error.message}
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = errorModal;
            document.body.appendChild(tempDiv.firstElementChild);
        }
    }
    
    async initializeFormComponents(container) {
        console.log('🔧 Инициализация компонентов формы...');
        
        await new Promise(resolve => setTimeout(resolve, 100));
        
        if (window.htmxManager && typeof window.htmxManager.initAceEditors === 'function') {
            console.log('📝 Инициализация Ace редакторов...');
            window.htmxManager.initAceEditors(container);
        } else {
            console.warn('⚠️ htmxManager не найден, пробуем альтернативный способ');
            this.initCodeEditorsManually(container);
        }
        
        if (typeof htmx !== 'undefined') {
            htmx.process(container);
        }
    }
    
    initCodeEditorsManually(container) {
        const codeContainers = container.querySelectorAll('.code-editor-container');
        
        if (codeContainers.length === 0) {
            console.log('ℹ️ Код редакторы не найдены в форме');
            return;
        }
        
        console.log(`📦 Найдено ${codeContainers.length} код редакторов`);
        
        codeContainers.forEach(editorContainer => {
            const fieldName = editorContainer.dataset.fieldName;
            const containerId = editorContainer.id;
            
            if (!containerId) {
                console.warn('⚠️ У контейнера нет ID:', editorContainer);
                return;
            }
            
            if (editorContainer.dataset.initialized === 'true') {
                console.log(`⏭️ Редактор ${fieldName} уже инициализирован`);
                return;
            }
            
            try {
                if (typeof CodeEditor !== 'undefined') {
                    const textarea = document.getElementById(fieldName);
                    const initialValue = textarea ? textarea.value : '';
                    
                    const codeEditor = new CodeEditor({
                        container: `#${containerId}`,
                        value: initialValue,
                        mode: 'python',
                        height: '400px',
                        onChange: (value) => {
                            if (textarea) {
                                textarea.value = value;
                                const event = new Event('change', { bubbles: true });
                                textarea.dispatchEvent(event);
                            }
                        }
                    });
                    
                    editorContainer.dataset.initialized = 'true';
                    console.log(`✅ CodeEditor инициализирован для ${fieldName}`);
                } else {
                    console.error('❌ CodeEditor класс не найден');
                }
            } catch (error) {
                console.error(`❌ Ошибка инициализации редактора ${fieldName}:`, error);
            }
        });
    }
    
    destroy() {
        console.log('🧹 Abilities модуль выгружен');
    }
}

