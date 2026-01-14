/**
 * AgentCreateModal - модальное окно выбора типа агента при создании
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

const AGENT_TEMPLATES = [
    {
        id: 'react',
        name: 'React Agent',
        description: 'Агент с циклом ReAct: рассуждение + действие. Подходит для сложных задач с использованием инструментов.',
        icon: 'ai',
        color: 'linear-gradient(135deg, #10b981 0%, #06b6d4 100%)',
    },
    {
        id: 'graph',
        name: 'Graph Agent',
        description: 'Агент с графовой структурой выполнения. Подходит для последовательных задач с условными переходами.',
        icon: 'workflow',
        color: 'linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%)',
    },
    {
        id: 'multi_agent',
        name: 'Multi-Agent System',
        description: 'Система с несколькими агентами. React агент с субагентами для сложных многошаговых сценариев.',
        icon: 'agent',
        color: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)',
    },
    {
        id: 'function',
        name: 'Function Agent',
        description: 'Агент на основе Python функций. Подходит для вычислений и трансформаций данных.',
        icon: 'code',
        color: 'linear-gradient(135deg, #84cc16 0%, #10b981 100%)',
    },
    {
        id: 'tool',
        name: 'Tool Agent',
        description: 'Агент-инструмент. Выполняет одну конкретную задачу и может быть использован другими агентами.',
        icon: 'tool',
        color: 'linear-gradient(135deg, #f97316 0%, #f59e0b 100%)',
    },
    {
        id: 'external',
        name: 'External Agent',
        description: 'Внешний агент. Подключается к существующему API или сервису через HTTP.',
        icon: 'cloud',
        color: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
    },
];

export class AgentCreateModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            .templates-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: var(--space-4);
                padding: var(--space-2) 0;
            }
            
            .template-card {
                display: flex;
                flex-direction: column;
                padding: var(--space-6);
                background: var(--glass-solid-subtle);
                border: 2px solid transparent;
                border-radius: var(--radius-xl);
                cursor: pointer;
                transition: all var(--duration-normal) var(--easing-default);
                position: relative;
                overflow: hidden;
            }
            
            .template-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
                background: var(--template-color);
                opacity: 0;
                transition: opacity var(--duration-normal) var(--easing-default);
            }
            
            .template-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
                box-shadow: var(--glass-shadow-medium);
                transform: translateY(-2px);
            }
            
            .template-card:hover::before {
                opacity: 1;
            }
            
            .template-icon {
                width: 64px;
                height: 64px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--template-color);
                border-radius: var(--radius-xl);
                margin-bottom: var(--space-4);
                color: white;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
            }
            
            .template-name {
                font-size: var(--text-lg);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }
            
            .template-description {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: var(--leading-relaxed);
            }
            
            .modal-message {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-bottom: var(--space-4);
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        creating: { type: Boolean },
    };

    constructor() {
        super();
        this.size = 'lg';
        this.title = 'Создать агента';
        this.subtitle = 'Выберите тип агента';
        this.creating = false;
    }

    async _onTemplateSelect(template) {
        if (this.creating) return;
        
        this.creating = true;
        
        try {
            const agentConfig = this._generateDefaultConfig(template);
            this.emit('template-selected', { template, config: agentConfig });
            this.close();
        } catch (error) {
            console.error('[AgentCreateModal] Error selecting template:', error);
            this.error(`Ошибка: ${error.message}`);
            this.creating = false;
        }
    }

    _generateDefaultConfig(template) {
        const timestamp = Date.now();
        const agentId = `${template.id}_agent_${timestamp}`;
        
        switch (template.id) {
            case 'react':
                return {
                    agent_id: agentId,
                    name: `Новый ${template.name}`,
                    description: 'Описание агента',
                    tags: ['новый', 'react'],
                    entry: 'main',
                    nodes: {
                        main: {
                            type: 'react_node',
                            prompt: 'Вы полезный ассистент, готовый помочь пользователю.',
                            tools: [],
                            llm: {
                                model: 'gpt-4o-mini',
                                temperature: 0.7,
                            }
                        }
                    },
                    edges: [
                        { from_node: 'main', to_node: null }
                    ],
                    variables: {}
                };
            
            case 'graph':
                return {
                    agent_id: agentId,
                    name: `Новый ${template.name}`,
                    description: 'Описание агента',
                    tags: ['новый', 'graph'],
                    entry: 'start',
                    nodes: {
                        start: {
                            type: 'function',
                            code: 'def run(state):\n    state["step"] = "start"\n    return state'
                        },
                        finish: {
                            type: 'function',
                            code: 'def run(state):\n    state["step"] = "finish"\n    return state'
                        }
                    },
                    edges: [
                        { from_node: 'start', to_node: 'finish' },
                        { from_node: 'finish', to_node: null }
                    ],
                    variables: {}
                };
            
            case 'multi_agent':
                return {
                    agent_id: agentId,
                    name: `Новый ${template.name}`,
                    description: 'Мульти-агентная система',
                    tags: ['новый', 'multi-agent'],
                    entry: 'supervisor',
                    nodes: {
                        supervisor: {
                            type: 'react_node',
                            prompt: 'Вы супервизор, координирующий работу других агентов. Делегируйте задачи подходящим агентам.',
                            tools: [],
                            llm: {
                                model: 'gpt-4o-mini',
                                temperature: 0.3,
                            }
                        }
                    },
                    edges: [
                        { from_node: 'supervisor', to_node: null }
                    ],
                    variables: {}
                };
            
            case 'function':
                return {
                    agent_id: agentId,
                    name: `Новый ${template.name}`,
                    description: 'Агент на основе функций',
                    tags: ['новый', 'function'],
                    entry: 'process',
                    nodes: {
                        process: {
                            type: 'function',
                            code: 'def run(state):\n    """Обработка данных"""\n    result = state.get("input", "")\n    state["output"] = f"Обработано: {result}"\n    return state'
                        }
                    },
                    edges: [
                        { from_node: 'process', to_node: null }
                    ],
                    variables: {}
                };
            
            case 'tool':
                return {
                    agent_id: agentId,
                    name: `Новый ${template.name}`,
                    description: 'Агент-инструмент',
                    tags: ['новый', 'tool'],
                    entry: 'tool_node',
                    nodes: {
                        tool_node: {
                            type: 'tool',
                            code: 'async def execute(args: dict, state: dict) -> str:\n    """Выполнение инструмента"""\n    return f"Результат: {args}"',
                            args_schema: {
                                'input': {
                                    'type': 'string',
                                    'description': 'Входные данные'
                                }
                            }
                        }
                    },
                    edges: [
                        { from_node: 'tool_node', to_node: null }
                    ],
                    variables: {}
                };
            
            case 'external':
                return {
                    agent_id: agentId,
                    name: `Новый ${template.name}`,
                    description: 'Внешний агент',
                    tags: ['новый', 'external'],
                    type: 'external',
                    external_url: 'https://example.com/api/agent',
                    external_status: 'pending',
                    entry: null,
                    nodes: {},
                    edges: [],
                    variables: {}
                };
            
            default:
                throw new Error(`Unknown template: ${template.id}`);
        }
    }

    renderHeader() {
        return html`
            <div style="flex: 1;">
                <h2 class="modal-title">${this.title}</h2>
                ${this.subtitle ? html`<div class="modal-subtitle">${this.subtitle}</div>` : ''}
            </div>
        `;
    }

    renderBody() {
        return html`
            <div class="modal-message">
                Выберите подходящий тип агента для вашей задачи
            </div>
            
            <div class="templates-grid">
                ${AGENT_TEMPLATES.map(template => html`
                    <div 
                        class="template-card" 
                        style="--template-color: ${template.color}"
                        @click=${() => this._onTemplateSelect(template)}
                    >
                        <div class="template-icon">
                            <platform-icon name="${template.icon}" size="32"></platform-icon>
                        </div>
                        <div class="template-name">${template.name}</div>
                        <div class="template-description">${template.description}</div>
                    </div>
                `)}
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button variant="secondary" @click=${() => this.close()}>
                Отмена
            </platform-button>
        `;
    }
}

customElements.define('agent-create-modal', AgentCreateModal);
console.log('[AgentCreateModal] Custom element registered');

