/**
 * FlowCreateModal - модальное окно выбора шаблона при создании flow
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

const TEMPLATE_IDS = [
    { id: 'react', icon: 'ai', color: 'linear-gradient(135deg, #10b981 0%, #06b6d4 100%)' },
    { id: 'graph', icon: 'workflow', color: 'linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%)' },
    { id: 'multi_agent', icon: 'agent', color: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)' },
    { id: 'code', icon: 'code', color: 'linear-gradient(135deg, #84cc16 0%, #10b981 100%)' },
    { id: 'external', icon: 'cloud', color: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)' },
];

export class FlowCreateModal extends PlatformModal {
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
        this.title = '';
        this.subtitle = '';
        this.creating = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this.title = this.i18n.t('flow_create.title');
        this.subtitle = this.i18n.t('flow_create.subtitle');
    }

    _tagsFromGen(templateId) {
        const raw = this.i18n.t(`flow_create.gen.${templateId}.tags`);
        return raw.split(',').map((s) => s.trim()).filter(Boolean);
    }

    async _onTemplateSelect(template) {
        if (this.creating) return;
        
        this.creating = true;
        
        try {
            const flowConfig = this._generateDefaultConfig(template);
            this.emit('template-selected', { template, config: flowConfig });
            this.close();
        } catch (error) {
            console.error('[FlowCreateModal] Error selecting template:', error);
            this.error(this.i18n.t('flow_create.err', { message: error.message }));
            this.creating = false;
        }
    }

    _generateDefaultConfig(template) {
        const timestamp = Date.now();
        const flowId = `${template.id}_flow_${timestamp}`;
        const g = (key) => this.i18n.t(`flow_create.gen.${template.id}.${key}`);

        switch (template.id) {
            case 'react':
                return {
                    flow_id: flowId,
                    name: g('flow_name'),
                    description: g('description'),
                    tags: this._tagsFromGen('react'),
                    entry: 'main',
                    nodes: {
                        main: {
                            type: 'llm_node',
                            prompt: g('prompt'),
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
                    flow_id: flowId,
                    name: g('flow_name'),
                    description: g('description'),
                    tags: this._tagsFromGen('graph'),
                    entry: 'start',
                    nodes: {
                        start: {
                            type: 'code',
                            code: 'def execute(args, state):\n    state.result = "start"\n    return {"step": "start"}'
                        },
                        finish: {
                            type: 'code',
                            code: 'def execute(args, state):\n    state.result = "finish"\n    return {"step": "finish"}'
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
                    flow_id: flowId,
                    name: g('flow_name'),
                    description: g('description'),
                    tags: this._tagsFromGen('multi_agent'),
                    entry: 'supervisor',
                    nodes: {
                        supervisor: {
                            type: 'llm_node',
                            prompt: g('prompt'),
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
            
            case 'code':
                return {
                    flow_id: flowId,
                    name: g('flow_name'),
                    description: g('description'),
                    tags: this._tagsFromGen('code'),
                    entry: 'main',
                    nodes: {
                        main: {
                            type: 'code',
                            code: 'def execute(args, state):\n    """Process data"""\n    result = args.get("input", "")\n    return {"output": f"Processed: {result}"}',
                        },
                    },
                    edges: [{ from_node: 'main', to_node: null }],
                    variables: {},
                };

            case 'external':
                return {
                    flow_id: flowId,
                    name: g('flow_name'),
                    description: g('description'),
                    tags: this._tagsFromGen('external'),
                    type: 'external',
                    external_url: 'https://example.com/api/flow',
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
                ${this.i18n.t('flow_create.intro')}
            </div>
            
            <div class="templates-grid">
                ${TEMPLATE_IDS.map((template) => html`
                    <div 
                        class="template-card" 
                        style="--template-color: ${template.color}"
                        @click=${() => this._onTemplateSelect(template)}
                    >
                        <div class="template-icon">
                            <platform-icon name="${template.icon}" size="32"></platform-icon>
                        </div>
                        <div class="template-name">${this.i18n.t(`flow_create.templates.${template.id}.name`)}</div>
                        <div class="template-description">${this.i18n.t(`flow_create.templates.${template.id}.description`)}</div>
                    </div>
                `)}
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button variant="secondary" @click=${() => this.close()}>
                ${this.i18n.t('flow_create.cancel')}
            </platform-button>
        `;
    }
}

customElements.define('flow-create-modal', FlowCreateModal);
