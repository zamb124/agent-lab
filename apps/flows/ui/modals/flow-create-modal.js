/**
 * FlowCreateModal - модальное окно выбора шаблона при создании flow
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

const TEMPLATE_IDS = [
    { id: 'react', icon: 'ai', color: 'linear-gradient(135deg, #99A6F9 0%, #FF885C 100%)' },
    { id: 'graph', icon: 'workflow', color: 'linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%)' },
    { id: 'multi_agent', icon: 'agent', color: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)' },
    { id: 'code', icon: 'code', color: 'linear-gradient(135deg, #84cc16 0%, #99A6F9 100%)' },
    { id: 'external', icon: 'cloud', color: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)' },
];

export class FlowCreateModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            :host .modal-content {
                height: min(74vh, 760px);
                overflow-y: auto;
                overflow-x: hidden;
            }

            .header-search {
                width: min(360px, 45vw);
                height: 36px;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                padding: 0 var(--space-3);
                font-size: var(--text-sm);
                outline: none;
            }

            .header-search:focus {
                border-color: var(--accent);
            }

            .section-title {
                margin: 0 0 var(--space-2) 0;
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .templates-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: var(--space-4);
                padding: var(--space-2) 0;
                min-height: 184px;
                align-content: start;
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
                animation: flowCreateCardEnter 160ms var(--easing-default);
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
                margin: 0;
            }

            .store-section {
                margin-top: var(--space-6);
            }

            .store-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 2px solid var(--border-subtle);
                border-radius: var(--radius-xl);
                transition: all var(--duration-normal) var(--easing-default);
                animation: flowCreateCardEnter 160ms var(--easing-default);
            }

            .store-card:hover {
                border-color: var(--glass-border-medium);
                box-shadow: var(--glass-shadow-medium);
                transform: translateY(-1px);
            }

            .store-card-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .store-badge {
                margin-left: auto;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                background: var(--glass-tint-medium);
                padding: 2px var(--space-2);
                border-radius: var(--radius-sm);
            }

            .store-name {
                margin: 0;
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .store-description {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: var(--leading-relaxed);
            }

            .store-footer {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                justify-content: space-between;
            }

            .store-tags {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                flex-wrap: wrap;
            }

            .store-tag {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                background: var(--glass-tint-medium);
                padding: 2px var(--space-2);
                border-radius: var(--radius-sm);
            }

            .section-divider {
                margin: var(--space-6) 0 var(--space-4) 0;
                border: none;
                border-top: 1px solid var(--border-subtle);
            }

            .store-empty,
            .store-loading {
                padding: var(--space-6) 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                text-align: center;
                min-height: 184px;
                display: flex;
                align-items: center;
                justify-content: center;
                animation: flowCreateCardEnter 140ms var(--easing-default);
            }
            
            .modal-message {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-bottom: var(--space-4);
            }

            @keyframes flowCreateCardEnter {
                from {
                    opacity: 0;
                    transform: translateY(4px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        creating: { type: Boolean },
        storeBundles: { type: Array, state: true },
        storeLoading: { type: Boolean, state: true },
        installingBundleId: { type: String, state: true },
        searchQuery: { type: String, state: true },
    };

    constructor() {
        super();
        this.size = 'xl';
        this.title = '';
        this.creating = false;
        this.storeBundles = [];
        this.storeLoading = false;
        this.installingBundleId = '';
        this.searchQuery = '';
    }

    connectedCallback() {
        super.connectedCallback();
        this.title = this.i18n.t('flow_create.title');
        this._loadStoreBundles();
    }

    async _loadStoreBundles() {
        if (!this.a2a) {
            throw new Error('[FlowCreateModal] a2a service not available');
        }
        this.storeLoading = true;
        try {
            const bundles = await this.a2a.listStoreBundles();
            if (!Array.isArray(bundles)) {
                throw new Error('Store bundles response must be an array');
            }
            this.storeBundles = bundles;
        } catch (error) {
            this.error(this.i18n.t('flow_create.store_load_error', { message: error.message }));
            this.storeBundles = [];
        } finally {
            this.storeLoading = false;
        }
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

    _normalizedQuery() {
        return this.searchQuery.trim().toLowerCase();
    }

    _matchesQuery(values) {
        const query = this._normalizedQuery();
        if (!query) {
            return true;
        }
        return values.some((value) => {
            if (value == null) {
                return false;
            }
            return String(value).toLowerCase().includes(query);
        });
    }

    _visibleTemplates() {
        return TEMPLATE_IDS.filter((template) => {
            const name = this.i18n.t(`flow_create.templates.${template.id}.name`);
            const description = this.i18n.t(`flow_create.templates.${template.id}.description`);
            return this._matchesQuery([template.id, name, description]);
        });
    }

    _visibleStoreBundles() {
        return this.storeBundles.filter((bundle) => this._matchesQuery([
            bundle.bundle_id,
            bundle.flow_id,
            bundle.name,
            bundle.description,
            ...bundle.tags,
        ]));
    }

    async _onInstall(bundle) {
        if (this.installingBundleId || bundle.installed) {
            return;
        }
        this.installingBundleId = bundle.bundle_id;
        try {
            const reloadResult = await this.a2a.reloadFlowFromBundle(bundle.bundle_id);
            const installedFlow = await this.a2a.getFlow(reloadResult.flow_id);
            this.storeBundles = this.storeBundles.map((item) => {
                if (item.bundle_id === bundle.bundle_id) {
                    return { ...item, installed: true };
                }
                return item;
            });
            this.emit('store-flow-installed', { flow: installedFlow, bundle });
            this.close();
        } catch (error) {
            this.error(this.i18n.t('flow_create.err', { message: error.message }));
        } finally {
            this.installingBundleId = '';
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
        return this.title;
    }

    renderHeaderActions() {
        return html`
            <input
                class="header-search"
                type="search"
                .value=${this.searchQuery}
                placeholder=${this.i18n.t('flow_create.search_placeholder')}
                @input=${(e) => { this.searchQuery = e.target.value; }}
            />
        `;
    }

    renderBody() {
        const templates = this._visibleTemplates();
        const storeBundles = this._visibleStoreBundles();
        return html`
            <div class="modal-message">
                ${this.i18n.t('flow_create.intro')}
            </div>

            <h3 class="section-title">${this.i18n.t('flow_create.section_templates')}</h3>
            <div class="templates-grid">
                ${templates.map((template) => html`
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

            <hr class="section-divider" />

            <div class="store-section">
                <h3 class="section-title">${this.i18n.t('flow_create.section_store')}</h3>
                ${this.storeLoading
                    ? html`<div class="store-loading">${this.i18n.t('flow_create.store_loading')}</div>`
                    : storeBundles.length === 0
                        ? html`<div class="store-empty">${this.i18n.t('flow_create.store_empty')}</div>`
                        : html`
                            <div class="templates-grid">
                                ${storeBundles.map((bundle) => html`
                                    <div class="store-card">
                                        <div class="store-card-header">
                                            <platform-icon name="workflow" size="18"></platform-icon>
                                            <h4 class="store-name">${bundle.name}</h4>
                                            <span class="store-badge">${bundle.flow_id}</span>
                                        </div>
                                        <p class="store-description">${bundle.description ?? ''}</p>
                                        <div class="store-footer">
                                            <div class="store-tags">
                                                ${bundle.tags.map((tag) => html`<span class="store-tag">${tag}</span>`)}
                                            </div>
                                            <platform-button
                                                size="sm"
                                                ?disabled=${bundle.installed || this.installingBundleId === bundle.bundle_id}
                                                @click=${() => this._onInstall(bundle)}
                                            >
                                                ${bundle.installed
                                                    ? this.i18n.t('flow_create.installed')
                                                    : this.installingBundleId === bundle.bundle_id
                                                        ? this.i18n.t('flow_create.installing')
                                                        : this.i18n.t('flow_create.install')}
                                            </platform-button>
                                        </div>
                                    </div>
                                `)}
                            </div>
                        `}
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
