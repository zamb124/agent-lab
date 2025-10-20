import { FlowNode } from '../nodes/FlowNode.js';
import { AgentNode } from '../nodes/AgentNode.js';
import { ToolNode } from '../nodes/ToolNode.js';
import { MessageNode } from '../nodes/MessageNode.js';
import { FunctionNode } from '../nodes/FunctionNode.js';
import { RouterNode } from '../nodes/RouterNode.js';
import { BaseNode } from './BaseNode.js';

/**
 * Фабрика для создания нод правильного типа
 */
export class NodeFactory {
    constructor(canvas) {
        this.canvas = canvas;
        this.nodeTypes = new Map();
        
        this.registerDefaults();
    }
    
    /**
     * Регистрация дефолтных типов нод
     */
    registerDefaults() {
        this.register('flow_node', FlowNode);
        this.register('agent_node', AgentNode);
        this.register('tool_node', ToolNode);
        this.register('message_node', MessageNode);
        this.register('function_node', FunctionNode);
        this.register('router_node', RouterNode);
    }
    
    /**
     * Регистрация типа ноды
     */
    register(type, NodeClass) {
        if (!(NodeClass.prototype instanceof BaseNode)) {
            throw new Error(`Класс ${NodeClass.name} должен наследоваться от BaseNode`);
        }
        
        this.nodeTypes.set(type, NodeClass);
    }
    
    /**
     * Создание ноды
     */
    async createNode(data) {
        const NodeClass = this.nodeTypes.get(data.type);
        
        if (!NodeClass) {
            console.warn(`Неизвестный тип ноды: ${data.type}, используется BaseNode`);
            return this.createGenericNode(data);
        }
        
        const node = new NodeClass(data, this.canvas);
        await node.create();
        
        return node;
    }
    
    /**
     * Создание универсальной ноды для неизвестных типов
     */
    async createGenericNode(data) {
        const GenericNode = class extends BaseNode {
            async createDOMElement() {
                const element = document.createElement('div');
                element.className = `canvas-node ${data.type}`;
                
                const name = data.params?.name || data.type;
                const displayName = name.length > 30 ? name.substring(0, 27) + '...' : name;
                
                element.innerHTML = `
                    <div class="node-simple-content">
                        <div class="node-simple-icon default">
                            <i class="bi bi-square"></i>
                        </div>
                        <div class="node-simple-info">
                            <div class="node-simple-title">${this.escapeHtml(displayName)}</div>
                        </div>
                    </div>
                `;
                
                return element;
            }
            
            async createPorts() {
                this.createPort('input', 'input');
                this.createPort('output', 'output');
                this.mountPorts();
            }
            
            escapeHtml(text) {
                if (!text) return '';
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
        };
        
        const node = new GenericNode(data, this.canvas);
        await node.create();
        
        return node;
    }
}

