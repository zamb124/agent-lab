/**
 * AgentsSidebar - sidebar для Agents Builder
 * Использует platform-sidebar с поддержкой collapsed/mobile mode
 */
import { html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { AgentsStore } from '../../store/agents.store.js';
import '@platform/lib/components/layout/platform-sidebar.js';
import '@platform/lib/components/layout/sidebar-section.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import './agent-card.js';

export class AgentsSidebar extends PlatformElement {
    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host {
                display: block;
                height: 100%;
            }

            platform-sidebar {
                height: 100%;
            }

            .create-btn {
                width: 22px;
                height: 22px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                color: white;
                background: var(--accent);
                border: none;
                cursor: pointer;
                box-shadow: 0 2px 6px rgba(16, 185, 129, 0.2);
                transition: all var(--duration-normal) var(--easing-default);
            }

            .create-btn:hover {
                background: var(--accent-hover);
                transform: scale(1.1);
                box-shadow: 0 3px 8px rgba(16, 185, 129, 0.3);
            }

            sidebar-section {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }

            .agents-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                flex: 1;
                overflow-y: auto;
                overflow-x: hidden;
                min-height: 0;
            }

            .footer-links {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }

            .footer-link {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border: none;
                text-decoration: none;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .footer-link:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            :host([collapsed]) .footer-links {
                display: flex;
                flex-direction: column;
                align-items: center;
            }

            :host([collapsed]) .footer-link {
                width: 36px;
                height: 36px;
                padding: 0;
                justify-content: center;
            }

            :host([collapsed]) .footer-link span {
                display: none;
            }

            :host([collapsed]) platform-user {
                display: none;
            }
        `
    ];

    constructor() {
        super();
        this.collapsed = false;
        this.mobileOpen = false;
        
        this.state = this.use(s => ({
            agents: s.agents.list,
            currentAgentId: s.agents.currentId,
            expandedAgents: s.ui.expandedAgents,
        }));
    }

    connectedCallback() {
        super.connectedCallback();
        AgentsStore.loadAgents(this.a2a);
    }

    toggleCollapse() {
        this.collapsed = !this.collapsed;
        this.emit('collapse-change', { collapsed: this.collapsed });
    }

    toggleMobile() {
        this.mobileOpen = !this.mobileOpen;
        this.emit('mobile-change', { open: this.mobileOpen });
    }

    closeMobile() {
        if (this.mobileOpen) {
            this.mobileOpen = false;
            this.emit('mobile-change', { open: false });
            window.dispatchEvent(new CustomEvent('platform-sidebar-mobile-change', {
                detail: { open: false },
            }));
        }
    }

    _createAgent() {
        const elementConstructor = customElements.get('agent-create-modal');
        
        if (!elementConstructor) {
            this.error('Модальное окно не загружено');
            return;
        }
        
        const modal = new elementConstructor();
        document.body.appendChild(modal);
        
        requestAnimationFrame(() => {
            modal.setAttribute('open', '');
        });
        
        modal.addEventListener('template-selected', async (e) => {
            const { config } = e.detail;
            
            try {
                const createdAgent = await AgentsStore.createAgent(config, this.a2a);
                this.success(`Агент "${createdAgent.name}" создан`);
                
                setTimeout(() => {
                    this._editAgent(createdAgent.agent_id);
                }, 100);
            } catch (error) {
                this.error(`Ошибка создания: ${error.message}`);
            }
        });
        
        modal.addEventListener('close', () => modal.remove());
    }

    _editAgent(agentId) {
        const modal = document.createElement('agent-edit-modal');
        modal.agentId = agentId;
        document.body.appendChild(modal);
        
        requestAnimationFrame(() => {
            modal.setAttribute('open', '');
        });
        
        modal.addEventListener('close', () => modal.remove());
    }

    _openSessions() {
        const modal = document.createElement('sessions-modal');
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _openMCPServers() {
        const modal = document.createElement('mcp-servers-modal');
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _openVariables() {
        const modal = document.createElement('variables-modal');
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _handleAgentAction(e) {
        const { action, agentId, skillId } = e.detail;
        
        switch (action) {
            case 'chat':
                if (skillId) {
                    AgentsStore.setCurrentAgentAndSkill(agentId, skillId);
                } else {
                    AgentsStore.setCurrentAgent(agentId);
                }
                this.closeMobile();
                break;
            case 'edit':
                if (skillId) {
                    const modal = document.createElement('agent-edit-modal');
                    modal.agentId = agentId;
                    modal.skillId = skillId;
                    document.body.appendChild(modal);
                    requestAnimationFrame(() => modal.setAttribute('open', ''));
                    modal.addEventListener('close', () => modal.remove());
                } else {
                    this._editAgent(agentId);
                }
                break;
            case 'delete':
                this._deleteAgent(agentId);
                break;
            case 'delete-skill':
                this._deleteSkill(agentId, skillId);
                break;
            case 'create-skill':
                this._createSkill(agentId);
                break;
            case 'toggle':
                AgentsStore.toggleExpandedAgent(agentId);
                break;
        }
    }

    async _deleteAgent(agentId) {
        const modal = document.createElement('confirm-modal');
        modal.title = 'Удалить агента?';
        modal.message = `Вы уверены что хотите удалить агента "${agentId}"? Это действие необратимо.`;
        modal.confirmText = 'Удалить';
        modal.confirmVariant = 'danger';
        document.body.appendChild(modal);
        
        const confirmed = await modal.confirm();
        modal.remove();
        
        if (!confirmed) return;
        
        try {
            await AgentsStore.deleteAgent(agentId, this.a2a);
            this.success('Агент удален');
        } catch (error) {
            this.error(`Ошибка удаления: ${error.message}`);
            throw error;
        }
    }

    async _deleteSkill(agentId, skillId) {
        const modal = document.createElement('confirm-modal');
        modal.title = 'Удалить скилл?';
        modal.message = `Вы уверены что хотите удалить скилл "${skillId}"?`;
        modal.confirmText = 'Удалить';
        modal.confirmVariant = 'danger';
        document.body.appendChild(modal);
        
        const confirmed = await modal.confirm();
        modal.remove();
        
        if (!confirmed) return;
        
        try {
            await AgentsStore.deleteSkill(agentId, skillId, this.a2a);
            this.success('Скилл удален');
        } catch (error) {
            this.error(`Ошибка удаления: ${error.message}`);
            throw error;
        }
    }

    _createSkill(agentId) {
        const modal = document.createElement('skill-create-modal');
        modal.agentId = agentId;
        document.body.appendChild(modal);
        modal.addEventListener('close', () => modal.remove());
    }

    render() {
        const { agents, currentAgentId, expandedAgents } = this.state.value;

        return html`
            <platform-sidebar
                logo-src="/static/core/assets/service_logos/agents_logo.svg"
                logo-text="Agents"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => this.collapsed = e.detail.collapsed}
                @mobile-change=${(e) => this.mobileOpen = e.detail.open}
            >
                <sidebar-section title="Все агенты" icon="folder" ?collapsed=${this.collapsed}>
                    <button 
                        slot="actions"
                        class="create-btn" 
                        title="Создать агента" 
                        @click=${this._createAgent}
                    >
                        <platform-icon name="plus" size="12"></platform-icon>
                    </button>
                    <div class="agents-list">
                        ${repeat(
                            agents,
                            (a) => a.agent_id,
                            (agent) => html`
                                <agent-card
                                    .agent=${agent}
                                    ?active=${agent.agent_id === currentAgentId}
                                    ?expanded=${!!expandedAgents[agent.agent_id]}
                                    ?collapsed=${this.collapsed}
                                    @agent-action=${this._handleAgentAction}
                                ></agent-card>
                            `
                        )}
                    </div>
                </sidebar-section>

                <div slot="footer">
                    <div class="footer-links">
                        <a class="footer-link" href="/docs" target="_blank">
                            <platform-icon name="file" size="16"></platform-icon>
                            <span>Docs</span>
                        </a>
                        <button class="footer-link" @click=${this._openSessions}>
                            <platform-icon name="chat" size="16"></platform-icon>
                            <span>Сессии</span>
                        </button>
                        <button class="footer-link" @click=${this._openMCPServers}>
                            <platform-icon name="cloud" size="16"></platform-icon>
                            <span>MCP</span>
                        </button>
                        <button class="footer-link" @click=${this._openVariables}>
                            <platform-icon name="key" size="16"></platform-icon>
                            <span>Vars</span>
                        </button>
                    </div>
                    <platform-user block></platform-user>
                </div>
            </platform-sidebar>
        `;
    }
}

customElements.define('agents-sidebar', AgentsSidebar);
