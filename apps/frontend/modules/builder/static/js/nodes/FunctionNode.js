import { BaseNode } from '../core/BaseNode.js';

/**
 * Нода для кастомного кода/функций
 */
export class FunctionNode extends BaseNode {
    /**
     * Создание DOM элемента
     */
    async createDOMElement() {
        const element = document.createElement('div');
        element.className = 'canvas-node function-node';
        
        element.innerHTML = this.renderTemplate();
        
        return element;
    }
    
    /**
     * Создание портов
     */
    async createPorts() {
        // Function имеет входной и выходной порты
        this.createPort('input', 'input');
        this.createPort('output', 'output');
        this.mountPorts();
    }
    
    /**
     * Рендеринг шаблона
     */
    renderTemplate() {
        const name = this.data.params?.name || 'Function';
        const description = this.data.params?.description || 'Custom code';
        
        const displayName = name.length > 30 ? name.substring(0, 27) + '...' : name;
        const displayDesc = description.length > 25 ? description.substring(0, 22) + '...' : description;
        
        return `
            <div class="node-simple-content">
                <div class="node-simple-icon function">
                    <i class="ti ti-code"></i>
                </div>
                <div class="node-simple-info">
                    <div class="node-simple-title">${this.escapeHtml(displayName)}</div>
                    <div class="node-simple-desc">${this.escapeHtml(displayDesc)}</div>
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

