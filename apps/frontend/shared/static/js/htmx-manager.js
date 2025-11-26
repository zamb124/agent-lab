/**
 * HTMX Manager - обработка HTMX событий и модальных окон
 */
export default class HTMXManager {
    constructor() {
        this.setupHTMXEvents();
        this.setupModalHandlers();
        this.setupWebSocketHandlers();
    }
    
    setupHTMXEvents() {
        console.log('🔧 Настройка HTMX событий...');
        
        // Обработка модальных окон после загрузки
        document.addEventListener('htmx:afterSwap', (e) => {
            console.log('📥 HTMX afterSwap:', e.detail.target);
            
            // Если это модальное окно - показываем его
            if (e.detail.target.id === 'modal-container') {
                this.showModal();
            }
            
            // Инициализируем Ace Editor после любого HTMX swap
            this.initAceEditors(e.detail.target);
        });
        
        // Обработка ошибок HTMX
        document.addEventListener('htmx:responseError', (e) => {
            console.error('❌ HTMX Error:', e.detail.xhr.status, e.detail.xhr.responseText);
            if (e.detail.xhr.status === 401) {
                window.location.href = '/frontend/auth';
            }
        });
        
        // Анимации для строк таблиц при обновлении
        document.addEventListener('htmx:beforeSwap', (e) => {
            if (e.target.tagName === 'TR' && e.target.hasAttribute('hx-get')) {
                e.target.style.opacity = '0.5';
            }
        });
        
        document.addEventListener('htmx:afterSwap', (e) => {
            if (e.target.tagName === 'TR') {
                setTimeout(() => {
                    e.target.style.opacity = '1';
                }, 100);
            }
        });
        
        console.log('✅ HTMX события настроены');
    }
    
