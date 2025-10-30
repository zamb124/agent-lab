import { EventEmitter } from '../core/EventEmitter.js';

/**
 * ContextMenuManager - управление контекстным меню нод
 */
export class ContextMenuManager extends EventEmitter {
    constructor(canvas) {
        super();
        
        this.canvas = canvas;
        this.contextMenu = null;
        this.currentNode = null;
    }
    
    /**
     * Показать контекстное меню для ноды
     */
    showNodeMenu(node, event) {
        this.closeMenu();
        
        this.currentNode = node;
        
        const html = `
            <div class="node-context-menu">
                <button class="context-menu-option" data-action="edit">
                    <i class="ti ti-pencil"></i>
                    <span>Изменить</span>
                </button>
                <button class="context-menu-option" data-action="delete">
                    <i class="ti ti-trash"></i>
                    <span>Удалить</span>
                </button>
                <button class="context-menu-option" data-action="duplicate">
                    <i class="ti ti-files"></i>
                    <span>Копировать</span>
                </button>
            </div>
        `;
        
        this.showMenu(html, event.clientX, event.clientY);
        
        // Обработчики
        const options = this.contextMenu.querySelectorAll('.context-menu-option');
        options.forEach(option => {
            option.addEventListener('click', () => {
                const action = option.dataset.action;
                this.handleMenuAction(action);
            });
        });
    }
    
    /**
     * Обработка действий контекстного меню
     */
    handleMenuAction(action) {
        if (!this.currentNode) return;
        
        switch (action) {
            case 'edit':
                this.editNode(this.currentNode);
                break;
            case 'delete':
                this.deleteNodeWithChildren(this.currentNode);
                break;
            case 'duplicate':
                this.duplicateNode(this.currentNode);
                break;
        }
        
        this.closeMenu();
    }
    
    /**
     * Редактирование ноды - открытие properties panel
     */
    editNode(node) {
        console.log('✏️ Редактирование ноды:', node.id);
        this.emit('node:edit', { node });
    }
    
    /**
     * Удаление ноды вместе с детьми
     */
    deleteNodeWithChildren(node) {
        if (!confirm(`Удалить элемент "${node.data.params?.name || node.type}"?\nВсе дочерние элементы тоже будут удалены.`)) {
            return;
        }
        
        console.log('🗑️ Удаление ноды с детьми:', node.id);
        
        // Получаем всех детей рекурсивно
        const childrenToDelete = this.getAllChildren(node);
        
        console.log(`📊 Будет удалено: 1 нода + ${childrenToDelete.length} детей`);
        
        // Удаляем всех детей
        childrenToDelete.forEach(childNode => {
            this.canvas.removeNode(childNode.id, false);
        });
        
        // Удаляем саму ноду
        this.canvas.removeNode(node.id, true);
        
        this.emit('node:deleted', { nodeId: node.id, childrenCount: childrenToDelete.length });
    }
    
    /**
     * Получение всех детей рекурсивно
     */
    getAllChildren(node) {
        const children = [];
        const visited = new Set();
        
        const collectChildren = (currentNode) => {
            const directChildren = currentNode.getChildNodes();
            
            directChildren.forEach(child => {
                if (!visited.has(child.id)) {
                    visited.add(child.id);
                    children.push(child);
                    collectChildren(child);
                }
            });
        };
        
        collectChildren(node);
        
        return children;
    }
    
    /**
     * Дублирование ноды
     */
    duplicateNode(node) {
        console.log('📋 Дублирование ноды:', node.id);
        
        // Копируем данные ноды
        const duplicateData = {
            ...node.data,
            id: `${node.type}_${Date.now()}`,
            params: {
                ...node.data.params,
                name: `${node.data.params?.name || node.type} (копия)`
            },
            ui: {
                x: node.x + 50,
                y: node.y + 50,
                width: node.width,
                height: node.height
            }
        };
        
        // Создаем дубликат БЕЗ автоматического разворачивания
        this.canvas.addNode(duplicateData, { autoExpand: false });
        
        this.emit('node:duplicated', { originalNode: node });
    }
    
    /**
     * Показать меню в позиции
     */
    showMenu(html, x, y) {
        const menu = document.createElement('div');
        menu.id = 'nodeContextMenu';
        menu.style.position = 'fixed';
        menu.style.left = `${x}px`;
        menu.style.top = `${y}px`;
        menu.style.zIndex = '10000';
        menu.innerHTML = html;
        
        document.body.appendChild(menu);
        this.contextMenu = menu;
        
        // Закрытие по клику вне меню
        setTimeout(() => {
            this.setupOutsideClickHandler();
        }, 100);
        
        // ESC для закрытия
        this.handleEsc = (e) => {
            if (e.key === 'Escape') {
                this.closeMenu();
            }
        };
        document.addEventListener('keydown', this.handleEsc);
    }
    
    /**
     * Настройка закрытия по клику вне меню
     */
    setupOutsideClickHandler() {
        this.handleOutsideClick = (e) => {
            if (this.contextMenu && !this.contextMenu.contains(e.target)) {
                this.closeMenu();
            }
        };
        
        document.addEventListener('click', this.handleOutsideClick);
    }
    
    /**
     * Закрытие меню
     */
    closeMenu() {
        if (this.contextMenu) {
            this.contextMenu.remove();
            this.contextMenu = null;
        }
        
        if (this.handleEsc) {
            document.removeEventListener('keydown', this.handleEsc);
            this.handleEsc = null;
        }
        
        if (this.handleOutsideClick) {
            document.removeEventListener('click', this.handleOutsideClick);
            this.handleOutsideClick = null;
        }
        
        this.currentNode = null;
    }
}

