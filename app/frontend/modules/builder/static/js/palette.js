/**
 * NodePalette - управление палитрой компонентов
 */

export default class NodePalette {
    constructor(builder) {
        this.builder = builder;
        this.element = document.getElementById('nodePalette');
        
        this.nodeTypes = {
            'flow_node': {
                icon: 'bi-diagram-3',
                color: '#3b82f6',
                label: 'Flow',
                desc: 'Entry point'
            },
            'agent_node': {
                icon: 'bi-robot',
                color: '#8b5cf6',
                label: 'Agent',
                desc: 'AI agent'
            },
            'tool_node': {
                icon: 'bi-tools',
                color: '#10b981',
                label: 'Tool',
                desc: 'Function call'
            },
            'function_node': {
                icon: 'bi-code-square',
                color: '#f59e0b',
                label: 'Function',
                desc: 'Custom code'
            },
            'message_node': {
                icon: 'bi-chat-dots',
                color: '#06b6d4',
                label: 'Message',
                desc: 'Send message'
            },
            'router_node': {
                icon: 'bi-lightning',
                color: '#ef4444',
                label: 'Router',
                desc: 'Router logic'
            }
        };
    }
    
    init() {
        console.log('🎨 Инициализация Palette...');
        this.setupEventListeners();
        console.log('✅ Palette инициализирована');
    }
    
    setupEventListeners() {
        const paletteItems = this.element.querySelectorAll('.palette-item');
        console.log(`📋 Найдено ${paletteItems.length} элементов палитры`);
        
        paletteItems.forEach(item => {
            item.addEventListener('dragstart', (e) => this.handleDragStart(e));
            item.addEventListener('dragend', (e) => this.handleDragEnd(e));
            console.log(`✅ Обработчики добавлены для ${item.dataset.nodeType}`);
        });
        
        // Кнопка сворачивания
        const collapseBtn = document.getElementById('collapsePaletteBtn');
        if (collapseBtn) {
            collapseBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleCollapse();
            });
        }
        
        // Клик на заголовок тоже сворачивает
        const header = document.getElementById('paletteHeader');
        if (header) {
            header.addEventListener('click', () => this.toggleCollapse());
        }
    }
    
    toggleCollapse() {
        this.element.classList.toggle('collapsed');
        console.log('🔄 Palette collapsed:', this.element.classList.contains('collapsed'));
    }
    
    handleDragStart(e) {
        const nodeType = e.target.closest('.palette-item').dataset.nodeType;
        
        e.dataTransfer.effectAllowed = 'copy';
        e.dataTransfer.setData('application/x-node-type', nodeType);
        e.dataTransfer.setData('text/plain', nodeType);
        
        e.target.closest('.palette-item').classList.add('dragging');
        
        console.log('🎨 Начало drag из palette:', nodeType);
    }
    
    handleDragEnd(e) {
        e.target.closest('.palette-item').classList.remove('dragging');
    }
}

