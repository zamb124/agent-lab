import { BaseNode } from '../core/BaseNode.js';

/**
 * Нода для сообщений (конечная точка)
 */
export class MessageNode extends BaseNode {
    /**
     * Создание DOM элемента
     */
    async createDOMElement() {
        const element = document.createElement('div');
        element.className = 'canvas-node message-node';
        
        element.innerHTML = this.renderTemplate();
        
        return element;
    }
    
    /**
     * Создание портов
     */
    async createPorts() {
        // Message имеет только входной порт (конечная точка)
        this.createPort('input', 'input');
        this.mountPorts();
    }
    
    /**
     * Рендеринг шаблона
     */
    renderTemplate() {
        const message = this.data.params?.message || 'Send message';
        const displayMessage = message.length > 40 ? message.substring(0, 37) + '...' : message;
        
        return `
            <div class="node-simple-content">
                <div class="node-simple-icon message">
                    <i class="bi bi-chat-dots"></i>
                </div>
                <div class="node-simple-info">
                    <div class="node-simple-title">Message</div>
                    <div class="node-simple-desc">${this.escapeHtml(displayMessage)}</div>
                </div>
            </div>
        `;
    }
    
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

