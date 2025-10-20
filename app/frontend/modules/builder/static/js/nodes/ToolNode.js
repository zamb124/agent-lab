import { BaseNode } from '../core/BaseNode.js';

/**
 * Нода для инструментов (тулов)
 */
export class ToolNode extends BaseNode {
    constructor(data, canvas) {
        super(data, canvas);
        this.toolData = null;
    }
    
    /**
     * Создание DOM элемента
     */
    async createDOMElement() {
        const element = document.createElement('div');
        element.className = 'canvas-node tool-node';
        
        const toolId = this.data.params?.tool_id;
        if (toolId) {
            this.toolData = await this.fetchToolData(toolId);
        }
        
        element.innerHTML = this.renderTemplate();
        
        return element;
    }
    
    /**
     * Создание портов
     */
    async createPorts() {
        const agentType = this.canvas.builder?.entryPointAgentType;
        
        // Входной порт есть всегда
        this.createPort('input', 'input');
        
        // Выходной порт только для StateGraph (не для ReAct)
        if (agentType !== 'react') {
            this.createPort('output', 'output');
        }
        
        this.mountPorts();
    }
    
    /**
     * Загрузка данных тула из API
     */
    async fetchToolData(toolId) {
        try {
            const encodedToolId = encodeURIComponent(toolId);
            const response = await fetch(`/frontend/api/tools/${encodedToolId}`);
            
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.warn('Ошибка загрузки данных тула:', error);
        }
        
        return null;
    }
    
    /**
     * Рендеринг шаблона
     */
    renderTemplate() {
        const name = this.toolData?.name || this.data.params?.name || 'Tool';
        const description = this.toolData?.description || this.data.params?.description || '';
        
        // Обрезаем название
        const displayName = name.length > 30 ? name.substring(0, 27) + '...' : name;
        
        // Обрезаем описание
        const displayDesc = description.length > 25 ? description.substring(0, 22) + '...' : description;
        
        return `
            <div class="node-simple-content">
                <div class="node-simple-icon tool">
                    <i class="bi bi-tools"></i>
                </div>
                <div class="node-simple-info">
                    <div class="node-simple-title">${this.escapeHtml(displayName)}</div>
                    ${displayDesc ? `<div class="node-simple-desc">${this.escapeHtml(displayDesc)}</div>` : ''}
                </div>
            </div>
        `;
    }
    
    /**
     * Обновление портов при изменении типа агента
     */
    async updatePortsForAgentType(agentType) {
        const shouldHaveOutput = agentType !== 'react';
        const hasOutput = this.ports.has('output');
        
        if (shouldHaveOutput === hasOutput) {
            return;
        }
        
        if (shouldHaveOutput && !hasOutput) {
            this.createPort('output', 'output');
            const outputPort = this.getPort('output');
            outputPort.mount(this.element);
        } else if (!shouldHaveOutput && hasOutput) {
            const outputPort = this.getPort('output');
            outputPort.destroy();
            this.ports.delete('output');
        }
    }
    
    /**
     * Экранирование HTML
     */
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