    setupModalHandlers() {
        console.log('🔧 Настройка обработчиков модальных окон...');
        
        // Обработка закрытия модалки по Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModal();
            }
        });
        
        console.log('✅ Обработчики модальных окон настроены');
    }
    
    setupWebSocketHandlers() {
        console.log('🔧 Настройка WebSocket обработчиков...');
        
        // Обработка WebSocket сообщений
        document.addEventListener('htmx:wsAfterMessage', (e) => {
            console.log('📨 WebSocket сообщение получено:', e.detail.message);
            
            try {
                const message = JSON.parse(e.detail.message);
                this.handleWebSocketMessage(message);
            } catch (error) {
                console.error('❌ Ошибка парсинга WebSocket сообщения:', error);
            }
        });
        
        console.log('✅ WebSocket обработчики настроены');
    }
    
    handleWebSocketMessage(message) {
        const { type, data } = message;
        
        switch (type) {
            case 'NOTIFICATION':
                this.showNotification(data);
                break;
            case 'AUTH':
                this.handleAuthMessage(data);
                break;
            case 'ALERT':
                this.showAlert(data);
                break;
            case 'MODEL_UPDATED':
                this.handleModelUpdate(data);
                break;
            default:
                console.warn('⚠️ Неизвестный тип WebSocket сообщения:', type);
        }
    }
    
    showNotification(data) {
        console.log('🔔 Показываем уведомление:', data);
        
        const container = document.getElementById('notifications-container');
        if (!container) return;
        
        const notification = document.createElement('div');
        notification.className = 'notification';
        notification.innerHTML = `
            <div class="alert alert-info">
                <i class="ti ti-info-circle"></i>
                ${data.message || 'Уведомление'}
            </div>
        `;
        
        container.appendChild(notification);
        
        // Автоматически убираем через 5 секунд
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }
    
    handleAuthMessage(data) {
        console.log('🔐 Обработка auth сообщения:', data);
        
        if (data.action === 'logout') {
            window.location.href = '/frontend/auth';
        }
    }
    
    showAlert(data) {
        console.log('⚠️ Показываем alert:', data);
        
        alert(data.message || 'Внимание!');
    }
    
    handleModelUpdate(data) {
        console.log('🔄 Обновление модели:', data);
        
        const { model_type, model_id } = data;
        
        // Находим все элементы с этой моделью
        const elements = document.querySelectorAll(`[data-model-type="${model_type}"][data-model-id="${model_id}"]`);
        
        console.log(`Найдено ${elements.length} элементов для обновления`);
        
        elements.forEach(element => {
            // Обновляем строку таблицы
            if (element.tagName === 'TR') {
                htmx.ajax('GET', `/frontend/models/${model_type}/${model_id}?view=table&parent_view_mode=table`, {
                    target: element,
                    swap: 'outerHTML'
                });
            }
            // Обновляем форму
            else if (element.tagName === 'FORM') {
                htmx.ajax('GET', `/frontend/models/${model_type}/${model_id}?view=form`, {
                    target: element,
                    swap: 'outerHTML'
                });
            }
        });
    }
    
    showModal() {
        console.log('🔍 Показываем модальное окно...');
        
        const modalContainer = document.getElementById('modal-container');
        if (!modalContainer) {
            console.error('❌ modal-container не найден');
            return;
        }
        
        const modalOverlay = modalContainer.querySelector('.modal-overlay');
        if (modalOverlay) {
            console.log('✅ Модальное окно найдено, показываем...');
            
            // Принудительно устанавливаем стили
            modalOverlay.style.cssText = `
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                z-index: 99999 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                background: rgba(0,0,0,0.8) !important;
                margin: 0 !important;
                padding: 20px !important;
                width: 100vw !important;
                height: 100vh !important;
                opacity: 1 !important;
                visibility: visible !important;
                pointer-events: auto !important;
            `;
            
            // Блокируем скролл body
            document.body.style.overflow = 'hidden';
            
            // Принудительно перемещаем модалку в body (на случай если она где-то глубоко)
            document.body.appendChild(modalOverlay);
            
            console.log('✅ Модальное окно показано');
            console.log('Позиция модалки:', modalOverlay.getBoundingClientRect());
        } else {
            console.error('❌ modal-overlay не найден в modal-container');
            console.log('modalContainer содержимое:', modalContainer.innerHTML);
        }
    }
    
    closeModal() {
        console.log('❌ Закрываем модальное окно...');
        
        const modalContainer = document.getElementById('modal-container');
        if (modalContainer) {
            const modalOverlay = modalContainer.querySelector('.modal-overlay');
            if (modalOverlay) {
                // Плавное исчезновение
                modalOverlay.style.opacity = '0';
                setTimeout(() => {
                    modalOverlay.remove();
                    // Разблокируем скролл body
                    document.body.style.overflow = '';
                }, 200);
            }
        }
    }
    
    initAceEditors(targetElement = document) {
        // Находим все контейнеры для code-editor
        const codeContainers = targetElement.querySelectorAll('.code-editor-container');
        
        if (codeContainers.length === 0) {
            return;
        }
        
        console.log(`📝 Найдено ${codeContainers.length} code editor контейнеров`);
        
        codeContainers.forEach(container => {
            const fieldName = container.dataset.fieldName;
            const containerId = container.id;
            
            if (!fieldName || !containerId) {
                console.warn('⚠️ Container без fieldName или id');
                return;
            }
            
            // Проверяем что контейнер еще не инициализирован
            if (container.dataset.aceInitialized === 'true') {
                console.log(`⏭️ Ace Editor уже инициализирован для ${fieldName}`);
                return;
            }
            
            // Проверяем что Ace загружен
            if (typeof ace === 'undefined') {
                console.error('❌ Ace Editor не загружен!');
                return;
            }
            
            console.log(`✅ Инициализируем Ace Editor для ${fieldName}`);
            
            try {
                // Проверяем что CodeEditor класс доступен
                if (typeof CodeEditor === 'undefined') {
                    console.error('❌ CodeEditor класс не найден! Используем простой Ace');
                    // Fallback на простой Ace
                    const editor = ace.edit(containerId);
                    editor.setTheme('ace/theme/monokai');
                    editor.session.setMode('ace/mode/python');
                    const textarea = document.getElementById(fieldName);
                    if (textarea) {
                        editor.setValue(textarea.value || '', -1);
                    }
                } else {
                    // Используем полноценный CodeEditor компонент
                    const textarea = document.getElementById(fieldName);
                    const initialValue = textarea ? textarea.value : '';
                    
                    // Получаем flowId из builder если есть
                    const flowId = window.builder?.currentFlow?.flow_id || null;
                    
                    const codeEditor = new CodeEditor({
                        container: `#${containerId}`,
                        value: initialValue,
                        mode: 'python',
                        height: '400px',
                        flowId: flowId,
                        onChange: (value) => {
                            if (textarea) {
                                textarea.value = value;
                                const event = new Event('change', { bubbles: true });
                                textarea.dispatchEvent(event);
                            }
                        }
                    });
                    
                    console.log(`✅ CodeEditor (с панелью) инициализирован для ${fieldName}, flowId:`, flowId);
                }
                
                // Помечаем как инициализированный
                container.dataset.aceInitialized = 'true';
                
            } catch (error) {
                console.error(`❌ Ошибка инициализации CodeEditor для ${fieldName}:`, error);
            }
        });
    }
}
